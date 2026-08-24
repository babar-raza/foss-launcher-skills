"""Run-bound control plane for the S-84 product refresh workflow.

This module makes one refresh execution an explicit state machine instead of
letting independently-invoked commands infer ownership from mutable
product-level reports. Runtime artifacts are local under ``reports/``; content
truth remains a function of Git, the pinned FOSS source SHA, and current
knowledge.

The command deliberately separates planning from mutation. ``run --dry-run``
advances through input refresh and impact planning, then stops at ``PLANNED``.
A normal ``run`` continues through the registered S-62/S-105 writers and the
blocking validation chain. Every mutating command requires a stable session
identity and an explicit run ID.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

import yaml

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

import session_identity  # noqa: E402
import freshness_guard  # noqa: E402
from advisory_lock import FileLock, LockTimeout  # noqa: E402
from core.fs import atomic_write, atomic_write_bytes  # noqa: E402
from lib.schema_validators import (  # noqa: E402
    validate_refresh_page_decision,
    validate_refresh_run_manifest,
)
from lib.provenance import is_manually_curated, read_provenance  # noqa: E402
from lib.reference_filter import index_generator_version_is_stale  # noqa: E402
from commands.ops import page_impact_matrix  # noqa: E402
from commands.knowledge import stale_detect  # noqa: E402
from commands.content import batch_reference  # noqa: E402
from commands.diagnostics import content_coverage_audit  # noqa: E402

SCHEMA_VERSION = 3
MODES = frozenset({"upstream", "remediation", "combined"})
TERMINAL_STATES = frozenset({"COMMITTED", "ABANDONED"})
VALIDATION_FIELDS = (
    "post_refresh_verify",
    "content_audit",
    "link_validation",
    "oracle",
    "triage_confirm",
    "seo_stability",
)
# MT030-2026-08-13: recorded in the manifest and in data/knowledge_state.json but
# deliberately excluded from the blocking not_pass check below. Truth-audit (S-38)
# debt is systemic and pre-existing (TRUTH-AUDIT-DEBT-001; 3d/net alone needed 7
# convergence passes) -- an immediate hard gate here would block nearly every
# future refresh repo-wide. Phase 1 of PDF-JAVA-REFRESH-003's fix: make the
# verdict visible and durable. Phase 2 (a real, differential gate that blocks only
# on FAILs a run's own diff introduced, not pre-existing debt) is a separate,
# future, backlog-tracked change gated on TRUTH-AUDIT-DEBT-001's closure.
ADVISORY_VALIDATION_FIELDS = ("truth_audit",)
NEXT_STATES = {
    "CREATED": {"INPUTS_PINNED", "BLOCKED", "ABANDONED"},
    "INPUTS_PINNED": {"PLANNED", "BLOCKED", "ABANDONED"},
    "PLANNED": {"APPLYING", "BLOCKED", "ABANDONED"},
    "APPLYING": {"VALIDATING", "BLOCKED", "ABANDONED"},
    "VALIDATING": {"READY_TO_COMMIT", "BLOCKED", "ABANDONED"},
    "READY_TO_COMMIT": {"COMMITTED", "BLOCKED", "ABANDONED"},
    "BLOCKED": {
        "INPUTS_PINNED",
        "PLANNED",
        "APPLYING",
        "VALIDATING",
        "READY_TO_COMMIT",
        "ABANDONED",
    },
    "COMMITTED": set(),
    "ABANDONED": set(),
}
_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
_repo_root = _DEFAULT_REPO_ROOT
_reports_root = _DEFAULT_REPO_ROOT / "reports"
_command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run
_source_sha_resolver: Callable[[str, str], str | None] | None = None
_now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)


class RefreshRunError(RuntimeError):
    """Raised when a run contract or state transition is unsafe."""


def configure(
    *,
    repo_root: Path | str | None = None,
    reports_root: Path | str | None = None,
    command_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    source_sha_resolver: Callable[[str, str], str | None] | None = None,
    now: Callable[[], datetime] | None = None,
) -> None:
    """Override external boundaries for tests; call without arguments to reset."""
    global _repo_root, _reports_root, _command_runner, _source_sha_resolver, _now
    _repo_root = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    _reports_root = (
        Path(reports_root) if reports_root is not None else _repo_root / "reports"
    )
    _command_runner = command_runner or subprocess.run
    _source_sha_resolver = source_sha_resolver
    _now = now or (lambda: datetime.now(timezone.utc))
    # FRESH-001 (2026-08-14): keep freshness_guard's module-level paths in lockstep
    # with this module's own configure() -- see batch_reference.py for the same
    # pattern/rationale. page_impact_matrix follows the identical precedent
    # (Task 2, 2026-08-23) -- without this, its own default repo_root would
    # silently diverge from this module's under test, writing real files into
    # the actual repo's reports/ tree instead of a test's tmp_path (caught
    # live: an early version of this wiring did exactly that).
    freshness_guard.configure(repo_root=_repo_root)
    page_impact_matrix.configure(repo_root=_repo_root)
    # content_coverage_audit.scan_product() calls batch_reference.run(), which
    # reads batch_reference's OWN module-level KNOWLEDGE_ROOT/CONTENT_ROOT --
    # same FRESH-001 lockstep requirement, one level removed (Task: content
    # coverage audit, 2026-08-24, closes the "content generation never
    # triggered for a real knowledge advance" gap found live for pdf/java).
    batch_reference.configure(repo_root=_repo_root)


def _utc() -> str:
    return _now().astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_token(value: str, label: str) -> str:
    if not isinstance(value, str) or not _SAFE_TOKEN.fullmatch(value) or ".." in value:
        raise RefreshRunError(
            f"{label} must match {_SAFE_TOKEN.pattern!r} and must not contain '..'"
        )
    return value


def _session_id(explicit: str | None = None) -> str:
    # Production concurrency redesign (2026-08-01), Step 2: was the weakest of
    # 4 duplicate identity-resolution copies -- no CLAUDE_CODE_SESSION_ID
    # fallback, so every call from a harness session with no explicit
    # --session-id/AGENT_SESSION_ID/CODEX_THREAD_ID hard-errored. Delegates to
    # the shared module (see lib/session_identity.py for full precedence
    # rationale) for both resolution and sanitization; _safe_token below still
    # applies this module's own stricter policy (must start alnum, <=128
    # chars, no "..") on top of session_identity's generic sanitize().
    value = session_identity.resolve_sanitized(explicit)
    if not value:
        raise RefreshRunError(
            "A stable session identity is required: pass --session-id or set "
            "AGENT_SESSION_ID/CODEX_THREAD_ID/CLAUDE_CODE_SESSION_ID"
        )
    return _safe_token(value, "session_id")


def _run_root(family: str, platform: str, run_id: str) -> Path:
    return _reports_root / "refresh_runs" / family / platform / run_id


def _product_root(family: str, platform: str) -> Path:
    return _reports_root / "refresh_runs" / family / platform


def _manifest_path(family: str, platform: str, run_id: str) -> Path:
    return _run_root(family, platform, run_id) / "manifest.json"


def _active_path(family: str, platform: str) -> Path:
    return _product_root(family, platform) / "ACTIVE.json"


def _product_lock_path(family: str, platform: str) -> Path:
    return _reports_root / "locks" / "refresh" / f"{family}-{platform}.lock"


@contextmanager
def _product_guard(family: str, platform: str) -> Iterator[None]:
    try:
        with FileLock(_product_lock_path(family, platform), timeout=10.0):
            yield
    except LockTimeout as exc:
        raise RefreshRunError(str(exc)) from exc


def _git(*args: str, check: bool = True) -> str:
    result = _command_runner(
        ["git", *args],
        cwd=str(_repo_root),
        capture_output=True,
        text=True,
        timeout=30,
    )
    if check and result.returncode != 0:
        raise RefreshRunError(
            f"git {' '.join(args)} failed ({result.returncode}): "
            f"{(result.stderr or result.stdout).strip()}"
        )
    return result.stdout.strip()


def _head_sha() -> str:
    sha = _git("rev-parse", "HEAD")
    if not sha:
        raise RefreshRunError("Could not resolve repository HEAD")
    return sha


def _model_state(family: str, platform: str) -> dict[str, Any]:
    path = _repo_root / "knowledge" / family / platform / "merged" / "model.yaml"
    if not path.is_file():
        raise RefreshRunError(f"Knowledge model not found: {path.relative_to(_repo_root)}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        raise RefreshRunError(f"Knowledge model is unreadable: {exc}") from exc
    # FRESH-001 (2026-08-14, T7): migrated from a raw stale_since read to the shared
    # freshness_guard gate (degraded mode — no network call, matching this function's
    # prior no-network behavior). Preserves the exact contract callers depend on:
    # return the parsed model dict on success, raise RefreshRunError otherwise.
    allowed, fresh_result = freshness_guard.is_generation_allowed(family, platform, mode="degraded")
    if not allowed:
        raise RefreshRunError(
            f"Knowledge model is not fresh (state={fresh_result.state}): {fresh_result.reason}; "
            f"refresh knowledge first"
        )
    sha = data.get("repo_sha")
    if not isinstance(sha, str) or not sha:
        raise RefreshRunError("Knowledge model has no non-empty repo_sha")
    return data


def _source_sha(family: str, platform: str) -> str:
    if _source_sha_resolver is not None:
        value = _source_sha_resolver(family, platform)
        if value:
            return value
        raise RefreshRunError(f"Clone HEAD unavailable for {family}/{platform}")
    try:
        from core.clone_cache import clone_head_sha

        value = clone_head_sha(family, platform)
    except Exception as exc:
        raise RefreshRunError(
            f"Clone HEAD unavailable for {family}/{platform}: {exc}"
        ) from exc
    if not value:
        raise RefreshRunError(f"Clone HEAD unavailable for {family}/{platform}")
    return value


def _relative_input(path: Path) -> str:
    resolved = path.resolve()
    root = _repo_root.resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError as exc:
        raise RefreshRunError(
            f"Scope manifest must be inside the repository: {path}"
        ) from exc


def _scope_manifest(path: str | None, mode: str) -> tuple[str | None, str | None]:
    if mode == "remediation" and not path:
        raise RefreshRunError("remediation mode requires --scope-manifest")
    if not path:
        return None, None
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = _repo_root / candidate
    if not candidate.is_file():
        raise RefreshRunError(f"Scope manifest not found: {candidate}")
    rel = _relative_input(candidate)
    digest = "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest()
    return rel, digest


def _scope_paths_from_file(relative_path: str | None) -> list[str]:
    if relative_path is None:
        return []
    path = _repo_root / relative_path
    raw = path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = yaml.safe_load(raw)
    if not isinstance(data, dict) or not isinstance(data.get("paths"), list):
        raise RefreshRunError(
            "Scope manifest must be an object with a 'paths' list"
        )
    paths: list[str] = []
    for value in data["paths"]:
        if not isinstance(value, str) or not value.strip():
            raise RefreshRunError("Every scope path must be a non-empty string")
        p = Path(value)
        if p.is_absolute() or ".." in p.parts:
            raise RefreshRunError(f"Unsafe scope path: {value}")
        normalized = p.as_posix()
        if not normalized.startswith("content/"):
            raise RefreshRunError(f"Scope path must be under content/: {value}")
        paths.append(normalized)
    return sorted(set(paths))


def _assert_product_scope(paths: list[str], family: str, platform: str) -> None:
    """Require every content path to belong to the run's English product.

    Site path shapes differ (found live, MT014-2026-07-29-PDF-GO-REDO): every
    site except blog.aspose.org carries an English locale segment --
    content/{site}/en/{family}/{platform}/... (docs, kb, reference, AND
    products -- e.g. content/products.aspose.org/en/pdf/go/_index.md; other
    products.aspose.org top-level entries are non-English locale codes like
    ar/bg/ca, confirming "en" is a real locale segment there too, not absent).
    Only blog.aspose.org omits it: content/blog.aspose.org/{family}/{platform}/...
    (its non-English variants suffix the *filename*, e.g. index.fr.md, rather
    than adding a locale directory). This function previously special-cased
    "products.aspose.org" as the no-locale site instead of "blog.aspose.org" --
    backwards -- so every real refresh scope touching blog or products pages
    was incorrectly rejected as "outside" the product.
    """
    invalid: list[str] = []
    for value in paths:
        parts = Path(value).parts
        if len(parts) < 4 or parts[0] != "content":
            invalid.append(value)
            continue
        if parts[1] == "blog.aspose.org":
            matches = len(parts) >= 4 and parts[2:4] == (family, platform)
        else:
            matches = (
                len(parts) >= 5
                and parts[2] == "en"
                and parts[3:5] == (family, platform)
            )
        if not matches:
            invalid.append(value)
    if invalid:
        raise RefreshRunError(
            f"Scope contains paths outside {family}/{platform}: {invalid[:5]}"
        )


def _scope_digest(paths: list[str], input_digest: str | None) -> str:
    payload = json.dumps(
        {"paths": sorted(paths), "input_digest": input_digest},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _path_hash(relative_path: str) -> str:
    path = _repo_root / relative_path
    if not path.is_file():
        return "MISSING"
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _casefold_path_diff(a: set[str], b: set[str]) -> tuple[set[str], set[str]]:
    """Set difference for content paths, tolerant of case-only variance.

    Windows and default-config macOS filesystems are case-insensitive: a
    generator writing 'Camera.md' when git still tracks 'camera.md' silently
    aliases to the same on-disk file rather than registering as a rename, so
    git-diff output, decision-row page_path values, and a scope manifest
    built at different pipeline stages can each report a different casing
    for the identical physical page (confirmed live, 2026-08-14: 3d/java's
    scope reconciliation reported camera.md/entity.md/light.md/material.md/
    mesh.md as both "missing" and "unexpected" simultaneously purely from
    casing, even though 25c5081230 had already fixed this exact page set
    once before -- the case only differed in the tool's own path bookkeeping,
    not on disk). Case-only pairs are real matches, not scope violations;
    only a genuine case-insensitive duplicate (same casefolded key, both
    sides supply it) collapses to one entry and is excluded from both output
    sets, same as an exact match would be.

    Returns (a_only, b_only): items with no casefold match on the other side.
    """
    a_keys = {p.casefold(): p for p in a}
    b_keys = {p.casefold(): p for p in b}
    a_only = {p for key, p in a_keys.items() if key not in b_keys}
    b_only = {p for key, p in b_keys.items() if key not in a_keys}
    return a_only, b_only


def _reconcile_scope_and_decisions(
    scope_paths: list[str],
    decision_rows: list[dict[str, Any]],
    initial_hashes: dict[str, str],
) -> tuple[list[str], list[str]]:
    """Return (real_missing, real_unexpected): the subset of scope/decision
    mismatches that indicate a genuine problem, filtering out two classes of
    expected noise found live during MT014-2026-07-29-PDF-GO-REDO's first
    real combined/upstream-mode run:

    - "missing": body_refresh.py has early-exit paths (auto_updatable:false
      pages; pages with zero actionable BODY_UPDATE sections) that never
      call _emit_run_decision, so a scoped no-op page can legitimately have
      no decision row at all. A missing decision is only a real problem if
      the page's bytes actually changed from the initial_hashes snapshot
      frozen in scope.json at PLANNED time.
    - "unexpected": batch_reference.py's --update mode decides and logs a
      disposition for every class in knowledge_delta.json, not just ones in
      this run's PIA-derived scope. An out-of-scope decision is only a real
      problem if its disposition implies a write happened
      (BODY_UPDATED/EVIDENCE_ONLY/GENERATED/RETIRED) AND, for GENERATED
      specifically, the page did not provably start empty (body_hash_before
      equal to the hash of empty content) -- an additive write to a
      genuinely new page cannot clobber existing content, which is the
      property scope-pinning exists to protect.

    Used by both apply_run's post-write reconciliation and
    _assert_run_evidence_ready's pre-commit evidence check -- keep both
    callers on this single implementation rather than two divergent copies.
    """
    from commands.content.body_refresh import _normalized_body_hash

    scope_set = set(scope_paths)
    decision_paths = {row.get("page_path") for row in decision_rows}
    missing_set, unexpected_set = _casefold_path_diff(scope_set, decision_paths)
    missing = sorted(missing_set)
    unexpected = sorted(unexpected_set)

    real_missing = [
        p for p in missing
        if _path_hash(p) != initial_hashes.get(p, "MISSING")
    ]

    empty_hash = _normalized_body_hash("")
    write_dispositions = {"BODY_UPDATED", "EVIDENCE_ONLY", "GENERATED", "RETIRED"}
    decisions_by_path: dict[str, list[dict[str, Any]]] = {}
    for row in decision_rows:
        decisions_by_path.setdefault(row.get("page_path"), []).append(row)

    def _is_real_violation(row: dict[str, Any]) -> bool:
        disposition = row.get("disposition")
        if disposition not in write_dispositions:
            return False
        if disposition == "GENERATED" and row.get("body_hash_before") == empty_hash:
            return False
        return True

    real_unexpected = [
        p for p in unexpected
        if any(_is_real_violation(row) for row in decisions_by_path.get(p, []))
    ]
    return real_missing, real_unexpected


def _allowed_commit_paths(
    scope_paths: list[str],
    decision_rows: list[dict[str, Any]],
    run_root: Path | None = None,
) -> set[str]:
    """Return the pinned scope plus any provably-additive GENERATED pages.

    scope.json is frozen from PIA's existing-page assessment at PLANNED time
    and cannot name a class file that did not exist yet, so a brand-new
    reference page batch_reference.py generates from api_surface.json always
    falls outside the pinned scope. Tolerate exactly the same case
    _reconcile_scope_and_decisions already does for apply_run's own
    post-write reconciliation: GENERATED with body_hash_before == the hash of
    empty content cannot have clobbered existing content, which is the
    property scope-pinning exists to protect.

    run_root: when given, also allows any path recorded in
    _record_extra_allowed_hash's sidecar (TC-DUPIDX-02's deliberately
    receipt-less _index.md regeneration, an S-73 manual-edit fallback, or a
    pre-commit-hook content_hash normalization touching an already-authorized
    file) -- mirrors the same tolerance _assert_scope_ownership's OCC guard
    already applies, so a committed path isn't flagged twice for the same
    already-authorized reason (confirmed live 2026-08-14, 3d/java).
    """
    from commands.content.body_refresh import _normalized_body_hash

    empty_hash = _normalized_body_hash("")
    allowed = set(scope_paths)
    allowed.update(
        str(row.get("page_path"))
        for row in decision_rows
        if row.get("disposition") == "GENERATED"
        and row.get("body_hash_before") == empty_hash
    )
    if run_root is not None:
        allowed.update(_load_extra_allowed_hashes(run_root).keys())
    return allowed


def _file_digest(path: Path) -> str:
    if not path.is_file():
        return "MISSING"
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _assert_pinned_scope(manifest: dict[str, Any]) -> dict[str, Any]:
    """Validate the exact scope artifact bound at planning time."""
    run_root = _run_root(
        manifest["family"], manifest["platform"], manifest["run_id"]
    )
    scope_path = run_root / "scope.json"
    if not scope_path.is_file():
        raise RefreshRunError("Pinned scope.json is missing")
    if (
        (manifest.get("output_digests") or {}).get("scope")
        != _file_digest(scope_path)
    ):
        raise RefreshRunError("Pinned scope.json digest does not match the manifest")
    try:
        scope = json.loads(scope_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RefreshRunError(f"Pinned scope.json is unreadable: {exc}") from exc
    scope_paths = list((manifest.get("scope") or {}).get("paths") or [])
    if (
        scope.get("run_id") != manifest["run_id"]
        or scope.get("family") != manifest["family"]
        or scope.get("platform") != manifest["platform"]
        or scope.get("paths") != scope_paths
        or (manifest.get("scope") or {}).get("digest")
        != _scope_digest(
            scope_paths, (manifest.get("scope") or {}).get("input_digest")
        )
    ):
        raise RefreshRunError("Pinned scope and run manifest do not reconcile")
    return scope


def _extra_allowed_hashes_path(run_root: Path) -> Path:
    return run_root / "extra_allowed_hashes.json"


def _record_extra_allowed_hash(run_root: Path, page_path: str, file_hash: str) -> None:
    """Authorize an out-of-band write with no receipt of its own.

    Some writers deliberately bypass the receipt/decision ledger -- e.g. the
    TC-DUPIDX-02 grouped-index regeneration in apply_run(), which rewrites
    _index.md without emitting a page_decisions.jsonl row (folding it into
    the pinned scope would make _reconcile_scope_and_decisions() see a
    phantom missing/unexpected entry for it, per that call site's own
    comment). _assert_scope_ownership()'s later OCC check has no such
    carve-out and, unpatched, blocks on exactly this deliberate write
    (confirmed live 2026-08-14 on 3d/java). This sidecar closes that gap
    without touching the digest-pinned scope.json.
    """
    path = _extra_allowed_hashes_path(run_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, list[str]] = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
    data.setdefault(page_path, [])
    if file_hash not in data[page_path]:
        data[page_path].append(file_hash)
    path.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _load_extra_allowed_hashes(run_root: Path) -> dict[str, set[str]]:
    path = _extra_allowed_hashes_path(run_root)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        key: set(value)
        for key, value in data.items()
        if isinstance(value, list)
    }


def _augment_initial_hashes_with_extra_allowed(
    initial_hashes: dict[str, str], run_root: Path
) -> dict[str, str]:
    """Treat an authorized out-of-band write (_record_extra_allowed_hash) as
    'unchanged from initial' for _reconcile_scope_and_decisions()'s
    missing-page hash check, so a deliberately receipt-less write -- e.g.
    TC-DUPIDX-02's _index.md regeneration in apply_run() -- is not reported
    as a real scope/decision gap (confirmed live 2026-08-14 on 3d/java).
    Only takes effect when the CURRENT on-disk hash is itself one of the
    authorized values; any other drift still blocks, same as before.
    """
    extra = _load_extra_allowed_hashes(run_root)
    if not extra:
        return initial_hashes
    augmented = dict(initial_hashes)
    for page_path, hashes in extra.items():
        current = _path_hash(page_path)
        if current in hashes:
            augmented[page_path] = current
    return augmented


def _assert_scope_ownership(manifest: dict[str, Any]) -> None:
    """OCC guard for uncommitted/concurrent edits and interrupted resumes.

    Hash keys are merged case-insensitively (casefold) before comparison:
    Windows/macOS filesystem aliasing means a receipt recorded for
    'Camera.md' authorizes the same physical file found at 'camera.md' in
    scope, and vice versa -- the OCC-guard counterpart to the same gap
    _casefold_path_diff() closes for scope/decision reconciliation
    (confirmed live 2026-08-14 on 3d/java).
    """
    run_root = _run_root(
        manifest["family"], manifest["platform"], manifest["run_id"]
    )
    scope = _assert_pinned_scope(manifest)
    initial_hashes = dict(scope.get("initial_hashes") or {})
    allowed_hashes: dict[str, set[str]] = {}
    display_path: dict[str, str] = {}

    def _add(page_path: str, file_hash: Any) -> None:
        key = page_path.casefold()
        allowed_hashes.setdefault(key, set()).add(file_hash)
        display_path.setdefault(key, page_path)

    for path, value in initial_hashes.items():
        _add(path, value)

    decisions_path = run_root / "page_decisions.jsonl"
    if decisions_path.is_file():
        for line in decisions_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            ref = Path(row["receipt_ref"])
            if ref.is_absolute() or ".." in ref.parts:
                raise RefreshRunError(f"Unsafe receipt reference: {ref}")
            receipt_path = run_root / ref
            if not receipt_path.is_file():
                raise RefreshRunError(f"Missing resume receipt: {ref}")
            receipt_doc = yaml.safe_load(
                receipt_path.read_text(encoding="utf-8")
            ) or {}
            receipt = receipt_doc.get("content_refresh_receipt") or {}
            _add(row["page_path"], receipt.get("new_hash"))

    extra_path = _extra_allowed_hashes_path(run_root)
    if extra_path.is_file():
        try:
            extra = json.loads(extra_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            extra = {}
        for page_path, hashes in extra.items():
            for file_hash in hashes:
                _add(page_path, file_hash)

    conflicts = [
        display_path[key]
        for key, acceptable in allowed_hashes.items()
        if not acceptable
        or any(not isinstance(value, str) for value in acceptable)
        or _path_hash(display_path[key]) not in acceptable
    ]
    if conflicts:
        raise RefreshRunError(
            "Scoped working files changed outside a validated run checkpoint: "
            f"{sorted(conflicts)[:5]}"
        )


def _assert_run_evidence_ready(
    manifest: dict[str, Any],
    *,
    include_validation: bool = False,
    require_all_pass: bool = True,
    include_attempts: bool = True,
) -> list[dict[str, Any]]:
    """Recompute run-artifact integrity and require one all-PASS decision per page."""
    run_root = _run_root(
        manifest["family"], manifest["platform"], manifest["run_id"]
    )
    output_digests = manifest.get("output_digests") or {}
    required_artifacts = {
        "scope": run_root / "scope.json",
        "page_decisions": run_root / "page_decisions.jsonl",
    }
    if include_validation:
        required_artifacts["validation"] = run_root / "validation.json"
    mismatched = [
        name
        for name, path in required_artifacts.items()
        if output_digests.get(name) != _file_digest(path)
    ]

    receipts_root = run_root / "receipts"
    receipt_paths = sorted(receipts_root.glob("*.yaml"))
    receipts_digest = "sha256:" + hashlib.sha256(
        "\n".join(
            f"{path.name}:{_file_digest(path)}" for path in receipt_paths
        ).encode("utf-8")
    ).hexdigest()
    if output_digests.get("receipts") != receipts_digest:
        mismatched.append("receipts")
    if mismatched:
        raise RefreshRunError(
            "Run evidence digest mismatch or missing artifact: "
            f"{sorted(set(mismatched))}"
        )

    pinned_scope = _assert_pinned_scope(manifest)
    scope_paths = list(manifest.get("scope", {}).get("paths") or [])
    initial_hashes = pinned_scope.get("initial_hashes") or {}

    decisions_path = required_artifacts["page_decisions"]
    decision_rows: list[dict[str, Any]] = []
    referenced_receipts: set[str] = set()
    for line_number, line in enumerate(
        decisions_path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RefreshRunError(
                f"Invalid page decision JSON at line {line_number}: {exc}"
            ) from exc
        if row.get("run_id") != manifest["run_id"]:
            raise RefreshRunError(
                f"Wrong-run page decision at line {line_number}: "
                f"{row.get('run_id')!r}"
            )
        schema_errors = validate_refresh_page_decision(row)
        if schema_errors:
            raise RefreshRunError(
                f"Invalid page decision at line {line_number}: {schema_errors}"
            )
        validators = row.get("validator_results")
        if not isinstance(validators, dict) or not validators:
            raise RefreshRunError(
                f"Page decision has no validator results at line {line_number}"
            )
        not_pass = {
            name: value
            for name, value in validators.items()
            if value != "PASS"
        }
        if require_all_pass and not_pass:
            raise RefreshRunError(
                "Page decision is not commit-ready at line "
                f"{line_number}: {not_pass}"
            )
        receipt_ref = Path(str(row.get("receipt_ref") or ""))
        if (
            not receipt_ref.parts
            or receipt_ref.is_absolute()
            or ".." in receipt_ref.parts
        ):
            raise RefreshRunError(
                f"Unsafe page-decision receipt reference at line {line_number}"
            )
        receipt_path = run_root / receipt_ref
        if (
            not receipt_path.is_file()
            or row.get("receipt_digest") != _file_digest(receipt_path)
        ):
            raise RefreshRunError(
                f"Page-decision receipt digest mismatch at line {line_number}"
            )
        referenced_receipts.add(receipt_ref.as_posix())
        decision_rows.append(row)

    # See _reconcile_scope_and_decisions()'s docstring: batch_reference.py's
    # --update mode logs decisions (and, for GENERATED, sometimes writes)
    # beyond this run's pinned scope, and body_refresh.py has early-exit
    # paths that record no decision at all for a legitimate no-op scoped
    # page. An exact 1:1 count/set match is too strict; check the real
    # safety properties instead. A duplicate decision for the SAME in-scope
    # page is still a genuine integrity problem and remains a hard block.
    decision_paths = [str(row.get("page_path")) for row in decision_rows]
    real_missing, real_unexpected = _reconcile_scope_and_decisions(
        scope_paths,
        decision_rows,
        _augment_initial_hashes_with_extra_allowed(initial_hashes, run_root),
    )
    scoped_decision_paths = [p for p in decision_paths if p in set(scope_paths)]
    if (
        real_missing
        or real_unexpected
        or len(set(scoped_decision_paths)) != len(scoped_decision_paths)
    ):
        raise RefreshRunError(
            "Run evidence must contain exactly one decision per scoped page: "
            f"missing={real_missing[:5]}, unexpected={real_unexpected[:5]}"
        )
    actual_receipt_refs = {
        path.relative_to(run_root).as_posix() for path in receipt_paths
    }
    manifest_receipt_refs: set[str] = set()
    for value in manifest.get("receipt_refs") or []:
        ref = Path(str(value))
        if ref.is_absolute() or ".." in ref.parts:
            raise RefreshRunError(f"Unsafe manifest receipt reference: {value}")
        manifest_receipt_refs.add(ref.as_posix())
    expected_decision_ref = decisions_path.relative_to(_repo_root).as_posix()
    if (
        referenced_receipts != actual_receipt_refs
        or {
            (run_root / value).relative_to(_repo_root).as_posix()
            for value in referenced_receipts
        }
        != manifest_receipt_refs
        or manifest.get("page_decision_ref") != expected_decision_ref
    ):
        raise RefreshRunError(
            "Run evidence contains unbound or mismatched receipt/decision references"
        )

    def _checked_ref(value: Any, label: str) -> tuple[Path, str]:
        ref = Path(str(value or ""))
        if not ref.parts or ref.is_absolute() or ".." in ref.parts:
            raise RefreshRunError(f"Unsafe {label} reference: {value!r}")
        path = run_root / ref
        if not path.is_file():
            raise RefreshRunError(f"Missing {label} artifact: {ref.as_posix()}")
        return path, ref.as_posix()

    if include_attempts:
        stage_refs = list(manifest.get("stage_attempt_refs") or [])
        stage_digests = dict(manifest.get("stage_attempt_digests") or {})
        stage_ref_set = {
            _checked_ref(value, "stage attempt")[1] for value in stage_refs
        }
        actual_stage_refs = {
            path.relative_to(run_root).as_posix()
            for path in (run_root / "stages").glob("*.result.json")
        }
        if (
            len(stage_refs) != len(stage_ref_set)
            or stage_ref_set != actual_stage_refs
            or set(stage_digests) != stage_ref_set
        ):
            raise RefreshRunError(
                "Stage attempts contain duplicate, missing, or unbound result artifacts"
            )
        for value in stage_refs:
            result_path, _ = _checked_ref(value, "stage attempt")
            if stage_digests.get(str(value)) != _file_digest(result_path):
                raise RefreshRunError(f"Stage result digest mismatch: {value}")
            payload = json.loads(result_path.read_text(encoding="utf-8"))
            if payload.get("run_id") != manifest["run_id"]:
                raise RefreshRunError(f"Wrong-run stage attempt: {value}")
            for stream in ("stdout", "stderr"):
                log_path, _ = _checked_ref(
                    payload.get(f"{stream}_ref"), f"stage {stream}"
                )
                if payload.get(f"{stream}_digest") != _file_digest(log_path):
                    raise RefreshRunError(
                        f"Stage {stream} digest mismatch in {value}"
                    )

    if include_validation and include_attempts:
        validation_refs = list(manifest.get("validation_attempt_refs") or [])
        validation_digests = dict(
            manifest.get("validation_attempt_digests") or {}
        )
        validation_ref_set = {
            _checked_ref(value, "validation attempt")[1]
            for value in validation_refs
        }
        actual_validation_refs = {
            path.relative_to(run_root).as_posix()
            for path in (run_root / "validation").glob("attempt-*/result.json")
        }
        if (
            not validation_refs
            or len(validation_refs) != len(validation_ref_set)
            or validation_ref_set != actual_validation_refs
            or set(validation_digests) != validation_ref_set
        ):
            raise RefreshRunError(
                "Validation attempts contain duplicate, missing, or unbound results"
            )
        latest_path, _ = _checked_ref(
            validation_refs[-1], "latest validation attempt"
        )
        if _file_digest(latest_path) != _file_digest(
            required_artifacts["validation"]
        ):
            raise RefreshRunError(
                "Latest validation attempt does not match validation.json"
            )
        for value in validation_refs:
            result_path, _ = _checked_ref(value, "validation attempt")
            if validation_digests.get(str(value)) != _file_digest(result_path):
                raise RefreshRunError(
                    f"Validation result digest mismatch: {value}"
                )
            payload = json.loads(result_path.read_text(encoding="utf-8"))
            if payload.get("run_id") != manifest["run_id"]:
                raise RefreshRunError(f"Wrong-run validation attempt: {value}")
            details = payload.get("details")
            if not isinstance(details, dict):
                raise RefreshRunError(
                    f"Validation attempt has no details: {value}"
                )
            for field, detail in details.items():
                if not isinstance(detail, dict):
                    raise RefreshRunError(
                        f"Invalid validation detail {field!r} in {value}"
                    )
                for stream in ("stdout", "stderr"):
                    log_path, _ = _checked_ref(
                        detail.get(f"{stream}_ref"),
                        f"validation {field} {stream}",
                    )
                    if detail.get(f"{stream}_digest") != _file_digest(log_path):
                        raise RefreshRunError(
                            f"Validation {field} {stream} digest mismatch in {value}"
                        )
    return decision_rows


def _write_json(path: Path, data: dict[str, Any]) -> None:
    atomic_write(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def _event(
    family: str,
    platform: str,
    run_id: str,
    event_type: str,
    **fields: Any,
) -> None:
    path = _run_root(family, platform, run_id) / "events.jsonl"
    row = {"at": _utc(), "event": event_type, **fields}
    prior = path.read_text(encoding="utf-8") if path.is_file() else ""
    atomic_write(path, prior + json.dumps(row, ensure_ascii=False) + "\n")


def _load_manifest(family: str, platform: str, run_id: str) -> dict[str, Any]:
    path = _manifest_path(family, platform, run_id)
    if not path.is_file():
        raise RefreshRunError(f"Run not found: {family}/{platform}/{run_id}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RefreshRunError(f"Run manifest is unreadable: {exc}") from exc
    errors = validate_refresh_run_manifest(data)
    if errors:
        raise RefreshRunError(f"Run manifest is invalid: {errors}")
    return data


def _save_manifest(data: dict[str, Any]) -> None:
    data["updated_at"] = _utc()
    errors = validate_refresh_run_manifest(data)
    if errors:
        raise RefreshRunError(f"Refusing to write invalid run manifest: {errors}")
    _write_json(
        _manifest_path(data["family"], data["platform"], data["run_id"]),
        data,
    )


def _set_active(family: str, platform: str, run_id: str) -> None:
    _write_json(
        _active_path(family, platform),
        {"run_id": run_id, "updated_at": _utc()},
    )


def _clear_active(family: str, platform: str, run_id: str) -> None:
    path = _active_path(family, platform)
    if not path.is_file():
        return
    try:
        active = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    if active.get("run_id") == run_id:
        path.unlink(missing_ok=True)


def _assert_active(family: str, platform: str, run_id: str) -> None:
    path = _active_path(family, platform)
    if not path.is_file():
        raise RefreshRunError(f"No active refresh is registered for {family}/{platform}")
    try:
        active = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RefreshRunError(f"Active-run pointer is unreadable: {exc}") from exc
    if active.get("run_id") != run_id:
        raise RefreshRunError(
            f"Run {run_id} is not active; active run is {active.get('run_id')!r}"
        )


def _transition(
    manifest: dict[str, Any],
    target: str,
    *,
    checkpoint: str | None = None,
) -> None:
    current = manifest["state"]
    if target not in NEXT_STATES.get(current, set()):
        raise RefreshRunError(f"Illegal refresh-run transition: {current} -> {target}")
    manifest["state"] = target
    if checkpoint:
        manifest.setdefault("stage_checkpoints", {})[checkpoint] = {
            "state": target,
            "completed_at": _utc(),
        }
    _save_manifest(manifest)
    _event(
        manifest["family"],
        manifest["platform"],
        manifest["run_id"],
        "STATE_TRANSITION",
        previous=current,
        current=target,
        checkpoint=checkpoint,
    )


def _transition_abandoned(
    manifest: dict[str, Any],
    *,
    reason: str,
    checkpoint: str | None = None,
) -> None:
    """Enter ABANDONED with its phase-required reason in one manifest write."""
    current = manifest["state"]
    if "ABANDONED" not in NEXT_STATES.get(current, set()):
        raise RefreshRunError(
            f"Illegal refresh-run transition: {current} -> ABANDONED"
        )
    manifest["state"] = "ABANDONED"
    manifest["resume_state"] = None
    manifest["failure_reason"] = _redact_artifact_text(reason.strip())
    if checkpoint:
        manifest.setdefault("stage_checkpoints", {})[checkpoint] = {
            "state": "ABANDONED",
            "completed_at": _utc(),
        }
    _save_manifest(manifest)
    _event(
        manifest["family"],
        manifest["platform"],
        manifest["run_id"],
        "STATE_TRANSITION",
        previous=current,
        current="ABANDONED",
        checkpoint=checkpoint,
    )


def create_run(
    family: str,
    platform: str,
    *,
    mode: str,
    scope_manifest: str | None = None,
    run_id: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Create and input-pin a new run; returns its validated manifest."""
    family = _safe_token(family, "family")
    platform = _safe_token(platform, "platform")
    if mode not in MODES:
        raise RefreshRunError(f"mode must be one of {sorted(MODES)}")
    owner = _session_id(session_id)
    rid = _safe_token(
        run_id or f"rf-{_now().strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:12]}",
        "run_id",
    )
    scope_ref, input_digest = _scope_manifest(scope_manifest, mode)
    existing_ids = list(
        (_reports_root / "refresh_runs").glob(f"*/*/{rid}/manifest.json")
    )
    if existing_ids:
        raise RefreshRunError(f"Run ID already exists: {rid}")

    with _product_guard(family, platform):
        active_path = _active_path(family, platform)
        if active_path.is_file():
            try:
                active = json.loads(active_path.read_text(encoding="utf-8"))
                active_id = active.get("run_id")
                prior = _load_manifest(family, platform, active_id)
            except Exception as exc:
                raise RefreshRunError(
                    f"Existing active-run pointer is invalid and must be investigated: {exc}"
                ) from exc
            if prior.get("state") not in TERMINAL_STATES:
                raise RefreshRunError(
                    f"{family}/{platform} already has active run {active_id} "
                    f"in state {prior.get('state')}"
                )
            _clear_active(family, platform, active_id)

        run_root = _run_root(family, platform, rid)
        if run_root.exists():
            raise RefreshRunError(f"Run ID already exists: {rid}")

        head = _head_sha()
        model = _model_state(family, platform)
        model_sha = model["repo_sha"]
        source_sha = _source_sha(family, platform)
        if mode == "remediation" and model_sha != source_sha:
            raise RefreshRunError(
                f"remediation requires current knowledge: model={model_sha}, source={source_sha}"
            )

        run_root.mkdir(parents=True)
        created = _utc()
        manifest: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "run_id": rid,
            "family": family,
            "platform": platform,
            "mode": mode,
            "state": "CREATED",
            "session_owner": owner,
            "created_at": created,
            "updated_at": created,
            "base_commit_sha": head,
            "initial_model_sha": model_sha,
            "initial_source_sha": source_sha,
            "target_model_sha": None,
            "target_source_sha": None,
            "scope": {
                "manifest_ref": scope_ref,
                "input_digest": input_digest,
                "digest": None,
                "paths": [],
            },
            "stage_checkpoints": {},
            "stage_attempt_refs": [],
            "stage_attempt_digests": {},
            "validation_attempt_refs": [],
            "validation_attempt_digests": {},
            "validation": {field: "NOT_RUN" for field in VALIDATION_FIELDS},
            "observed_heads": [head],
            "input_digests": {
                "model_yaml": _file_digest(
                    _repo_root
                    / "knowledge"
                    / family
                    / platform
                    / "merged"
                    / "model.yaml"
                ),
                "scope_manifest": input_digest,
            },
            "output_digests": {},
            "receipt_refs": [],
            "page_decision_ref": None,
            "commit_sha": None,
            "failure_reason": None,
        }
        _save_manifest(manifest)
        _event(family, platform, rid, "RUN_CREATED", mode=mode, owner=owner)
        _set_active(family, platform, rid)
        _transition(manifest, "INPUTS_PINNED", checkpoint="inputs_pinned")
        return manifest


def _command(args: list[str], *, timeout: int = 1800) -> subprocess.CompletedProcess[str]:
    result = _command_runner(
        args,
        cwd=str(_repo_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    return result


def _redact_artifact_text(value: str) -> str:
    """Remove workstation paths and common inline secret assignments."""
    text = str(value)
    replacements = (
        (str(_repo_root), "<repo-root>"),
        (_repo_root.as_posix(), "<repo-root>"),
        (str(Path.home()), "<user-home>"),
        (Path.home().as_posix(), "<user-home>"),
    )
    for raw, replacement in replacements:
        if raw:
            text = text.replace(raw, replacement)
    return re.sub(
        r"(?i)\b(api[_-]?key|token|secret|password)=\S+",
        r"\1=<redacted>",
        text,
    )


def _result_counters(stdout: str, stderr: str) -> dict[str, int]:
    counters = {"warnings": 0, "errors": 0, "skips": 0}
    structured = re.compile(
        r"^\s*(warnings?|errors?|fails?|failed|skips?|skipped)"
        r"\s*[:=]\s*(\d+)\b",
        re.IGNORECASE,
    )
    explicit = re.compile(
        r"^\s*(warning|warn|error|fail|failed|skip|skipped)"
        r"\b(?:\s*[:\-]|\s+)",
        re.IGNORECASE,
    )
    for line in "\n".join((stdout or "", stderr or "")).splitlines():
        match = structured.match(line)
        if match:
            label, value = match.group(1).lower(), int(match.group(2))
        else:
            match = explicit.match(line)
            if not match:
                continue
            label, value = match.group(1).lower(), 1
        if label.startswith("warn"):
            counters["warnings"] += value
        elif label.startswith(("error", "fail")):
            counters["errors"] += value
        else:
            counters["skips"] += value
    return counters


def _write_stage_attempt(
    manifest: dict[str, Any],
    *,
    label: str,
    args: list[str],
    started_at: str,
    result: subprocess.CompletedProcess[str] | None = None,
    exception: BaseException | None = None,
) -> str:
    """Atomically persist one immutable planning/writer command attempt."""
    family, platform, rid = (
        manifest["family"],
        manifest["platform"],
        manifest["run_id"],
    )
    stage_root = _run_root(family, platform, rid) / "stages"
    stage_root.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-") or "stage"
    attempts = []
    for path in stage_root.glob(f"{slug}-*.*"):
        match = re.match(rf"{re.escape(slug)}-(\d+)\.", path.name)
        if match:
            attempts.append(int(match.group(1)))
    attempt = max(attempts, default=0) + 1
    stem = f"{slug}-{attempt:02d}"
    stdout = _redact_artifact_text((result.stdout if result else "") or "")
    stderr = _redact_artifact_text((result.stderr if result else "") or "")
    if exception is not None:
        stderr = "\n".join(
            part for part in (stderr, f"{type(exception).__name__}: {exception}") if part
        )
        stderr = _redact_artifact_text(stderr)
    stdout_path = stage_root / f"{stem}.stdout.log"
    stderr_path = stage_root / f"{stem}.stderr.log"
    result_path = stage_root / f"{stem}.result.json"
    atomic_write(stdout_path, stdout)
    atomic_write(stderr_path, stderr)
    counters = _result_counters(stdout, stderr)
    payload = {
        "schema_version": 1,
        "run_id": rid,
        "stage": label,
        "attempt": attempt,
        "retry_count": attempt - 1,
        "command": [_redact_artifact_text(arg) for arg in args],
        "started_at": started_at,
        "completed_at": _utc(),
        "status": (
            "ERROR" if exception is not None
            else "PASS" if result and result.returncode == 0
            else "FAIL"
        ),
        "exit_code": result.returncode if result is not None else None,
        "stdout_ref": stdout_path.relative_to(
            _run_root(family, platform, rid)
        ).as_posix(),
        "stderr_ref": stderr_path.relative_to(
            _run_root(family, platform, rid)
        ).as_posix(),
        "stdout_digest": _file_digest(stdout_path),
        "stderr_digest": _file_digest(stderr_path),
        **counters,
    }
    _write_json(result_path, payload)
    result_ref = result_path.relative_to(
        _run_root(family, platform, rid)
    ).as_posix()
    _event(
        family,
        platform,
        rid,
        "STAGE_RESULT",
        stage=label,
        attempt=attempt,
        result=payload["status"],
        exit_code=payload["exit_code"],
        result_ref=result_ref,
        warnings=counters["warnings"],
        errors=counters["errors"],
        skips=counters["skips"],
    )
    return result_ref


def _require_command(
    args: list[str],
    label: str,
    *,
    manifest: dict[str, Any] | None = None,
    timeout: int = 1800,
) -> None:
    started_at = _utc()
    try:
        result = _command(args, timeout=timeout)
    except Exception as exc:
        if manifest is not None:
            result_ref = _write_stage_attempt(
                manifest,
                label=label,
                args=args,
                started_at=started_at,
                exception=exc,
            )
            manifest.setdefault("stage_attempt_refs", []).append(result_ref)
            manifest.setdefault("stage_attempt_digests", {})[result_ref] = (
                _file_digest(
                    _run_root(
                        manifest["family"],
                        manifest["platform"],
                        manifest["run_id"],
                    )
                    / result_ref
                )
            )
            _save_manifest(manifest)
        raise RefreshRunError(
            f"{label} raised {type(exc).__name__}: "
            f"{_redact_artifact_text(str(exc))}"
        ) from exc
    if manifest is not None:
        result_ref = _write_stage_attempt(
            manifest,
            label=label,
            args=args,
            started_at=started_at,
            result=result,
        )
        manifest.setdefault("stage_attempt_refs", []).append(result_ref)
        manifest.setdefault("stage_attempt_digests", {})[result_ref] = (
            _file_digest(
                _run_root(
                    manifest["family"],
                    manifest["platform"],
                    manifest["run_id"],
                )
                / result_ref
            )
        )
        _save_manifest(manifest)
    if result.returncode != 0:
        detail = _redact_artifact_text(
            (result.stderr or result.stdout).strip()
        )
        raise RefreshRunError(f"{label} failed ({result.returncode}): {detail}")


def _paths_from_pia(path: Path) -> list[str]:
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("pages", [])
    if isinstance(rows, dict):
        iterable = [
            {"page_path": page_path, **(entry if isinstance(entry, dict) else {})}
            for page_path, entry in rows.items()
        ]
    elif isinstance(rows, list):
        iterable = rows
    else:
        return []
    selected = []
    for row in iterable:
        if not isinstance(row, dict):
            continue
        # page_impact_assess.py's real, documented output field is "pia_score"
        # (see its own module comment: "_paths_from_pia() in refresh_run.py
        # filters on pia_score"). The legacy alias names below never appear in
        # real PIA output -- kept only as a defensive fallback for any other
        # caller that might use a different schema, not because PIA itself
        # emits them.
        impact = (
            row.get("pia_score")
            or row.get("impact")
            or row.get("impact_level")
            or row.get("classification")
        )
        path_value = row.get("page_path") or row.get("path")
        if impact in {"HIGH_IMPACT", "MEDIUM_IMPACT"} and isinstance(path_value, str):
            selected.append(Path(path_value).as_posix())
    return sorted(set(selected))


_KNOWLEDGE_DELTA_LIST_FIELDS = (
    "new_claims", "removed_claims", "modified_claims",
    "new_apis", "removed_apis", "modified_apis", "resurrected_apis",
)


def _knowledge_delta_is_real(delta_path: Path) -> bool:
    """Task 6 (S9.6): a real, non-empty release delta -- at least one of
    knowledge_delta.json's 7 change lists is non-empty -- vs. a no-op sync
    (repo_sha advanced with zero actual API/claim change, which produces no
    announcement, per S9.6's own scoping). Fails open (False, no announcement
    forced) on any read error -- this is a same-run gate the caller already
    knows the file exists for (see the is_file() check just above its call
    site), not an independent existence check."""
    try:
        data = json.loads(delta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    if not isinstance(data, dict):
        return False
    return any(data.get(field) for field in _KNOWLEDGE_DELTA_LIST_FIELDS)


def _discover_fact_pack(family: str, platform: str) -> "dict[str, Any] | None":
    """Task 4 (S9.2, reconciles F3/F9): search reports/handoff/*/fact-pack.json
    for one matching this product's family/platform. Fact packs live under a
    mission-ID-named directory (e.g. reports/handoff/MT036-2026-08-21-PDF-JAVA-
    MAVEN-PUBLISH-HARDENING/), not a predictable {family}/{platform} path -- so
    this is a search, not a direct path construction (confirmed: no canonical
    pointer file exists yet; recommended to the publishing lane as a future
    convenience, not implemented here). When more than one fact pack matches
    (multiple releases over time), the most recently modified file wins.
    """
    handoff_root = _repo_root / "reports" / "handoff"
    if not handoff_root.is_dir():
        return None
    candidates = []
    for path in handoff_root.glob("*/fact-pack.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        product = data.get("product", {})
        if product.get("family") == family and product.get("platform") == platform:
            candidates.append((path.stat().st_mtime, path, data))
    if not candidates:
        return None
    candidates.sort(key=lambda c: c[0])
    _mtime, path, data = candidates[-1]
    data["_fact_pack_path"] = str(path.relative_to(_repo_root).as_posix())
    return data


def _load_package_registry_candidate(family: str, platform: str) -> "dict[str, Any] | None":
    registry_path = _repo_root / "data" / "package_registry.json"
    if not registry_path.is_file():
        return None
    try:
        data = json.loads(registry_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    entry = data.get(family, {}).get(platform) if isinstance(data.get(family), dict) else None
    if not isinstance(entry, dict):
        return None
    return entry.get("candidate")


def _reconcile_fact_pack_with_registry(
    fact_pack: dict[str, Any], family: str, platform: str,
) -> list[str]:
    """F9's mechanical fix: a fact pack's version/maven coordinates must agree
    with data/package_registry.json's current candidate -- this is exactly
    the class of drift that let pdf/java render a stale Maven version in
    production for a day after its real 26.8.0 republish (F9). Returns a list
    of human-readable mismatch descriptions; empty means agreement (or the
    registry has no entry at all yet, which is a separate, non-fact-pack
    concern this check does not itself raise on -- registry population is
    /repo-scout's job, not this run's)."""
    candidate = _load_package_registry_candidate(family, platform)
    if candidate is None:
        return []

    mismatches = []
    fp_version = fact_pack.get("version", {}).get("new")
    if fp_version and candidate.get("version") and fp_version != candidate.get("version"):
        mismatches.append(
            f"version: fact pack says '{fp_version}', "
            f"package_registry.json candidate says '{candidate.get('version')}'"
        )
    fp_maven = fact_pack.get("maven", {})
    for field in ("group_id", "artifact_id"):
        fp_value = fp_maven.get(field)
        reg_value = candidate.get(field)
        if fp_value and reg_value and fp_value != reg_value:
            mismatches.append(
                f"maven.{field}: fact pack says '{fp_value}', "
                f"package_registry.json candidate says '{reg_value}'"
            )
    return mismatches


def prepare_run(manifest: dict[str, Any]) -> dict[str, Any]:
    """Refresh/revalidate inputs and create the immutable run scope."""
    family, platform, rid = (
        manifest["family"],
        manifest["platform"],
        manifest["run_id"],
    )
    if manifest["state"] != "INPUTS_PINNED":
        raise RefreshRunError(
            f"prepare requires INPUTS_PINNED, got {manifest['state']}"
        )

    # Release fact-pack read (Task 4, S9.2, reconciles F3/F9) -- deliberately
    # first, before the heavier knowledge-refresh subprocess below: this is an
    # input-validation step, and a real coordinate mismatch here should fail
    # fast rather than after an expensive knowledge refresh has already run.
    # Fallback when no fact pack exists for this product yet: proceed with no
    # fact pack at all (documented, not blocking) -- callers needing release
    # facts before a real fact pack has been delivered fall back to
    # live-assembly from package_registry.json directly (data/package_registry.json's
    # own candidate.* fields), which prepare_run already reads for
    # reconciliation regardless of whether a fact pack was found.
    fact_pack = _discover_fact_pack(family, platform)
    if fact_pack is not None:
        mismatches = _reconcile_fact_pack_with_registry(fact_pack, family, platform)
        if mismatches:
            raise RefreshRunError(
                f"Release fact pack ({fact_pack.get('_fact_pack_path')}) disagrees "
                f"with data/package_registry.json's current candidate: "
                f"{'; '.join(mismatches)}. Reconcile package_registry.json (or the "
                f"fact pack, if it's the one that's actually stale) before "
                f"proceeding -- this is exactly the class of drift F9 found live "
                f"in production."
            )
        manifest["fact_pack_ref"] = fact_pack.get("_fact_pack_path")
    else:
        manifest["fact_pack_ref"] = None

    python = sys.executable
    post_kr_snapshot: dict[str, str] = {}
    if manifest["mode"] in {"upstream", "combined"}:
        _require_command(
            [
                python,
                str(
                    _repo_root
                    / "scripts/pipeline/commands/knowledge/refresh_knowledge.py"
                ),
                family,
                platform,
                "--compulsory-enrich",
            ],
            "knowledge refresh",
            manifest=manifest,
        )
        # Knowledge refresh's own attach_evidence.py sub-step legitimately
        # rewrites working-tree content pages (evidence.model_sha bumps)
        # *before* scope is even known -- scope is only computed later, from
        # this same refresh's PIA output. Snapshot which pages are dirty
        # right now (and their exact bytes) so the "clean scoped base" check
        # below can tell "already touched by this run's own knowledge
        # refresh" apart from "touched by something else after knowledge
        # refresh finished". Found live (MT014-2026-07-29-PDF-GO-REDO):
        # comparing scoped pages directly against base_commit_sha made
        # every real combined/upstream run block on its own legitimate
        # evidence-refresh output, unconditionally -- no combined/upstream
        # run has ever completed prepare_run() as a result (the one prior
        # attempt on record, cells/go's mt011-cells-go-ref, was left
        # BLOCKED at an earlier step and never resumed past it).
        post_kr_diff = _command_runner(
            ["git", "diff", "--name-only", manifest["base_commit_sha"]],
            cwd=str(_repo_root),
            capture_output=True,
            text=True,
            timeout=30,
        )
        post_kr_snapshot = {
            line.strip(): _path_hash(line.strip())
            for line in post_kr_diff.stdout.splitlines()
            if line.strip()
        }

    model = _model_state(family, platform)
    source_sha = _source_sha(family, platform)
    if model["repo_sha"] != source_sha:
        raise RefreshRunError(
            f"Knowledge/source SHA mismatch after preparation: "
            f"model={model['repo_sha']}, source={source_sha}"
        )

    delta = (
        _repo_root
        / "knowledge"
        / family
        / platform
        / "merged"
        / "knowledge_delta.json"
    )
    if manifest["mode"] in {"upstream", "combined"}:
        if not delta.is_file():
            raise RefreshRunError(
                "upstream/combined run has no knowledge_delta.json after knowledge refresh"
            )
        # Task 6 (S9.6, corrected 2026-08-23 -- see the plan's own note on why
        # /new-blog-post cannot be invoked from here directly): a deterministic
        # signal only. This run's own agent-facing workflow (the new
        # blog-release-check skill, S-124) is what actually directs a human/
        # agent to draft the announcement via /new-blog-post -- prepare_run
        # itself only records whether a real (non-empty) delta exists, since
        # that's the one part of this decision that's genuinely mechanical.
        manifest["blog_announcement_required"] = _knowledge_delta_is_real(delta)
        _require_command(
            [
                python,
                str(_repo_root / "scripts/pipeline/commands/launch/site_planner.py"),
                family,
                platform,
                "--mode",
                "update",
            ],
            "delta site planning",
            manifest=manifest,
        )

    run_root = _run_root(family, platform, rid)
    planning_root = run_root / "planning"
    planning_product = planning_root / family / platform
    planning_product.mkdir(parents=True, exist_ok=True)
    if delta.is_file():
        _require_command(
            [
                python,
                str(
                    _repo_root
                    / "scripts/pipeline/commands/knowledge/semantic_diff.py"
                ),
                family,
                platform,
                "--output",
                str(planning_product / "semantic_changes.json"),
            ],
            "run-scoped semantic diff",
            manifest=manifest,
        )
        _require_command(
            [
                python,
                str(
                    _repo_root
                    / "scripts/pipeline/commands/content/claim_parser.py"
                ),
                family,
                platform,
                "--all-pages",
                "--output",
                str(planning_product / "claim_maps"),
            ],
            "run-scoped claim parsing",
            manifest=manifest,
        )
        _require_command(
            [
                python,
                str(
                    _repo_root
                    / "scripts/pipeline/commands/content/body_impact.py"
                ),
                family,
                platform,
                "--reports-root",
                str(planning_root),
            ],
            "run-scoped body impact",
            manifest=manifest,
        )
        _require_command(
            [
                python,
                str(
                    _repo_root
                    / "scripts/pipeline/commands/ops/page_impact_assess.py"
                ),
                family,
                platform,
                "--output-dir",
                str(planning_product),
                "--require-delta",
            ],
            "page impact assessment",
            manifest=manifest,
        )

    scope_ref = manifest.get("scope", {}).get("manifest_ref")
    expected_scope_input = manifest.get("scope", {}).get("input_digest")
    if scope_ref and _file_digest(_repo_root / scope_ref) != expected_scope_input:
        raise RefreshRunError("Scope manifest changed after INPUTS_PINNED")
    explicit_scope_paths = _scope_paths_from_file(scope_ref)
    pia_scope_paths = _paths_from_pia(planning_product / "page_impact.json")
    if manifest["mode"] == "remediation":
        # A remediation run is an explicit, operator-pinned truth-audit scope.
        # Historical PIA output may inform planning, but must never broaden the
        # paths authorized by the supplied scope manifest.
        scope_paths = explicit_scope_paths
    elif manifest["mode"] == "combined":
        scope_paths = sorted(set(explicit_scope_paths + pia_scope_paths))
    else:
        scope_paths = pia_scope_paths
    if not scope_paths:
        raise RefreshRunError("Refresh scope resolved to zero pages")
    _assert_product_scope(scope_paths, family, platform)

    dirty_scope: list[str] = []
    for relative_path in scope_paths:
        current_path = _repo_root / relative_path
        if relative_path in post_kr_snapshot:
            # Already dirty immediately after this run's own knowledge
            # refresh -- only block if something ELSE has touched it since
            # (bytes no longer match that post-refresh snapshot).
            clean = _path_hash(relative_path) == post_kr_snapshot[relative_path]
        else:
            base_has_path = _command_runner(
                [
                    "git",
                    "cat-file",
                    "-e",
                    f"{manifest['base_commit_sha']}:{relative_path}",
                ],
                cwd=str(_repo_root),
                capture_output=True,
                text=True,
                timeout=30,
            ).returncode == 0
            if base_has_path:
                clean = _command_runner(
                    [
                        "git",
                        "diff",
                        "--quiet",
                        manifest["base_commit_sha"],
                        "--",
                        relative_path,
                    ],
                    cwd=str(_repo_root),
                    capture_output=True,
                    text=True,
                    timeout=30,
                ).returncode == 0
            else:
                clean = not current_path.exists()
        if not clean:
            dirty_scope.append(relative_path)
    if dirty_scope:
        raise RefreshRunError(
            "Refresh requires a clean scoped base; pre-existing changes found: "
            f"{dirty_scope[:5]}"
        )
    scope = {
        "schema_version": 1,
        "run_id": rid,
        "family": family,
        "platform": platform,
        "paths": scope_paths,
        "initial_hashes": {
            path: _path_hash(path) for path in scope_paths
        },
        "source": {
            "scope_manifest": manifest.get("scope", {}).get("manifest_ref"),
            "page_impact": (
                (planning_product / "page_impact.json").relative_to(_repo_root).as_posix()
                if (planning_product / "page_impact.json").is_file()
                else None
            ),
        },
    }
    scope_path = run_root / "scope.json"
    _write_json(scope_path, scope)

    manifest["target_model_sha"] = model["repo_sha"]
    manifest["target_source_sha"] = source_sha
    manifest["scope"]["paths"] = scope_paths
    manifest["scope"]["digest"] = _scope_digest(
        scope_paths, manifest["scope"].get("input_digest")
    )
    manifest["scope"]["resolved_ref"] = (
        scope_path
    ).relative_to(_repo_root).as_posix()
    manifest["input_digests"]["knowledge_delta"] = (
        _file_digest(delta) if delta.is_file() else None
    )
    manifest["output_digests"]["scope"] = _file_digest(scope_path)
    _transition(manifest, "PLANNED", checkpoint="planning_complete")
    return manifest


def _head_scope_conflicts(manifest: dict[str, Any]) -> list[str]:
    observed = manifest.get("observed_heads") or []
    prior = observed[-1] if observed else manifest["base_commit_sha"]
    current = _head_sha()
    if current == prior:
        return []
    manifest.setdefault("observed_heads", []).append(current)
    paths = manifest.get("scope", {}).get("paths") or []
    if not paths:
        _save_manifest(manifest)
        return []
    try:
        changed = _git("diff", "--name-only", f"{prior}..{current}", "--", *paths)
    except RefreshRunError:
        return paths
    _save_manifest(manifest)
    return [p for p in changed.splitlines() if p.strip()]


def apply_run(manifest: dict[str, Any]) -> dict[str, Any]:
    """Execute the refresh writers under the run-bound contract: body_refresh.py
    (non-reference scope), batch_reference.py (reference scope), and -- TC12,
    2026-08-21 -- backlink_backfill.py's all-5-subdomain reconciliation pass.
    """
    if manifest["state"] != "PLANNED":
        raise RefreshRunError(f"apply requires PLANNED, got {manifest['state']}")
    conflicts = _head_scope_conflicts(manifest)
    if conflicts:
        raise RefreshRunError(
            f"HEAD moved across {len(conflicts)} in-scope path(s): {conflicts[:3]}"
        )
    _assert_scope_ownership(manifest)
    _transition(manifest, "APPLYING", checkpoint="apply_started")

    family, platform, rid = (
        manifest["family"],
        manifest["platform"],
        manifest["run_id"],
    )
    run_root = _run_root(family, platform, rid)
    python = sys.executable
    scope_paths = manifest.get("scope", {}).get("paths") or []
    body_scope = [
        path for path in scope_paths if "reference.aspose.org/" not in path
    ]
    reference_scope = [
        path for path in scope_paths if "reference.aspose.org/" in path
    ]
    body_impact = run_root / "planning" / family / platform / "body_impact.json"
    if body_scope:
        if not body_impact.is_file():
            raise RefreshRunError(
                "Non-reference remediation scope has no run-scoped body-impact "
                "evidence; derive current truth findings before mutation"
            )
        _assert_pinned_scope(manifest)
        _require_command(
            [
                python,
                str(_repo_root / "scripts/pipeline/commands/content/body_refresh.py"),
                family,
                platform,
                "--execute",
                "--run-id",
                rid,
                "--run-root",
                str(run_root),
            ],
            "body refresh",
            manifest=manifest,
        )
    if reference_scope:
        # Two-step regeneration rule (mandatory when removed_apis > 0):
        # an --update-only pass only regenerates pages for classes in
        # modified_apis, so reference pages for OTHER, unmodified classes
        # can retain phantom members that were only removed as a
        # side-effect of the deleted classes (proven on pdf/java
        # Rectangle.md, 2026-06-12). Prior to this fix, only
        # mode=="remediation" ever triggered --rebuild-all; a plain
        # upstream/combined refresh with real removals silently skipped
        # it (found live during 3D-PYTHON-REFRESH-001, 2026-08-01).
        removed_apis_count = 0
        delta_path = (
            _repo_root / "knowledge" / family / platform / "merged" / "knowledge_delta.json"
        )
        if delta_path.is_file():
            try:
                removed_apis_count = len(
                    json.loads(delta_path.read_text(encoding="utf-8")).get("removed_apis") or []
                )
            except (OSError, ValueError):
                removed_apis_count = 0
        reference_mode = (
            ["--rebuild-all", "--confirm-rebuild"]
            if manifest["mode"] == "remediation" or removed_apis_count > 0
            else ["--update"]
        )
        _assert_pinned_scope(manifest)
        _require_command(
            [
                python,
                str(
                    _repo_root
                    / "scripts/pipeline/commands/content/batch_reference.py"
                ),
                family,
                platform,
                *reference_mode,
                "--run-id",
                rid,
                "--run-root",
                str(run_root),
            ],
            "reference refresh",
            manifest=manifest,
        )

    receipts = sorted((run_root / "receipts").glob("*.yaml"))
    decisions = run_root / "page_decisions.jsonl"
    if not decisions.is_file():
        raise RefreshRunError("Writers produced no run-scoped page decision ledger")
    decision_rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        decisions.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RefreshRunError(
                f"Invalid page decision JSON at line {line_number}: {exc}"
            ) from exc
        if row.get("run_id") != rid:
            raise RefreshRunError(
                f"Wrong-run page decision at line {line_number}: "
                f"{row.get('run_id')!r}"
            )
        decision_rows.append(row)
    scope_paths_list = list(manifest.get("scope", {}).get("paths") or [])
    initial_hashes = _assert_pinned_scope(manifest).get("initial_hashes") or {}
    real_missing, real_unexpected = _reconcile_scope_and_decisions(
        scope_paths_list, decision_rows, initial_hashes
    )
    if real_missing or real_unexpected:
        raise RefreshRunError(
            "Run decision/scope reconciliation failed: "
            f"missing={real_missing[:5]}, unexpected={real_unexpected[:5]}"
        )
    blocked = [
        row.get("page_path")
        for row in decision_rows
        if row.get("disposition") == "BLOCKED"
    ]
    if blocked:
        raise RefreshRunError(
            f"{len(blocked)} scoped page decision(s) are BLOCKED: {blocked[:5]}"
        )

    # TC-DUPIDX-02 (2026-08-12, ST-059): version-gated reference-index re-invocation. Runs as
    # an independent step, deliberately AFTER scope/decision reconciliation above (not folded
    # into the "reference refresh" _require_command call) -- generate_grouped_index() (invoked
    # via --generate-index) writes no page_decisions.jsonl row, so folding it into the pinned
    # scope would make _reconcile_scope_and_decisions() see a phantom missing/unexpected entry
    # for _index.md. This closes the gap that let the GI-01 disambiguation fix (362430210c,
    # 2026-06-20) sit unapplied on 9 already-published pages indefinitely: nothing in the
    # routine refresh path ever re-derived an already-grouped index from current generator
    # logic, only from current knowledge data (is_stale_grouped_index, a separate axis).
    if reference_scope:
        index_path = (
            _repo_root / "content" / "reference.aspose.org" / "en" / family / platform
            / "_index.md"
        )
        if index_path.is_file() and not is_manually_curated(index_path):
            if index_generator_version_is_stale(read_provenance(index_path)):
                _require_command(
                    [
                        python,
                        str(
                            _repo_root
                            / "scripts/pipeline/commands/content/batch_reference.py"
                        ),
                        family,
                        platform,
                        "--generate-index",
                    ],
                    "reference index generator-version re-invocation",
                    manifest=manifest,
                )
                # This write emits no page_decisions.jsonl row (see the
                # TC-DUPIDX-02 comment above) -- authorize its resulting hash
                # so the later _assert_scope_ownership() OCC check in
                # verify_run() does not block on its own deliberate write.
                index_rel = index_path.relative_to(_repo_root).as_posix()
                _record_extra_allowed_hash(run_root, index_rel, _path_hash(index_rel))

    # TC12 (2026-08-21, backlink-governance-redesign): backlink reconciliation
    # writer step, covering all 5 subdomains -- not just reference.aspose.org's
    # side effect via batch_reference.py's own content generation above. Before
    # this, refresh-product (the skill explicitly built to run repeatedly
    # against an already-launched product) never revisited a page's aspose.com
    # backlink outside reference.aspose.org: whatever state it had before the
    # refresh, it still had after, even if wrong. Runs LAST (after both
    # writers and the index step) for two reasons: (1) body_refresh.py's
    # RG-010 guard + _PROTECTED_SECTION_IDS mean it only ever PRESERVES an
    # existing See-Also/Related-Resources link, never corrects one -- so
    # nothing it does conflicts with a later backlink write; (2) running
    # reconciliation before body_refresh.py would change page content ahead
    # of its own pre-write hash validation against body_impact.json's
    # PLANNED-time snapshot, spuriously triggering VD_SKIPPED_HASH. Scoped by
    # family/platform across all 5 subdomains (not the narrower pinned
    # scope_paths) -- deliberately broader than this run's content-diff scope,
    # since a page can carry a stale/wrong backlink even when its own
    # knowledge-derived content diff is empty; that gap is exactly what this
    # step exists to close. Like the TC-DUPIDX-02 index step above, this
    # writer emits no page_decisions.jsonl row, so every file it actually
    # modifies must be registered via _record_extra_allowed_hash() or the
    # later OCC guard in verify_run() would block on its own deliberate write.
    backlink_manifest_path = run_root / "backlink_reconciliation.json"
    _require_command(
        [
            python,
            str(_repo_root / "scripts/pipeline/commands/ops/backlink_backfill.py"),
            "--write",
            "--family", family,
            "--platform", platform,
            "--output", str(backlink_manifest_path),
        ],
        "backlink reconciliation",
        manifest=manifest,
    )
    # _require_command() only raises on a nonzero subprocess exit --
    # backlink_backfill.py's own main() always returns 0 even when its
    # manifest.errors is non-empty (confirmed: only a fatal target-map load
    # failure exits nonzero), so per-page failures must be checked explicitly.
    if not backlink_manifest_path.is_file():
        raise RefreshRunError(
            "backlink reconciliation produced no output manifest"
        )
    try:
        backlink_result = json.loads(backlink_manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RefreshRunError(
            f"backlink reconciliation manifest is not valid JSON: {exc}"
        ) from exc
    if backlink_result.get("total_errors"):
        raise RefreshRunError(
            f"backlink reconciliation reported {backlink_result['total_errors']} "
            f"page error(s): {backlink_result.get('errors', [])[:5]}"
        )
    for change in backlink_result.get("changes", []):
        if change.get("skipped"):
            continue
        change_rel = change["file"]
        _record_extra_allowed_hash(run_root, change_rel, _path_hash(change_rel))

    manifest["receipt_refs"] = [
        path.relative_to(_repo_root).as_posix() for path in receipts
    ]
    manifest["page_decision_ref"] = decisions.relative_to(_repo_root).as_posix()
    manifest["output_digests"]["page_decisions"] = _file_digest(decisions)
    manifest["output_digests"]["receipts"] = "sha256:" + hashlib.sha256(
        "\n".join(
            f"{path.name}:{_file_digest(path)}" for path in receipts
        ).encode("utf-8")
    ).hexdigest()
    _transition(manifest, "VALIDATING", checkpoint="apply_complete")
    return manifest


def verify_run(manifest: dict[str, Any]) -> dict[str, Any]:
    """Execute the blocking validators and move to READY_TO_COMMIT on all PASS."""
    if manifest["state"] not in {"VALIDATING", "READY_TO_COMMIT"}:
        raise RefreshRunError(
            f"verify requires VALIDATING or READY_TO_COMMIT, got {manifest['state']}"
        )
    conflicts = _head_scope_conflicts(manifest)
    if conflicts:
        raise RefreshRunError(
            f"HEAD moved across {len(conflicts)} in-scope path(s): {conflicts[:3]}"
        )
    current_model = _model_state(manifest["family"], manifest["platform"])
    current_source_sha = _source_sha(manifest["family"], manifest["platform"])
    expected_sha = manifest.get("target_source_sha")
    if (
        current_model.get("repo_sha") != current_source_sha
        or current_source_sha != expected_sha
        or manifest.get("target_model_sha") != expected_sha
    ):
        raise RefreshRunError(
            "Knowledge/source/run pin mismatch at verification: "
            f"model={current_model.get('repo_sha')}, source={current_source_sha}, "
            f"run_target={expected_sha}"
        )
    _assert_scope_ownership(manifest)
    _assert_run_evidence_ready(manifest)

    family, platform, rid = (
        manifest["family"],
        manifest["platform"],
        manifest["run_id"],
    )
    python = sys.executable
    scope_paths = list(manifest.get("scope", {}).get("paths") or [])
    run_root = _run_root(family, platform, rid)
    validation_root = run_root / "validation"
    prior_attempts = [
        int(path.name.split("-", 1)[1])
        for path in validation_root.glob("attempt-*")
        if path.is_dir() and path.name.split("-", 1)[1].isdigit()
    ] if validation_root.is_dir() else []
    validation_attempt = max(prior_attempts, default=0) + 1
    validation_logs = validation_root / f"attempt-{validation_attempt:02d}"
    validation_logs.mkdir(parents=True, exist_ok=True)
    validation_details: dict[str, Any] = {}
    commands = {
        "post_refresh_verify": [
            python,
            str(
                _repo_root
                / "scripts/pipeline/commands/ops/post_refresh_verify.py"
            ),
            family,
            platform,
            "--verify",
            "--run-id",
            rid,
        ],
        "oracle": [
            python,
            str(_repo_root / "scripts/pipeline/commands/content/refresh_oracle.py"),
            family,
            platform,
            "--receipts",
            str(run_root / "receipts"),
        ],
        "triage_confirm": [
            python,
            str(_repo_root / "scripts/pipeline/lib/triage_confirm.py"),
            family,
            platform,
            "--files",
            *scope_paths,
            "--json",
        ],
        "seo_stability": [
            python,
            str(
                _repo_root
                / "scripts/pipeline/commands/content/seo_stability_check.py"
            ),
            *scope_paths,
            "--base",
            manifest["base_commit_sha"],
            "--intentional-renames",
            ",".join(manifest.get("intentional_renames") or []),
        ],
        # MT030-2026-08-13: ADVISORY_VALIDATION_FIELDS member -- runs through the
        # same uniform loop below (recorded, logged, durable-stamped via
        # truth_audit.py's own knowledge_state wiring) but excluded from the
        # blocking not_pass check further down. See ADVISORY_VALIDATION_FIELDS'
        # module-level comment for why this isn't a hard gate yet.
        "truth_audit": [
            python,
            str(_repo_root / "scripts/pipeline/commands/diagnostics/truth_audit.py"),
            family,
            platform,
        ],
    }

    def _validation_call(
        args: list[str],
    ) -> tuple[subprocess.CompletedProcess[str], str, str, str | None]:
        started_at = _utc()
        try:
            result = _command(args)
            error = None
        except Exception as exc:  # noqa: BLE001 - preserve an immutable UNKNOWN attempt
            error = _redact_artifact_text(
                f"{type(exc).__name__}: {exc}"
            )
            result = subprocess.CompletedProcess(
                args=args,
                returncode=3,
                stdout="",
                stderr=error,
            )
        return result, started_at, _utc(), error

    for field, args in commands.items():
        result, started_at, completed_at, exception_text = _validation_call(args)
        manifest["validation"][field] = (
            "PASS" if result.returncode == 0 else
            "UNKNOWN" if result.returncode == 3 else
            "FAIL"
        )
        stdout = _redact_artifact_text(result.stdout)
        stderr = _redact_artifact_text(result.stderr)
        _event(
            family,
            platform,
            rid,
            "VALIDATION_RESULT",
            validator=field,
            result=manifest["validation"][field],
            exit_code=result.returncode,
            stdout_sha256=hashlib.sha256(stdout.encode("utf-8")).hexdigest(),
            stderr_sha256=hashlib.sha256(stderr.encode("utf-8")).hexdigest(),
        )
        stdout_path = validation_logs / f"{field}.stdout.log"
        stderr_path = validation_logs / f"{field}.stderr.log"
        atomic_write(stdout_path, stdout)
        atomic_write(stderr_path, stderr)
        validation_details[field] = {
            "exit_code": result.returncode,
            "stdout_ref": stdout_path.relative_to(run_root).as_posix(),
            "stderr_ref": stderr_path.relative_to(run_root).as_posix(),
            "stdout_digest": _file_digest(stdout_path),
            "stderr_digest": _file_digest(stderr_path),
            "command": [_redact_artifact_text(arg) for arg in args],
            "started_at": started_at,
            "completed_at": completed_at,
            "attempt": validation_attempt,
            "retry_count": validation_attempt - 1,
            "exception": exception_text,
            **_result_counters(stdout, stderr),
        }

    scoped_commands = {
        "content_audit": [
            python,
            str(_repo_root / "scripts/pipeline/commands/content/audit.py"),
            "--files",
        ],
        "link_validation": [
            python,
            str(_repo_root / "scripts/pipeline/commands/ops/link_validator.py"),
            "--files",
        ],
    }
    # Keep Windows command lines bounded while still validating the exact run
    # scope. The aggregate is FAIL > UNKNOWN > PASS.
    for field, prefix in scoped_commands.items():
        chunk_results: list[str] = []
        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []
        exit_codes: list[int] = []
        chunk_details: list[dict[str, Any]] = []
        for offset in range(0, len(scope_paths), 40):
            chunk = scope_paths[offset:offset + 40]
            chunk_args = [*prefix, *chunk]
            result, started_at, completed_at, exception_text = (
                _validation_call(chunk_args)
            )
            exit_codes.append(result.returncode)
            stdout_chunks.append(_redact_artifact_text(result.stdout))
            stderr_chunks.append(_redact_artifact_text(result.stderr))
            status = (
                "PASS" if result.returncode == 0 else
                "UNKNOWN" if result.returncode == 3 else
                "FAIL"
            )
            chunk_results.append(status)
            _event(
                family,
                platform,
                rid,
                "VALIDATION_RESULT",
                validator=field,
                result=status,
                chunk_index=offset // 40,
                page_count=len(chunk),
                exit_code=result.returncode,
                stdout_sha256=hashlib.sha256(
                    _redact_artifact_text(result.stdout).encode("utf-8")
                ).hexdigest(),
                stderr_sha256=hashlib.sha256(
                    _redact_artifact_text(result.stderr).encode("utf-8")
                ).hexdigest(),
            )
            chunk_details.append(
                {
                    "chunk_index": offset // 40,
                    "page_count": len(chunk),
                    "exit_code": result.returncode,
                    "started_at": started_at,
                    "completed_at": completed_at,
                    "exception": exception_text,
                }
            )
        manifest["validation"][field] = (
            "FAIL" if "FAIL" in chunk_results else
            "UNKNOWN" if "UNKNOWN" in chunk_results or not chunk_results else
            "PASS"
        )
        stdout_path = validation_logs / f"{field}.stdout.log"
        stderr_path = validation_logs / f"{field}.stderr.log"
        atomic_write(stdout_path, "\n".join(stdout_chunks))
        atomic_write(stderr_path, "\n".join(stderr_chunks))
        validation_details[field] = {
            "exit_codes": exit_codes,
            "stdout_ref": stdout_path.relative_to(run_root).as_posix(),
            "stderr_ref": stderr_path.relative_to(run_root).as_posix(),
            "stdout_digest": _file_digest(stdout_path),
            "stderr_digest": _file_digest(stderr_path),
            "command_prefix": [
                _redact_artifact_text(arg) for arg in prefix
            ],
            "attempt": validation_attempt,
            "retry_count": validation_attempt - 1,
            "chunks": chunk_details,
            **_result_counters(
                "\n".join(stdout_chunks), "\n".join(stderr_chunks)
            ),
        }
    validation_payload = {
        "schema_version": 1,
        "run_id": rid,
        "attempt": validation_attempt,
        "base_commit_sha": manifest["base_commit_sha"],
        "target_source_sha": manifest["target_source_sha"],
        "results": manifest["validation"],
        "details": validation_details,
        "recorded_at": _utc(),
    }
    attempt_validation_path = validation_logs / "result.json"
    _write_json(attempt_validation_path, validation_payload)
    validation_path = run_root / "validation.json"
    _write_json(validation_path, validation_payload)
    attempt_ref = attempt_validation_path.relative_to(run_root).as_posix()
    manifest.setdefault("validation_attempt_refs", []).append(attempt_ref)
    manifest.setdefault("validation_attempt_digests", {})[attempt_ref] = (
        _file_digest(attempt_validation_path)
    )
    manifest["output_digests"]["validation"] = _file_digest(validation_path)
    _save_manifest(manifest)

    not_pass = {
        k: v for k, v in manifest["validation"].items()
        if v != "PASS" and k not in ADVISORY_VALIDATION_FIELDS
    }
    if not_pass:
        raise RefreshRunError(f"Validation did not pass: {not_pass}")

    # Page-Impact Matrix (S9.1, Task 2, closes G7): a composed, read-only
    # cross-surface report joining knowledge_delta.json, semantic_changes.json,
    # page_impact.json, page_decisions.jsonl, triage_verdict.yaml,
    # package_registry.json, manifest.json, and oracle_verdicts/ -- never a
    # second source of truth (see page_impact_matrix.py's own docstring for
    # why that framing matters, per F1). Deliberately placed AFTER the
    # not_pass gate above (a run that fails validation never reaches this
    # point, so no matrix is ever written for a run that isn't genuinely
    # about to be marked READY_TO_COMMIT) and is advisory by construction:
    # a failure building the matrix must never block a run whose real
    # validators already passed.
    try:
        matrix_json_path, _matrix_md_path = page_impact_matrix.write_matrix_report(
            family, platform, rid
        )
        manifest.setdefault("output_digests", {})["page_impact_matrix"] = (
            page_impact_matrix.matrix_digest(matrix_json_path)
        )
    except Exception as exc:  # noqa: BLE001 -- advisory only, see docstring above
        manifest.setdefault("output_digests", {})["page_impact_matrix"] = None
        manifest["page_impact_matrix_error"] = str(exc)

    # Locale evidence-staleness sizing (§9.8, Task 11d, closes G8/sizes F7):
    # advisory-only, additive, same placement rationale as the matrix call above
    # (never blocks a run whose real validators already passed). force=False is
    # deliberate here (unlike the CLI's own explicit --include-locales call,
    # which always forces a fresh scan): verify_run() can fire repeatedly across
    # retries for the same run, and a full corpus scan measured live at ~35s for
    # pdf/java's ~12,300-file locale footprint alone -- reusing a same-repo_sha
    # cached report (see scan_product_locales' own docstring) keeps this cheap
    # for the common case without ever serving a stale count once the knowledge
    # baseline actually advances. Never remediates anything -- detection only.
    try:
        locale_report = stale_detect.scan_product_locales(
            family, platform,
            content_root=_repo_root / "content",
            knowledge_root=_repo_root / "knowledge",
            report_root=_repo_root / "reports" / "locale_staleness",
            force=False,
        )
        report_path = _repo_root / "reports" / "locale_staleness" / f"{family}-{platform}.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(locale_report, indent=2, ensure_ascii=False), encoding="utf-8")
        manifest["locale_staleness_summary"] = {
            "knowledge_repo_sha": locale_report["knowledge_repo_sha"],
            "total_locale_files": locale_report["total_locale_files"],
            "total_stale": locale_report["total_stale"],
        }
    except Exception as exc:  # noqa: BLE001 -- advisory only, see docstring above
        manifest["locale_staleness_summary"] = None
        manifest["locale_staleness_error"] = str(exc)

    # Content-coverage audit (found live 2026-08-24, deep-reassessment pass):
    # a cumulative, delta-independent detector for api_surface.json classes
    # with no reference page -- closes a real structural gap where a genuine
    # knowledge advance (e.g. pdf/java's ~121-class Structured Document Model
    # addition) was correctly captured by ONE refresh cycle but never
    # consumed by content generation, becoming permanently invisible to every
    # LATER cycle's own (necessarily narrower, point-in-time) delta. See
    # content_coverage_audit.py's own module docstring for the full account.
    # Cheap (~0.6s measured live for pdf/java's 1157-class corpus -- a plain
    # file-existence check per candidate, not a content parse) so no caching
    # is needed here unlike locale staleness above. Advisory only, same
    # placement/try-except pattern as every other step in this block --
    # never blocks a run whose real validators already passed.
    #
    # Catches SystemExit alongside Exception (a deliberate, narrow addition,
    # not BaseException -- KeyboardInterrupt etc. must still propagate):
    # batch_reference.run() signals its own missing-precondition errors (e.g.
    # no api_surface.json yet) via sys.exit(1), a CLI-style convention that
    # raises SystemExit, which does NOT inherit from Exception. A bare
    # `except Exception` here would let that propagate uncaught, crashing
    # this entire advisory step instead of degrading gracefully -- found live
    # while wiring this in (test fixtures without api_surface.json are a
    # normal, expected state elsewhere in verify_run()'s own test suite, not
    # a real error).
    try:
        coverage_report = content_coverage_audit.scan_product(family, platform)
        content_coverage_audit.write_report(
            coverage_report, report_root=_repo_root / "reports" / "content_coverage"
        )
        manifest["content_coverage_summary"] = {
            "total_candidates": coverage_report["total_candidates"],
            "missing_page_count": coverage_report["missing_page_count"],
        }
    except (Exception, SystemExit) as exc:  # noqa: BLE001 -- advisory only, see docstring above
        manifest["content_coverage_summary"] = None
        # SystemExit's own str() is just the bare exit code (e.g. "1") --
        # batch_reference.run()'s real message already went to stdout via
        # print(), so name the exception type too for a self-contained record.
        manifest["content_coverage_error"] = f"{type(exc).__name__}: {exc}"
    _save_manifest(manifest)  # persist the digest even when state is already READY_TO_COMMIT (re-verify)

    if manifest["state"] == "VALIDATING":
        _transition(manifest, "READY_TO_COMMIT", checkpoint="validation_complete")
    return manifest


def _block(manifest: dict[str, Any], exc: Exception) -> None:
    prior = manifest["state"]
    if prior in TERMINAL_STATES:
        return
    resume_map = {
        # APPLYING is an in-flight state. A resume re-enters from the durable
        # PLANNED checkpoint; immutable/idempotent writer evidence prevents
        # duplicate receipts and scoped hash checks detect outside edits.
        "APPLYING": "PLANNED",
        "VALIDATING": "VALIDATING",
    }
    manifest["resume_state"] = (
        resume_map.get(prior, prior)
        if prior != "BLOCKED"
        else manifest.get("resume_state")
    )
    reason = _redact_artifact_text(str(exc))
    manifest["failure_reason"] = reason
    if prior != "BLOCKED":
        _transition(manifest, "BLOCKED")
    else:
        _save_manifest(manifest)
    _event(
        manifest["family"],
        manifest["platform"],
        manifest["run_id"],
        "RUN_BLOCKED",
        resume_state=manifest.get("resume_state"),
        reason=reason,
    )


def execute_run(
    family: str,
    platform: str,
    run_id: str,
    *,
    session_id: str | None = None,
    dry_run: bool = False,
    resume: bool = False,
) -> dict[str, Any]:
    owner = _session_id(session_id)
    with _product_guard(family, platform):
        _assert_active(family, platform, run_id)
        manifest = _load_manifest(family, platform, run_id)
        if manifest["session_owner"] != owner:
            raise RefreshRunError(
                f"Run is owned by session {manifest['session_owner']!r}, not {owner!r}"
            )
        if manifest["state"] == "BLOCKED":
            if not resume:
                raise RefreshRunError(
                    "Run is BLOCKED; use resume after correcting the recorded cause"
                )
            resume_state = manifest.get("resume_state")
            manifest["failure_reason"] = None
            manifest["resume_state"] = None
            _transition(manifest, resume_state, checkpoint="resumed")
        try:
            if manifest["state"] == "INPUTS_PINNED":
                prepare_run(manifest)
            if dry_run:
                return manifest
            if manifest["state"] == "PLANNED":
                apply_run(manifest)
            if manifest["state"] == "VALIDATING":
                verify_run(manifest)
            return manifest
        except Exception as exc:
            _block(manifest, exc)
            raise


def _restore_scope_to_baseline(
    manifest: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """Restore every scoped path this run touched back to its pinned-baseline
    bytes, verified by hash. Returns (restored_paths, already_restored_paths).

    RPR-ABANDON-001: shared by abandon_run and recover_run so both verbs give
    the same working-tree safety guarantee -- previously only recover_run had
    this, and a real production incident (FONT-PYTHON-REFRESH-002) shows
    corruption compounding across repeated abandon+restart cycles precisely
    because abandon left whatever body_refresh.py had already written on
    disk, and the next attempt started from that dirty state, not a clean
    baseline.

    A run abandoned before APPLYING ever produced page_decisions.jsonl has
    nothing to restore -- this must remain a harmless no-op, not an error
    (_assert_run_evidence_ready raises on a missing/mismatched artifact, so
    it is only safe to call once page_decisions.jsonl actually exists).
    """
    run_root = _run_root(
        manifest["family"], manifest["platform"], manifest["run_id"]
    )
    if not (run_root / "page_decisions.jsonl").is_file():
        return [], []
    decision_rows = _assert_run_evidence_ready(
        manifest,
        require_all_pass=False,
        include_attempts=False,
    )
    scope = json.loads(
        (run_root / "scope.json").read_text(encoding="utf-8")
    )
    initial_hashes = dict(scope.get("initial_hashes") or {})
    restore_payloads: dict[str, bytes] = {}
    already_restored: list[str] = []
    for row in decision_rows:
        page_path = str(row["page_path"])
        initial_hash = initial_hashes.get(page_path)
        receipt_path = run_root / Path(row["receipt_ref"])
        receipt_doc = yaml.safe_load(
            receipt_path.read_text(encoding="utf-8")
        ) or {}
        output_hash = (
            receipt_doc.get("content_refresh_receipt") or {}
        ).get("new_hash")
        current_hash = _path_hash(page_path)
        if current_hash == initial_hash:
            already_restored.append(page_path)
            continue
        if not isinstance(output_hash, str) or current_hash != output_hash:
            raise RefreshRunError(
                "Recovery refused because a scoped path no longer matches "
                f"the run output or pinned input: {page_path}"
            )
        result = _command_runner(
            [
                "git",
                "cat-file",
                "--filters",
                f"--path={page_path}",
                f"{manifest['base_commit_sha']}:{page_path}",
            ],
            cwd=str(_repo_root),
            capture_output=True,
            text=False,
            timeout=30,
        )
        if result.returncode != 0:
            raise RefreshRunError(
                "Recovery will not delete a path absent from the pinned base: "
                f"{page_path}"
            )
        payload = result.stdout
        if isinstance(payload, str):
            payload = payload.encode("utf-8")
        restored_hash = "sha256:" + hashlib.sha256(payload).hexdigest()
        if restored_hash != initial_hash:
            raise RefreshRunError(
                "Pinned base bytes do not match the recorded initial hash for "
                f"{page_path}"
            )
        restore_payloads[page_path] = payload

    for page_path, payload in restore_payloads.items():
        atomic_write_bytes(_repo_root / page_path, payload)
        if _path_hash(page_path) != initial_hashes[page_path]:
            raise RefreshRunError(
                f"Recovery write verification failed for {page_path}"
            )

    return sorted(restore_payloads), sorted(already_restored)


def abandon_run(
    family: str,
    platform: str,
    run_id: str,
    *,
    reason: str,
    session_id: str | None = None,
) -> dict[str, Any]:
    owner = _session_id(session_id)
    if not reason.strip():
        raise RefreshRunError("abandon requires a non-empty --reason")
    with _product_guard(family, platform):
        _assert_active(family, platform, run_id)
        manifest = _load_manifest(family, platform, run_id)
        if manifest["session_owner"] != owner:
            raise RefreshRunError(
                f"Run is owned by session {manifest['session_owner']!r}, not {owner!r}"
            )
        # abandon is the unconditional, last-resort "give up" verb -- it must
        # never get stuck ACTIVE, for ANY reason _restore_scope_to_baseline
        # can fail: a crash mid-APPLYING leaving manifest["output_digests"]
        # unfinalized (RefreshRunError from _assert_run_evidence_ready), but
        # also a corrupt/missing scope.json or receipt (FileNotFoundError,
        # json/yaml decode errors), a malformed decision row (KeyError), a
        # hung git subprocess (subprocess.TimeoutExpired), or a disk-full
        # write (OSError) -- all of these are exactly the "run is in a messy,
        # crashed state" scenarios abandon exists to rescue from, so all of
        # them must degrade to a best-effort, unverified restore rather than
        # propagate. recover_run (an explicit, deliberate operator action)
        # still fails loudly on any of these by design; only abandon must not.
        restore_error: str | None = None
        try:
            restored_paths, already_restored = _restore_scope_to_baseline(manifest)
        except Exception as exc:  # noqa: BLE001 -- abandon must never re-raise; see above
            restored_paths, already_restored = [], []
            restore_error = _redact_artifact_text(str(exc))
        manifest["recovery"] = {
            "base_commit_sha": manifest["base_commit_sha"],
            "restored_paths": restored_paths,
            "already_restored_paths": already_restored,
            "reason": _redact_artifact_text(reason.strip()),
            "completed_at": _utc(),
        }
        if restore_error is not None:
            manifest["recovery"]["restore_error"] = restore_error
        _save_manifest(manifest)
        _event(
            family,
            platform,
            run_id,
            "RUN_RECOVERED",
            restored_paths=restored_paths,
            already_restored_paths=already_restored,
            restore_error=restore_error,
        )
        _transition_abandoned(manifest, reason=reason)
        _clear_active(family, platform, run_id)
        return manifest


def recover_run(
    family: str,
    platform: str,
    run_id: str,
    *,
    reason: str,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Restore evidence-owned outputs from the pinned base, then abandon the run."""
    owner = _session_id(session_id)
    if not reason.strip():
        raise RefreshRunError("recover requires a non-empty --reason")
    with _product_guard(family, platform):
        _assert_active(family, platform, run_id)
        manifest = _load_manifest(family, platform, run_id)
        if manifest["session_owner"] != owner:
            raise RefreshRunError(
                f"Run is owned by session {manifest['session_owner']!r}, not {owner!r}"
            )
        if manifest["state"] in TERMINAL_STATES:
            raise RefreshRunError(
                f"recover cannot operate on terminal state {manifest['state']}"
            )
        restored_paths, already_restored = _restore_scope_to_baseline(manifest)
        manifest["recovery"] = {
            "base_commit_sha": manifest["base_commit_sha"],
            "restored_paths": restored_paths,
            "already_restored_paths": already_restored,
            "reason": _redact_artifact_text(reason.strip()),
            "completed_at": _utc(),
        }
        _save_manifest(manifest)
        _event(
            family,
            platform,
            run_id,
            "RUN_RECOVERED",
            restored_paths=restored_paths,
            already_restored_paths=already_restored,
        )
        _transition_abandoned(
            manifest,
            reason=reason,
            checkpoint="recovery_complete",
        )
        _clear_active(family, platform, run_id)
        return manifest


def _commit_trailer_values(message: str) -> dict[str, list[str]]:
    """Return simple ``Key: value`` fields from the final Git trailer block.

    A matching line in the subject or body is not a trailer.  The accepted
    block must be the final non-empty paragraph and every line in that
    paragraph must have trailer syntax.  The refresh contract deliberately
    emits single-line values, so continuation lines are not accepted here.
    """
    lines = message.rstrip().splitlines()
    if not lines:
        return {}
    start = len(lines)
    trailer_line = re.compile(r"^([A-Za-z0-9][A-Za-z0-9-]*):[ \t]*(.*)$")
    while start > 0 and trailer_line.fullmatch(lines[start - 1]):
        start -= 1
    if start == len(lines):
        return {}
    if start > 0 and lines[start - 1].strip():
        return {}
    values: dict[str, list[str]] = {}
    for line in lines[start:]:
        match = trailer_line.fullmatch(line)
        if match is None:  # defensive; the backward scan already checked it
            return {}
        values.setdefault(match.group(1), []).append(match.group(2).strip())
    return values


def bind_commit(
    family: str,
    platform: str,
    run_id: str,
    commit_sha: str,
    *,
    session_id: str | None = None,
) -> dict[str, Any]:
    owner = _session_id(session_id)
    with _product_guard(family, platform):
        _assert_active(family, platform, run_id)
        manifest = _load_manifest(family, platform, run_id)
        if manifest["session_owner"] != owner:
            raise RefreshRunError(
                f"Run is owned by session {manifest['session_owner']!r}, not {owner!r}"
            )
        if manifest["state"] != "READY_TO_COMMIT":
            raise RefreshRunError(
                f"bind-commit requires READY_TO_COMMIT, got {manifest['state']}"
            )
        current_model = _model_state(family, platform)
        current_source_sha = _source_sha(family, platform)
        expected_sha = manifest.get("target_source_sha")
        if (
            current_model.get("repo_sha") != current_source_sha
            or current_source_sha != expected_sha
            or manifest.get("target_model_sha") != expected_sha
        ):
            raise RefreshRunError(
                "Knowledge/source/run pin mismatch at commit binding: "
                f"model={current_model.get('repo_sha')}, "
                f"source={current_source_sha}, run_target={expected_sha}"
            )
        _assert_scope_ownership(manifest)
        decision_rows = _assert_run_evidence_ready(
            manifest, include_validation=True
        )
        not_pass = {
            key: value
            for key, value in (manifest.get("validation") or {}).items()
            if value != "PASS" and key not in ADVISORY_VALIDATION_FIELDS
        }
        if not_pass:
            raise RefreshRunError(
                f"Run validation is not commit-ready: {not_pass}"
            )
        resolved = _git("rev-parse", f"{commit_sha}^{{commit}}")
        ancestor = _command_runner(
            ["git", "merge-base", "--is-ancestor", manifest["base_commit_sha"], resolved],
            cwd=str(_repo_root),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if ancestor.returncode != 0:
            raise RefreshRunError(
                f"Commit {resolved} does not descend from base {manifest['base_commit_sha']}"
            )
        message = _git("show", "-s", "--format=%B", resolved)
        required = {
            "Refresh-Run": run_id,
            "Refresh-Base": manifest["base_commit_sha"],
            "Refresh-Source-SHA": manifest["target_source_sha"],
        }
        trailers = _commit_trailer_values(message)
        invalid_trailers = []
        for key, value in required.items():
            matches = trailers.get(key, [])
            if matches != [value]:
                invalid_trailers.append(
                    f"{key}: expected exactly [{value!r}], found {matches!r}"
                )
        if invalid_trailers:
            raise RefreshRunError(
                "Commit has missing, duplicate, or conflicting refresh trailers: "
                f"{invalid_trailers}"
            )
        changed_paths = {
            path
            for path in _git(
                "diff-tree",
                "--no-commit-id",
                "--name-only",
                "-r",
                resolved,
            ).splitlines()
            if path
        }
        allowed_paths = _allowed_commit_paths(
            list(manifest.get("scope", {}).get("paths") or []),
            decision_rows,
            run_root=_run_root(family, platform, run_id),
        )
        if not changed_paths:
            raise RefreshRunError(f"Commit {resolved} has no changed paths")
        unexpected_set, _ = _casefold_path_diff(changed_paths, allowed_paths)
        unexpected = sorted(unexpected_set)
        if unexpected:
            raise RefreshRunError(
                "Refresh commit contains paths outside the pinned run scope: "
                f"{unexpected[:5]}"
            )
        expected_changed: set[str] = set()
        for row in decision_rows:
            if row.get("disposition") in {
                "BODY_UPDATED",
                "EVIDENCE_ONLY",
                "GENERATED",
                "RETIRED",
            }:
                expected_changed.add(str(row.get("page_path")))
        # Authorized out-of-band writes (TC-DUPIDX-02, S-73 manual-edit
        # fallback, or a pre-commit-hook content_hash normalization on an
        # already-authorized file) have no decision row by design; treat
        # them as expected too, mirroring _allowed_commit_paths above
        # (confirmed live 2026-08-14, 3d/java).
        expected_changed.update(
            _load_extra_allowed_hashes(_run_root(family, platform, run_id)).keys()
        )
        missing_changed_set, unexpected_changed_set = _casefold_path_diff(
            expected_changed, changed_paths
        )
        if missing_changed_set or unexpected_changed_set:
            raise RefreshRunError(
                "Refresh commit paths do not exactly match change decisions: "
                f"missing={sorted(missing_changed_set)[:5]}, "
                f"unexpected={sorted(unexpected_changed_set)[:5]}"
            )
        from commands.content.body_refresh import (
            _frontmatter_hash,
            _normalized_body_hash,
        )

        extra_allowed_for_bind = _load_extra_allowed_hashes(
            _run_root(family, platform, run_id)
        )
        # git's tree object is case-sensitive even on a case-insensitive
        # filesystem: a decision row recording the generator's canonical
        # class-name casing ('Camera.md') resolves to nothing via a direct
        # `git cat-file <sha>:Camera.md` lookup when the tree actually
        # tracks it as 'camera.md' (confirmed live 2026-08-14, 3d/java --
        # git add on Windows never renamed the already-tracked lowercase
        # path). Resolve each decision row's page_path to its real
        # git-tracked casing via a full tree listing at this commit --
        # `changed_paths` alone is not enough: a NOT_AFFECTED page's decision
        # row still needs this resolution but was never rewritten, so it
        # never appears in `git diff-tree`'s changed-paths output.
        tree_listing = _git("ls-tree", "-r", "--name-only", resolved)
        changed_path_by_casefold = {
            p.casefold(): p for p in tree_listing.splitlines() if p
        }
        hash_mismatches: list[str] = []
        for row in decision_rows:
            page_path = str(row["page_path"])
            git_path = changed_path_by_casefold.get(page_path.casefold(), page_path)
            result = _command_runner(
                [
                    "git",
                    "cat-file",
                    "--filters",
                    f"--path={git_path}",
                    f"{resolved}:{git_path}",
                ],
                cwd=str(_repo_root),
                capture_output=True,
                text=False,
                timeout=30,
            )
            if result.returncode != 0:
                hash_mismatches.append(page_path)
                continue
            committed_bytes = result.stdout
            if not isinstance(committed_bytes, bytes):
                committed_bytes = str(committed_bytes).encode("utf-8")
            receipt_path = _run_root(family, platform, run_id) / Path(
                str(row["receipt_ref"])
            )
            receipt_doc = yaml.safe_load(
                receipt_path.read_text(encoding="utf-8")
            ) or {}
            receipt = receipt_doc.get("content_refresh_receipt") or {}
            committed_raw_hash = (
                "sha256:" + hashlib.sha256(committed_bytes).hexdigest()
            )
            try:
                # Universal-newline decode, matching every other text read in
                # this module (Path.read_text() always normalizes CRLF->LF).
                # A raw .decode() preserves real CRLF bytes some pre-existing
                # committed pages carry (confirmed live 2026-08-14, 3d/java:
                # working-with-3d-formats-in-java/index.md was already CRLF
                # in git history, untouched -- NOT_AFFECTED disposition), and
                # the receipt's body/frontmatter hashes were computed at
                # write time from a universal-newline read, so comparing a
                # raw CRLF decode against them is a false mismatch, not a
                # real content difference.
                committed_text = committed_bytes.decode("utf-8").replace(
                    "\r\n", "\n"
                )
            except UnicodeDecodeError:
                hash_mismatches.append(page_path)
                continue
            if (
                committed_raw_hash != receipt.get("new_hash")
                or _normalized_body_hash(committed_text)
                != row.get("body_hash_after")
                or _frontmatter_hash(committed_text)
                != row.get("frontmatter_hash_after")
            ):
                # A page can carry a valid S-84-chain receipt AND a later
                # authorized out-of-band edit (e.g. an S-73 manual-edit
                # fallback fixing a stale API reference the chain's own
                # strategies didn't resolve) -- the receipt then legitimately
                # predates the final committed bytes. Accept it only when the
                # committed content matches the SUBSEQUENT authorization, not
                # merely because an extra_allowed entry exists for the path
                # (confirmed live 2026-08-14, 3d/java).
                if committed_raw_hash not in extra_allowed_for_bind.get(page_path, set()):
                    hash_mismatches.append(page_path)
        if hash_mismatches:
            raise RefreshRunError(
                "Bound commit content does not match run decisions: "
                f"{hash_mismatches[:5]}"
            )
        manifest["commit_sha"] = resolved
        _transition(manifest, "COMMITTED", checkpoint="commit_bound")
        _clear_active(family, platform, run_id)
        return manifest


def _locate_run(run_id: str) -> tuple[str, str]:
    run_id = _safe_token(run_id, "run_id")
    matches = list((_reports_root / "refresh_runs").glob(f"*/*/{run_id}/manifest.json"))
    if not matches:
        raise RefreshRunError(f"Run not found: {run_id}")
    if len(matches) > 1:
        raise RefreshRunError(f"Run ID is ambiguous across products: {run_id}")
    path = matches[0]
    return path.parents[2].name, path.parents[1].name


def _print_manifest(manifest: dict[str, Any]) -> None:
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="refresh_run",
        description="Run-bound state machine for the S-84 product refresh chain.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start")
    start.add_argument("family")
    start.add_argument("platform")
    start.add_argument("--mode", choices=sorted(MODES), required=True)
    start.add_argument("--scope-manifest")
    start.add_argument("--run-id")
    start.add_argument("--session-id")

    for name in ("run", "resume", "verify", "status"):
        command = sub.add_parser(name)
        command.add_argument("--run-id", required=True)
        if name in {"run", "resume", "verify"}:
            command.add_argument("--session-id")
        if name in {"run", "resume"}:
            command.add_argument("--dry-run", action="store_true")

    bind = sub.add_parser("bind-commit")
    bind.add_argument("--run-id", required=True)
    bind.add_argument("--commit", required=True)
    bind.add_argument("--session-id")

    abandon = sub.add_parser("abandon")
    abandon.add_argument("--run-id", required=True)
    abandon.add_argument("--reason", required=True)
    abandon.add_argument("--session-id")

    recover = sub.add_parser("recover")
    recover.add_argument("--run-id", required=True)
    recover.add_argument("--reason", required=True)
    recover.add_argument("--session-id")

    args = parser.parse_args(argv)
    try:
        if args.command == "start":
            manifest = create_run(
                args.family,
                args.platform,
                mode=args.mode,
                scope_manifest=args.scope_manifest,
                run_id=args.run_id,
                session_id=args.session_id,
            )
        else:
            family, platform = _locate_run(args.run_id)
            if args.command in {"run", "resume"}:
                manifest = execute_run(
                    family,
                    platform,
                    args.run_id,
                    session_id=args.session_id,
                    dry_run=args.dry_run,
                    resume=args.command == "resume",
                )
            elif args.command == "verify":
                owner = _session_id(args.session_id)
                with _product_guard(family, platform):
                    manifest = _load_manifest(family, platform, args.run_id)
                    if manifest["session_owner"] != owner:
                        raise RefreshRunError(
                            f"Run is owned by {manifest['session_owner']!r}, not {owner!r}"
                        )
                    try:
                        verify_run(manifest)
                    except Exception as exc:
                        _block(manifest, exc)
                        raise
            elif args.command == "bind-commit":
                manifest = bind_commit(
                    family,
                    platform,
                    args.run_id,
                    args.commit,
                    session_id=args.session_id,
                )
            elif args.command == "abandon":
                manifest = abandon_run(
                    family,
                    platform,
                    args.run_id,
                    reason=args.reason,
                    session_id=args.session_id,
                )
            elif args.command == "recover":
                manifest = recover_run(
                    family,
                    platform,
                    args.run_id,
                    reason=args.reason,
                    session_id=args.session_id,
                )
            else:
                manifest = _load_manifest(family, platform, args.run_id)
        _print_manifest(manifest)
        return 0
    except RefreshRunError as exc:
        print(f"REFRESH-RUN BLOCKED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
