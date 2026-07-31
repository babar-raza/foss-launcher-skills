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
import os
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

from advisory_lock import FileLock, LockTimeout  # noqa: E402
from core.fs import atomic_write, atomic_write_bytes  # noqa: E402
from lib.schema_validators import (  # noqa: E402
    validate_refresh_page_decision,
    validate_refresh_run_manifest,
)

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


def _utc() -> str:
    return _now().astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_token(value: str, label: str) -> str:
    if not isinstance(value, str) or not _SAFE_TOKEN.fullmatch(value) or ".." in value:
        raise RefreshRunError(
            f"{label} must match {_SAFE_TOKEN.pattern!r} and must not contain '..'"
        )
    return value


def _session_id(explicit: str | None = None) -> str:
    value = (
        explicit
        or os.environ.get("AGENT_SESSION_ID", "").strip()
        or os.environ.get("CODEX_THREAD_ID", "").strip()
    )
    if not value:
        raise RefreshRunError(
            "A stable session identity is required: pass --session-id or set "
            "AGENT_SESSION_ID/CODEX_THREAD_ID"
        )
    cleaned = "".join(c if (c.isalnum() or c in "-_") else "-" for c in value)[:64]
    return _safe_token(cleaned, "session_id")


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
    if data.get("stale_since") is not None:
        raise RefreshRunError(
            f"Knowledge model is stale since {data.get('stale_since')}; refresh knowledge first"
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
    missing = sorted(scope_set - decision_paths)
    unexpected = sorted(decision_paths - scope_set)

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
    scope_paths: list[str], decision_rows: list[dict[str, Any]]
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


def _assert_scope_ownership(manifest: dict[str, Any]) -> None:
    """OCC guard for uncommitted/concurrent edits and interrupted resumes."""
    run_root = _run_root(
        manifest["family"], manifest["platform"], manifest["run_id"]
    )
    scope = _assert_pinned_scope(manifest)
    initial_hashes = dict(scope.get("initial_hashes") or {})
    allowed_hashes = {
        path: {value} for path, value in initial_hashes.items()
    }

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
            allowed_hashes.setdefault(row["page_path"], set()).add(
                receipt.get("new_hash")
            )

    conflicts = [
        path
        for path, acceptable in allowed_hashes.items()
        if not acceptable
        or any(not isinstance(value, str) for value in acceptable)
        or _path_hash(path) not in acceptable
    ]
    if conflicts:
        raise RefreshRunError(
            "Scoped working files changed outside a validated run checkpoint: "
            f"{conflicts[:5]}"
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
        scope_paths, decision_rows, initial_hashes
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
    """Execute the two refresh writers under the run-bound contract."""
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
        reference_mode = (
            ["--rebuild-all", "--confirm-rebuild"]
            if manifest["mode"] == "remediation"
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
        k: v for k, v in manifest["validation"].items() if v != "PASS"
    }
    if not_pass:
        raise RefreshRunError(f"Validation did not pass: {not_pass}")
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
        decision_rows = _assert_run_evidence_ready(
            manifest,
            require_all_pass=False,
            include_attempts=False,
        )
        run_root = _run_root(family, platform, run_id)
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

        restored_paths = sorted(restore_payloads)
        manifest["recovery"] = {
            "base_commit_sha": manifest["base_commit_sha"],
            "restored_paths": restored_paths,
            "already_restored_paths": sorted(already_restored),
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
            already_restored_paths=sorted(already_restored),
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
            if value != "PASS"
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
            list(manifest.get("scope", {}).get("paths") or []), decision_rows
        )
        if not changed_paths:
            raise RefreshRunError(f"Commit {resolved} has no changed paths")
        unexpected = sorted(changed_paths.difference(allowed_paths))
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
        if changed_paths != expected_changed:
            raise RefreshRunError(
                "Refresh commit paths do not exactly match change decisions: "
                f"missing={sorted(expected_changed - changed_paths)[:5]}, "
                f"unexpected={sorted(changed_paths - expected_changed)[:5]}"
            )
        from commands.content.body_refresh import (
            _frontmatter_hash,
            _normalized_body_hash,
        )

        hash_mismatches: list[str] = []
        for row in decision_rows:
            page_path = str(row["page_path"])
            result = _command_runner(
                [
                    "git",
                    "cat-file",
                    "--filters",
                    f"--path={page_path}",
                    f"{resolved}:{page_path}",
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
                committed_text = committed_bytes.decode("utf-8")
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
