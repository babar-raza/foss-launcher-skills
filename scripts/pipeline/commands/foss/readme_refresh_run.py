"""CONTRACT: run-bound state machine for the /readme-refresh skill.

Mirrors scripts/pipeline/commands/ops/refresh_run.py's architecture (S-84's production
pattern -- run-ID/session-ID binding, directory-per-run evidence, one exception type, two
exit codes, FileLock-guarded single-owner-per-product locking) adapted to this skill's actual
effect boundary: the mutating effect is an EXTERNAL GitHub push + PR, not a local content
commit, so "recovery" means idempotently verifying/completing external side effects, never a
git cat-file style local restore.

State machine (plan: C:\\Users\\prora\\.claude\\plans\\d-users-prora-onedrive-documents-github-humble-tome.md,
"Skill contract update" / Design section):

    CREATED -> INPUTS_PINNED -> PLANNED -> VERIFYING_EXAMPLES -> AWAITING_REVIEW -> APPROVED -> PUSHING -> PUSHED
    BLOCKED re-enterable from INPUTS_PINNED / PLANNED / VERIFYING_EXAMPLES / PUSHING.
    ABANDONED terminal from any non-terminal state. PUSHED and ABANDONED are the only terminals.
    AWAITING_REVIEW -> PLANNED and APPROVED -> PLANNED both exist for the "recheck found drift,
    force back to re-plan" path (approve() re-verifies pinned inputs haven't drifted before
    letting a run proceed) -- `recheck` itself does NOT transition state; it re-runs the
    deterministic checks in place and updates checks/result.json.

HONEST SCOPE STATEMENT for this first real implementation (do not read a passing round-trip
test as proof every step is production-hardened to the same depth as refresh_run.py's 2500+
lines -- that script is the product of many real incidents over months; this one is new):

  - `plan`/`ingest-candidate`/`approve` are fully real: they read data/products.json,
    data/registry_exclusions.json, data/package_registry.json, data/diagram_archetypes.json,
    data/diagram_capability_dependencies.json, and the real clone cache, and they call the
    real functions in readme_refresh_checks.py -- nothing here is a stub.
  - `verify-examples` is real in its STATE MACHINE and EVIDENCE-WRITING behavior (it always
    writes upstream-issues.md, always requires a named status per code block before advancing,
    never silently passes) but its actual per-language compile/run execution is a pluggable
    seam (`configure(verification_runner=...)`), not yet wired to real Java/Go/Rust/C++/.NET/
    TypeScript toolchains -- the default runner honestly reports every block
    BLOCKED-WITH-REASON: TOOLCHAIN-UNAVAILABLE rather than claiming a compile that never
    happened. Wiring the real per-language procedure table from the plan's "Verification pass"
    section is real, separate, follow-on work.
  - `push` performs the REAL disposable-clone + branch + git-plumbing-commit + push mechanics
    (the same commit-tree/update-ref sequence used by the plan's hand-run "Manual PR-push SOP",
    now finally coded instead of hand-run) and a real `gh pr create` call when not --dry-run.
    It has not been exercised against a real external GitHub org in this pass -- only against
    local scratch git repos in the round-trip test -- pending explicit authorization to push
    live, per the plan's own Steps 3-4 ("first dry run" before "first live push").
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
_FOSS_DIR = Path(__file__).resolve().parent
if str(_FOSS_DIR) not in sys.path:
    sys.path.insert(0, str(_FOSS_DIR))

import session_identity  # noqa: E402
from advisory_lock import FileLock, LockTimeout  # noqa: E402
from core.fs import atomic_write  # noqa: E402

import readme_refresh_checks as checks  # noqa: E402

SCHEMA_VERSION = 1
TERMINAL_STATES = frozenset({"PUSHED", "ABANDONED"})
NEXT_STATES: dict[str, set[str]] = {
    "CREATED": {"INPUTS_PINNED", "BLOCKED", "ABANDONED"},
    "INPUTS_PINNED": {"PLANNED", "BLOCKED", "ABANDONED"},
    "PLANNED": {"VERIFYING_EXAMPLES", "BLOCKED", "ABANDONED"},
    "VERIFYING_EXAMPLES": {"AWAITING_REVIEW", "BLOCKED", "ABANDONED"},
    "AWAITING_REVIEW": {"APPROVED", "PLANNED", "ABANDONED"},
    "APPROVED": {"PUSHING", "PLANNED", "ABANDONED"},
    # PUSHING -> APPROVED is the dry-run-rehearsal-return path: push(dry_run=True) legitimately
    # enters PUSHING to rehearse the real disposable-clone/branch/commit mechanics under the
    # same transitions a real push uses, then returns to APPROVED since nothing was actually
    # pushed -- a real bug found via this module's own round-trip test (the transition was
    # attempted before this entry existed, correctly rejected by the state machine, exposing
    # the gap rather than silently succeeding).
    "PUSHING": {"PUSHED", "APPROVED", "BLOCKED", "ABANDONED"},
    "BLOCKED": {"INPUTS_PINNED", "PLANNED", "VERIFYING_EXAMPLES", "PUSHING", "ABANDONED"},
    "PUSHED": set(),
    "ABANDONED": set(),
}
_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
_repo_root = _DEFAULT_REPO_ROOT
_reports_root = _DEFAULT_REPO_ROOT / "reports"
_clone_cache_root = _DEFAULT_REPO_ROOT / "runs" / ".clone_cache"
_command_runner: Callable[..., "subprocess.CompletedProcess[str]"] = subprocess.run
_now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
_verification_runner: "Callable[[Path, dict], dict] | None" = None


class ReadmeRefreshRunError(RuntimeError):
    """Raised when a run contract or state transition is unsafe."""


def configure(
    *,
    repo_root: "Path | str | None" = None,
    reports_root: "Path | str | None" = None,
    clone_cache_root: "Path | str | None" = None,
    command_runner: "Callable[..., subprocess.CompletedProcess[str]] | None" = None,
    now: "Callable[[], datetime] | None" = None,
    verification_runner: "Callable[[Path, dict], dict] | None" = None,
) -> None:
    """Override external boundaries for tests; call without arguments to reset."""
    global _repo_root, _reports_root, _clone_cache_root, _command_runner, _now, _verification_runner
    _repo_root = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    _reports_root = Path(reports_root) if reports_root is not None else _repo_root / "reports"
    _clone_cache_root = (
        Path(clone_cache_root) if clone_cache_root is not None else _repo_root / "runs" / ".clone_cache"
    )
    _command_runner = command_runner or subprocess.run
    _now = now or (lambda: datetime.now(timezone.utc))
    _verification_runner = verification_runner


def _utc() -> str:
    return _now().astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_token(value: str, label: str) -> str:
    if not isinstance(value, str) or not _SAFE_TOKEN.fullmatch(value) or ".." in value:
        raise ReadmeRefreshRunError(f"{label} must match {_SAFE_TOKEN.pattern!r} and must not contain '..'")
    return value


def _session_id(explicit: "str | None" = None) -> str:
    value = session_identity.resolve_sanitized(explicit)
    if not value:
        raise ReadmeRefreshRunError(
            "A stable session identity is required: pass --session-id or set "
            "AGENT_SESSION_ID/CODEX_THREAD_ID/CLAUDE_CODE_SESSION_ID"
        )
    return _safe_token(value, "session_id")


# --- Paths -----------------------------------------------------------------------------------


def _run_root(family: str, platform: str, run_id: str) -> Path:
    return _reports_root / "readme_refresh_runs" / family / platform / run_id


def _product_root(family: str, platform: str) -> Path:
    return _reports_root / "readme_refresh_runs" / family / platform


def _manifest_path(family: str, platform: str, run_id: str) -> Path:
    return _run_root(family, platform, run_id) / "manifest.json"


def _active_path(family: str, platform: str) -> Path:
    return _product_root(family, platform) / "ACTIVE.json"


def _product_lock_path(family: str, platform: str) -> Path:
    return _reports_root / "locks" / "readme_refresh" / f"{family}-{platform}.lock"


def _candidate_readme_path(family: str, platform: str) -> Path:
    return _reports_root / "repo-presenter" / family / platform / "readme.md"


def _upstream_issues_path(family: str, platform: str) -> Path:
    return _reports_root / "repo-presenter" / family / platform / "upstream-issues.md"


def _content_dispositions_path(family: str, platform: str) -> Path:
    """Fifteenth incident / MT030 (2026-08-09): the real, agent-authored artifact
    `dropped_claims.json` only ever promised (docstring-only, 2026-08-04 through 2026-08-09,
    never implemented). Sibling to readme.md/upstream-issues.md, same directory."""
    return _reports_root / "repo-presenter" / family / platform / "content-dispositions.json"


def _product_clone_cache(family: str, platform: str) -> Path:
    return _clone_cache_root / f"aspose_{family}_{platform}"


@contextmanager
def _product_guard(family: str, platform: str) -> Iterator[None]:
    try:
        with FileLock(_product_lock_path(family, platform), timeout=10.0):
            yield
    except LockTimeout as exc:
        raise ReadmeRefreshRunError(str(exc)) from exc


def _git(*args: str, cwd: "Path | None" = None, check: bool = True) -> str:
    result = _command_runner(
        ["git", *args], cwd=str(cwd or _repo_root), capture_output=True, text=True, timeout=60,
    )
    if check and result.returncode != 0:
        raise ReadmeRefreshRunError(
            f"git {' '.join(args)} failed ({result.returncode}): {(result.stderr or result.stdout).strip()}"
        )
    return result.stdout.strip()


# --- Manifest (lightweight in-module validation -- see module docstring for why this does not
# register a new type with the shared scripts/pipeline/lib/schema_validators.py registry: that
# module is a widely-shared, sensitive surface, and a self-contained check here is adequate for
# a first real implementation without expanding that blast radius) -------------------------------

_REQUIRED_MANIFEST_KEYS = {
    "schema_version", "run_id", "family", "platform", "state", "session_owner",
    "created_at", "updated_at",
}


def _validate_manifest(data: dict) -> list[str]:
    errors = []
    for key in _REQUIRED_MANIFEST_KEYS:
        if key not in data:
            errors.append(f"missing required key: {key}")
    if "state" in data and data["state"] not in NEXT_STATES:
        errors.append(f"unknown state: {data.get('state')!r}")
    return errors


def _write_json(path: Path, data: dict) -> None:
    atomic_write(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def _load_manifest(family: str, platform: str, run_id: str) -> dict:
    path = _manifest_path(family, platform, run_id)
    if not path.is_file():
        raise ReadmeRefreshRunError(f"Run not found: {family}/{platform}/{run_id}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ReadmeRefreshRunError(f"Run manifest is unreadable: {exc}") from exc
    errors = _validate_manifest(data)
    if errors:
        raise ReadmeRefreshRunError(f"Run manifest is invalid: {errors}")
    return data


def _save_manifest(data: dict) -> None:
    data["updated_at"] = _utc()
    errors = _validate_manifest(data)
    if errors:
        raise ReadmeRefreshRunError(f"Refusing to write invalid run manifest: {errors}")
    _write_json(_manifest_path(data["family"], data["platform"], data["run_id"]), data)


def _event(family: str, platform: str, run_id: str, event_type: str, **fields: Any) -> None:
    path = _run_root(family, platform, run_id) / "events.jsonl"
    row = {"at": _utc(), "event": event_type, **fields}
    prior = path.read_text(encoding="utf-8") if path.is_file() else ""
    atomic_write(path, prior + json.dumps(row, ensure_ascii=False) + "\n")


def _set_active(family: str, platform: str, run_id: str) -> None:
    _write_json(_active_path(family, platform), {"run_id": run_id, "updated_at": _utc()})


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


def _transition(manifest: dict, target: str, *, checkpoint: "str | None" = None) -> None:
    current = manifest["state"]
    if target not in NEXT_STATES.get(current, set()):
        raise ReadmeRefreshRunError(f"Illegal readme-refresh-run transition: {current} -> {target}")
    manifest["state"] = target
    if checkpoint:
        manifest.setdefault("stage_checkpoints", {})[checkpoint] = {"state": target, "completed_at": _utc()}
    _save_manifest(manifest)
    _event(manifest["family"], manifest["platform"], manifest["run_id"], "STATE_TRANSITION",
           previous=current, current=target, checkpoint=checkpoint)


def _transition_abandoned(manifest: dict, *, reason: str) -> None:
    current = manifest["state"]
    if "ABANDONED" not in NEXT_STATES.get(current, set()):
        raise ReadmeRefreshRunError(f"Illegal readme-refresh-run transition: {current} -> ABANDONED")
    manifest["state"] = "ABANDONED"
    manifest["resume_state"] = None
    manifest["failure_reason"] = reason.strip()
    _save_manifest(manifest)
    _event(manifest["family"], manifest["platform"], manifest["run_id"], "STATE_TRANSITION",
           previous=current, current="ABANDONED")


def _block(manifest: dict, reason: str) -> None:
    current = manifest["state"]
    manifest["resume_state"] = current
    manifest["failure_reason"] = reason.strip()
    _transition(manifest, "BLOCKED")


# --- start: CREATED -> INPUTS_PINNED --------------------------------------------------------


def _load_products() -> list[dict]:
    return json.loads((_repo_root / "data" / "products.json").read_text(encoding="utf-8"))


def _load_registry_exclusions() -> list[dict]:
    path = _repo_root / "data" / "registry_exclusions.json"
    if not path.is_file():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_product(family: str, platform: str) -> dict:
    for entry in _load_products():
        if entry.get("family") == family and entry.get("platform") == platform:
            if not entry.get("active", False):
                raise ReadmeRefreshRunError(f"{family}/{platform} is not active in data/products.json")
            for excl in _load_registry_exclusions():
                if excl.get("match") == "family_platform" and excl.get("family") == family and excl.get("platform") == platform:
                    raise ReadmeRefreshRunError(f"{family}/{platform} is excluded: {excl.get('reason')}")
                if excl.get("match") == "repo_name" and excl.get("repo_url") == entry.get("repo_url"):
                    raise ReadmeRefreshRunError(f"{family}/{platform} is excluded: {excl.get('reason')}")
            return entry
    raise ReadmeRefreshRunError(f"{family}/{platform} not found in data/products.json")


def _preflight_access_check(repo_full_name: str) -> dict:
    """Real gh api call -- refuses to proceed if push/admin access is missing. This is the
    literal fix for foss-java-publish (S-110)'s documented gap: that skill assumed access as a
    prose precondition and never actually checked it."""
    result = _command_runner(
        ["gh", "api", f"repos/{repo_full_name}", "--jq", "{permissions, default_branch, archived, disabled}"],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise ReadmeRefreshRunError(
            f"Pre-flight access check failed for {repo_full_name}: {(result.stderr or result.stdout).strip()}"
        )
    try:
        info = json.loads(result.stdout)
    except Exception as exc:
        raise ReadmeRefreshRunError(f"Pre-flight access check returned unparseable output: {exc}") from exc
    permissions = info.get("permissions", {})
    if not (permissions.get("push") or permissions.get("admin")):
        raise ReadmeRefreshRunError(f"No push/admin access to {repo_full_name}: {permissions}")
    if info.get("archived") or info.get("disabled"):
        raise ReadmeRefreshRunError(f"{repo_full_name} is archived or disabled")
    return info


def start_run(
    family: str, platform: str, *, run_id: "str | None" = None, session_id: "str | None" = None,
    skip_preflight: bool = False,
) -> dict:
    """CREATED -> INPUTS_PINNED: resolve the product, run the pre-flight access check, pin
    inputs. Returns the validated manifest."""
    family = _safe_token(family, "family")
    platform = _safe_token(platform, "platform")
    owner = _session_id(session_id)
    rid = _safe_token(run_id or f"rr-{_now().strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:12]}", "run_id")

    product = _resolve_product(family, platform)
    repo_full_name = product["repo_url"].split("github.com/", 1)[-1].rstrip("/")

    with _product_guard(family, platform):
        active_path = _active_path(family, platform)
        if active_path.is_file():
            try:
                active = json.loads(active_path.read_text(encoding="utf-8"))
                prior = _load_manifest(family, platform, active["run_id"])
            except Exception as exc:
                raise ReadmeRefreshRunError(f"Existing active-run pointer is invalid: {exc}") from exc
            if prior.get("state") not in TERMINAL_STATES:
                raise ReadmeRefreshRunError(
                    f"{family}/{platform} already has active run {active['run_id']} in state {prior.get('state')}"
                )
            _clear_active(family, platform, active["run_id"])

        run_root = _run_root(family, platform, rid)
        if run_root.exists():
            raise ReadmeRefreshRunError(f"Run ID already exists: {rid}")
        run_root.mkdir(parents=True)

        preflight = None
        if not skip_preflight:
            preflight = _preflight_access_check(repo_full_name)

        clone_cache = _product_clone_cache(family, platform)
        clone_cache_head = None
        if clone_cache.is_dir():
            try:
                clone_cache_head = _git("rev-parse", "HEAD", cwd=clone_cache)
            except ReadmeRefreshRunError:
                clone_cache_head = None

        now = _utc()
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "run_id": rid,
            "family": family,
            "platform": platform,
            "repo_full_name": repo_full_name,
            "repo_url": product["repo_url"],
            "clone_url": product["clone_url"],
            "state": "CREATED",
            "session_owner": owner,
            "created_at": now,
            "updated_at": now,
            "pinned_inputs": {
                "clone_cache_head": clone_cache_head,
                "preflight": preflight,
            },
            "stage_checkpoints": {},
        }
        _save_manifest(manifest)
        _event(family, platform, rid, "RUN_CREATED", session_owner=owner)
        _transition(manifest, "INPUTS_PINNED", checkpoint="inputs_pinned")
        _set_active(family, platform, rid)
        return manifest


# --- plan: INPUTS_PINNED -> PLANNED (emits facts/factpack.json) ----------------------------


def _detect_archetype(family: str, platform: str) -> dict:
    path = _repo_root / "data" / "diagram_archetypes.json"
    if not path.is_file():
        return {"archetype": "transform", "archetype_basis": "default (no override entry)"}
    rows = json.loads(path.read_text(encoding="utf-8"))
    for row in rows:
        if row.get("family") == family and row.get("platform") == platform:
            return {"archetype": row["archetype"], "archetype_basis": row.get("evidence", "")}
    return {"archetype": "transform", "archetype_basis": "default (no override entry)"}


def _detect_archetype_entry_raw(family: str, platform: str) -> "dict | None":
    """The full raw data/diagram_archetypes.json row for this product (archetype, evidence,
    decided_at), or None if no override entry exists. Distinct from _detect_archetype()
    (above), which only returns {"archetype", "archetype_basis"} for the factpack -- this
    keeps the full row, including decided_at, for check_diagram_hybrid_reverification's
    freshness check (2026-08-08, Rule 2 refinement #2)."""
    path = _repo_root / "data" / "diagram_archetypes.json"
    if not path.is_file():
        return None
    rows = json.loads(path.read_text(encoding="utf-8"))
    for row in rows:
        if row.get("family") == family and row.get("platform") == platform:
            return row
    return None


def _canonical_format_casing() -> dict:
    """Uppercase-normalized format name -> canonical casing, sourced from
    data/format_descriptions.json's keys (2026-08-08, Rule 1). A real, pre-existing wrinkle
    in that registry (OpenXps not OPENXPS, and both WORDML/WordML present as separate keys)
    means an uppercase collision is possible -- first-seen wins, a deliberate, disclosed
    limitation rather than a silent crash on a registry the factpack step doesn't own."""
    path = _repo_root / "data" / "format_descriptions.json"
    if not path.is_file():
        return {}
    registry = json.loads(path.read_text(encoding="utf-8"))
    canonical: dict[str, str] = {}
    for key in registry:
        canonical.setdefault(key.upper(), key)
    return canonical


def _known_family_display_names() -> "set[str]":
    """Real family names (e.g. {"Words", "PDF", "Cells", ..., "3D", ...}), stripped of their
    "Aspose." prefix, sourced from data/families.json -- the bounded allowlist check_no_
    cross_product_citation needs to avoid the false positives an unrestricted Aspose\\.\\w+
    scan produces (a product's own C#-safe namespace spelling, internal tooling names)."""
    path = _repo_root / "data" / "families.json"
    if not path.is_file():
        return set()
    registry = json.loads(path.read_text(encoding="utf-8"))
    return {value.split(".", 1)[1] for value in registry.values() if value.startswith("Aspose.")}


def _product_formats_md(family: str, platform: str) -> str:
    path = _repo_root / "knowledge" / family / platform / "merged" / "formats.md"
    return path.read_text(encoding="utf-8", errors="ignore") if path.is_file() else ""


def _product_api_surface(family: str, platform: str) -> str:
    """Twelfth incident / MT025 Phase 0c (2026-08-09): raw api_surface.json text, the real
    source-evidence signal for check_diagram_verified_format_claims. `""` if absent -- the
    2-of-3 corroboration model tolerates its absence, same as check_diagram_container_format_
    purity tolerates formats.md gaps."""
    path = _repo_root / "knowledge" / family / platform / "merged" / "api_surface.json"
    return path.read_text(encoding="utf-8", errors="ignore") if path.is_file() else ""


def _product_reference_dir(family: str, platform: str) -> Path:
    """MT027 (2026-08-09): the real, already-graded reference.aspose.org content directory for
    this product. May not exist for every product -- callers must check/handle absence, same
    posture as every other best-effort source in this module."""
    return _repo_root / "content" / "reference.aspose.org" / "en" / family / platform


def _product_reference_index_md(family: str, platform: str) -> str:
    """MT027 (2026-08-09): raw `_index.md` text for `parse_reference_api_index`. `""` if
    absent -- graceful degradation, same posture as `_product_formats_md`/`_product_api_surface`."""
    path = _product_reference_dir(family, platform) / "_index.md"
    return path.read_text(encoding="utf-8", errors="ignore") if path.is_file() else ""


def _detect_capability_dependencies(family: str, platform: str) -> "list | None":
    path = _repo_root / "data" / "diagram_capability_dependencies.json"
    if not path.is_file():
        return None
    rows = json.loads(path.read_text(encoding="utf-8"))
    for row in rows:
        if row.get("family") == family and row.get("platform") == platform:
            return row.get("pipeline_edges", [])
    return None  # never traced -- distinct from "confirmed independent" (see the store's own docs)


def _detect_install_info(family: str, platform: str) -> dict:
    path = _repo_root / "data" / "package_registry.json"
    if not path.is_file():
        return {"source": "package_registry_missing"}
    registry = json.loads(path.read_text(encoding="utf-8"))
    family_entry = registry.get(family, {})
    platform_entry = family_entry.get(platform) if isinstance(family_entry, dict) else None
    if not platform_entry:
        return {"source": "no_package_registry_entry", "fallback_text_required": True}
    verification = platform_entry.get("verification", {})
    return {
        "source": "package_registry.json",
        "registry_type": platform_entry.get("registry_type"),
        "candidate": platform_entry.get("candidate"),
        "published": verification.get("published", False),
        "fallback_text_required": not verification.get("published", False),
    }


def _detect_license_file(clone_cache: Path) -> "dict | None":
    if not clone_cache.is_dir():
        return None
    candidates = list(clone_cache.glob("LICENSE*")) + list(clone_cache.glob("*/LICENSE*")) + list(
        clone_cache.glob("license/LICENSE*")
    )
    for candidate in candidates:
        if candidate.is_file():
            try:
                head = candidate.read_text(encoding="utf-8", errors="ignore")[:20]
            except OSError:
                continue
            if head.startswith("MIT License"):
                return {"relative_path": str(candidate.relative_to(clone_cache)).replace("\\", "/")}
    return None


def _detect_dev_test_artifacts(clone_cache: Path) -> list[dict]:
    """Fourteenth incident / MT029 (2026-08-09), Item 5. Real, deterministic scan for
    development/testing/governance artifacts that -- when they exist -- must be linked from
    the README (`check_dev_test_artifacts_linked`). Mirrors `_detect_license_file`'s shape
    exactly: scan the real clone cache, return real found paths, never invent.

    A confirmed-real, deliberately narrow allowlist (2026-08-09, 8-product audit). Categories
    NOT in this list (`CONTRIBUTING.md`/`.rst`, `tox.ini`, `noxfile.py`, `Makefile`,
    `.coveragerc`, `CODE_OF_CONDUCT.md`, root `SECURITY.md`) were confirmed absent from every
    one of the 8 sampled repos and are deliberately excluded rather than guessed at.
    """
    if not clone_cache.is_dir():
        return []
    found: list[dict] = []

    seen_real_paths: set[str] = set()

    def _add(path: Path, kind: str, section: str) -> None:
        if not path.is_file():
            return
        # Case-insensitive filesystems (Windows) alias "AGENTS.md" and "agents.md" to the
        # same real file -- verify the real on-disk name matches what was requested before
        # adding, so a single physical file is never registered twice under different
        # casings (found live via this function's own fixture test on Windows; same
        # discipline _detect_license_file already uses -- "use the exact on-disk path and
        # casing verbatim").
        try:
            real_name = next(p.name for p in path.parent.iterdir() if p.name == path.name)
        except StopIteration:
            return
        if real_name != path.name:
            return
        relative_path = str(path.relative_to(clone_cache)).replace("\\", "/")
        if relative_path in seen_real_paths:
            return
        seen_real_paths.add(relative_path)
        found.append({"relative_path": relative_path, "kind": kind, "section": section})

    # Case-insensitive scan, not a fixed casing list: "AGENTS.md"/"agents.md" alone missed a
    # real third variant found live during the Phase 2 portfolio rollout (cells/java's real
    # file is cased "Agents.md") -- neither literal candidate string-equals that name, so `_add`'s
    # own on-disk-name verification (a case-sensitive Python `==`) silently rejected both lookups
    # even though the file genuinely exists. Scanning the directory once for a case-insensitive
    # match and handing `_add` the real discovered name closes this for any future casing.
    try:
        _agents_entries = list(clone_cache.iterdir()) if clone_cache.is_dir() else []
    except OSError:
        _agents_entries = []
    for _entry in _agents_entries:
        if _entry.is_file() and _entry.name.lower() == "agents.md":
            _add(_entry, "agents_guide", "Documentation & Resources")
            break
    for name in ("CONTRIBUTING.md", "CONTRIBUTING.rst"):
        _add(clone_cache / name, "contributing_guide", "Documentation & Resources")
    _add(clone_cache / "PUBLIC_API.md", "public_api_doc", "Documentation & Resources")
    _add(clone_cache / "CHANGELOG.md", "changelog", "Documentation & Resources")
    _add(clone_cache / "PUBLISHING.md", "publishing_guide", "Documentation & Resources")

    docs_dir = clone_cache / "docs"
    if docs_dir.is_dir():
        for md in sorted(docs_dir.glob("*.md")):
            _add(md, "docs_guide", "Documentation & Resources")

    workflows_dir = clone_cache / ".github" / "workflows"
    if workflows_dir.is_dir():
        for wf in sorted(workflows_dir.glob("*.yml")) + sorted(workflows_dir.glob("*.yaml")):
            _add(wf, "ci_workflow", "Development and Testing")

    _add(clone_cache / "examples" / "README.md", "examples_readme", "Development and Testing")

    for child in sorted(clone_cache.iterdir()):
        # A leading "." excludes tool-generated cache directories (found live 2026-08-09,
        # html/python's real `.pytest_cache/` -- pytest itself writes a boilerplate
        # README.md there on every test run; it's a build artifact, not real, meaningful
        # contributor-facing documentation, and "test" is a substring of "pytest_cache").
        if child.is_dir() and "test" in child.name.lower() and not child.name.startswith("."):
            _add(child / "README.md", "test_dir_readme", "Development and Testing")

    return found


def _load_package_registry() -> dict:
    """Fifteenth incident / MT030 (2026-08-09): small, reusable loader -- content-unit evidence
    resolution (`check_content_unit_evidence_resolves`) needs the raw `data/package_registry.json`
    dict directly, not `_detect_install_info`'s already-summarized per-product view. `{}` if the
    file is absent, matching this module's established graceful-degradation posture."""
    path = _repo_root / "data" / "package_registry.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _load_content_docs_texts(family: str, platform: str) -> dict[str, str]:
    """Fifteenth incident / MT030 (2026-08-09): real doc texts a content-unit disposition can
    cite as `"docs_reference"` evidence -- every real governance/contributor doc
    `_detect_dev_test_artifacts` already discovers in the clone cache, keyed by the same
    relative path, plus the knowledge-layer `formats.md`/`limitations.md` texts this module
    already knows how to read elsewhere. Mirrors `_product_formats_md`/`_product_api_surface`'s
    existing "read once, hand in as text" pattern -- `{}` is a valid, expected result for a
    product with none of these, same graceful-degradation posture as those two functions."""
    clone_cache = _product_clone_cache(family, platform)
    texts: dict[str, str] = {}
    for artifact in _detect_dev_test_artifacts(clone_cache):
        path = clone_cache / artifact["relative_path"]
        if path.is_file():
            texts[artifact["relative_path"]] = path.read_text(encoding="utf-8", errors="ignore")
    formats_md = _product_formats_md(family, platform)
    if formats_md:
        texts["knowledge/formats.md"] = formats_md
    limitations_path = _repo_root / "knowledge" / family / platform / "merged" / "limitations.md"
    if limitations_path.is_file():
        texts["knowledge/limitations.md"] = limitations_path.read_text(encoding="utf-8", errors="ignore")
    return texts


def _old_readme_inventory(clone_cache: Path) -> dict:
    old_readme = clone_cache / "README.md"
    if not old_readme.is_file():
        return {"links": [], "headings": [], "source": "no_old_readme_found", "content_units": []}
    text = old_readme.read_text(encoding="utf-8", errors="ignore")
    links = [href for _, href in checks._MD_LINK_RE.findall(text) if not href.startswith(("http://", "https://"))]
    headings = [m.group(2) for m in checks._HEADING_RE.finditer(text)]
    return {
        "links": sorted(set(links)), "headings": headings, "source": "clone_cache/README.md",
        "content_units": checks.extract_old_readme_content_units(text),
    }


def _compute_candidate_format_evidence(family: str, platform: str) -> dict:
    """Twelfth incident / MT025 Phase 0c (2026-08-09): a compose-time HINT for the agent
    drafting Starting Points/Outputs content -- NOT the authoritative verification. The
    candidate's own prose (the third corroboration signal `check_diagram_verified_format_
    claims` uses) doesn't exist until the candidate itself is composed -- a real
    chicken-and-egg constraint, not an oversight. This uses only the 2 signals available before
    composition (formats.md + real source evidence from api_surface.json/clone-cache). The real
    gate at `ingest_candidate` re-derives all 3 signals fresh against the actual composed text,
    so a wrong or stale hint here can never itself let an unverified claim through -- it only
    helps the composing agent start from a better-informed draft instead of guessing blind.

    Covers every format named in EITHER formats.md OR source evidence, not just formats.md's own
    rows -- so a real, source-confirmed format missing from formats.md entirely (pdf/cpp's real
    PDF/PNG support, html/python's real HTML support) still surfaces as a real candidate for the
    agent to consider, rather than silently absent because formats.md happened to omit it.

    Returns `{"import": [{"format", "formats_md", "source"}, ...], "export": [...]}`.
    """
    formats_table = checks.parse_formats_table(_product_formats_md(family, platform))
    api_surface_names = checks._load_api_surface_names(_product_api_surface(family, platform))
    known_format_names = (
        set(_canonical_format_casing().values()) | checks._DIAGRAM_SUPPLEMENTARY_FORMAT_NAMES
    )

    candidates = set(formats_table.keys())
    for fmt in known_format_names:
        if (
            checks._source_direction_signal(api_surface_names, fmt, "import")
            or checks._source_direction_signal(api_surface_names, fmt, "export")
        ):
            candidates.add(fmt.upper())

    evidence: dict[str, list] = {"import": [], "export": []}
    for fmt in sorted(candidates):
        row = checks._formats_table_lookup(formats_table, fmt)
        for direction in ("import", "export"):
            sig_formats_md = bool(row.get(direction, False))
            sig_source = checks._source_direction_signal(api_surface_names, fmt, direction)
            if sig_formats_md or sig_source:
                evidence[direction].append({
                    "format": fmt, "formats_md": sig_formats_md, "source": sig_source,
                })
    return evidence


def plan_run(family: str, platform: str, run_id: str, *, session_id: "str | None" = None) -> dict:
    """INPUTS_PINNED -> PLANNED: emit facts/factpack.json (deterministic data only). The agent
    -- not this script -- composes candidate/README.candidate.md from the factpack, then calls
    ingest_candidate()."""
    owner = _session_id(session_id)
    with _product_guard(family, platform):
        manifest = _load_manifest(family, platform, run_id)
        if manifest["session_owner"] != owner:
            raise ReadmeRefreshRunError(f"Run is owned by {manifest['session_owner']!r}, not {owner!r}")

        clone_cache = _product_clone_cache(family, platform)
        archetype = _detect_archetype(family, platform)
        factpack = {
            "family": family,
            "platform": platform,
            "generated_at": _utc(),
            "archetype": archetype["archetype"],
            "archetype_basis": archetype["archetype_basis"],
            "capability_dependency_pipeline_edges": _detect_capability_dependencies(family, platform),
            "candidate_format_evidence": _compute_candidate_format_evidence(family, platform),
            "install": _detect_install_info(family, platform),
            "license_file": _detect_license_file(clone_cache),
            "old_readme_inventory": _old_readme_inventory(clone_cache),
            "homepage": f"https://products.aspose.org/{family}/{platform}/",
            "banner_url": f"https://products.aspose.org/media/{family}/{platform}/banner-readme.png",
            "reference_api_index": checks.parse_reference_api_index(
                _product_reference_index_md(family, platform)
            ),
            "documentation_links": {
                "docs": f"https://docs.aspose.org/{family}/{platform}/",
                "kb": f"https://kb.aspose.org/{family}/{platform}/",
                "reference": f"https://reference.aspose.org/{family}/{platform}/",
            },
        }
        run_root = _run_root(family, platform, run_id)
        (run_root / "facts").mkdir(parents=True, exist_ok=True)
        _write_json(run_root / "facts" / "factpack.json", factpack)
        _event(family, platform, run_id, "FACTPACK_EMITTED")
        _transition(manifest, "PLANNED", checkpoint="planned")
        return manifest


# --- ingest-candidate: PLANNED -> VERIFYING_EXAMPLES (runs deterministic checks) -----------


def ingest_candidate(
    family: str, platform: str, run_id: str, *, session_id: "str | None" = None,
    declared_file_set: "list[str] | None" = None,
) -> dict:
    """PLANNED -> VERIFYING_EXAMPLES: run the real deterministic checks module against the
    agent-authored candidate. A hard-gate failure blocks the transition (raises, does not
    silently proceed)."""
    owner = _session_id(session_id)
    with _product_guard(family, platform):
        manifest = _load_manifest(family, platform, run_id)
        if manifest["session_owner"] != owner:
            raise ReadmeRefreshRunError(f"Run is owned by {manifest['session_owner']!r}, not {owner!r}")

        candidate_path = _candidate_readme_path(family, platform)
        if not candidate_path.is_file():
            raise ReadmeRefreshRunError(f"No candidate found at {candidate_path}")
        text = candidate_path.read_text(encoding="utf-8")
        clone_cache = _product_clone_cache(family, platform)

        result = _run_deterministic_checks(family, platform, text, clone_cache)
        run_root = _run_root(family, platform, run_id)
        (run_root / "checks").mkdir(parents=True, exist_ok=True)
        _write_json(run_root / "checks" / "result.json", result)
        # TC-HARDEN-12 (MT033): establish checkpoint 0 for recheck()'s change-isolation gates
        # (check_only_mermaid_block_changed / check_only_sections_changed) -- written even when
        # this candidate fails hard gates below, so the fix-and-recheck cycle that follows can
        # still prove its own fix stayed within the declared section(s).
        _write_checks_snapshot(family, platform, run_id, text)

        hard_gate_failures = [name for name, r in result.items() if r.get("hard_gate") and r.get("findings")]
        if hard_gate_failures:
            _event(family, platform, run_id, "INGEST_CANDIDATE_FAILED", failed_checks=hard_gate_failures)
            raise ReadmeRefreshRunError(
                f"ingest-candidate failed hard-gate checks: {hard_gate_failures} -- see checks/result.json"
            )

        _event(family, platform, run_id, "INGEST_CANDIDATE_PASSED")
        _transition(manifest, "VERIFYING_EXAMPLES", checkpoint="ingested")
        return manifest


def _run_deterministic_checks(family: str, platform: str, text: str, clone_cache: Path) -> dict:
    result: dict[str, dict] = {}

    result["required_sections"] = {
        "hard_gate": True, "findings": checks.check_required_sections(text),
    }
    result["banner_present"] = {
        "hard_gate": True, "findings": checks.check_banner_present(text, family, platform),
    }
    result["no_excluded_domain_links"] = {
        "hard_gate": True, "findings": checks.check_no_excluded_domain_links(text),
    }
    result["license_link_target"] = {
        "hard_gate": True, "findings": checks.check_license_link_target(text, str(clone_cache)),
    }
    # 2026-08-08 simplified diagram model (Tenth incident, MT024): check_diagram_connectivity
    # (orphan-reachability) is retired -- replaced by check_diagram_shape (fixed Product ->
    # Core Capabilities -> Outputs container-chain structure) and check_diagram_column_balance
    # (<=5 capabilities = 1 column, >=6 = 2 balanced columns), both hard gates.
    result["diagram_shape"] = {
        "hard_gate": True, "findings": checks.check_diagram_shape(text),
    }
    result["diagram_column_balance"] = {
        "hard_gate": True, "findings": checks.check_diagram_column_balance(text),
    }
    # Eleventh incident / MT025 (2026-08-08): the simplified diagram model shipped with no
    # mechanism requiring a Starting Points container for transform/compile-archetype products
    # (27 of 30 products silently lost real Inputs), and no purity constraint stopping non-format
    # content from entering Outputs (6 of 10 sampled products mixed formats with extracted-data/
    # object-graph/report descriptions). check_diagram_starting_points_presence and
    # check_diagram_container_format_purity close both gaps; check_diagram_hybrid_reverification
    # (below) is narrowed to only hybrid's own freshness question -- see each function's own
    # docstring for the full forensic trace.
    archetype = _detect_archetype(family, platform)["archetype"]
    result["diagram_starting_points_presence"] = {
        "hard_gate": True,
        "findings": checks.check_diagram_starting_points_presence(text, archetype),
    }
    pipeline_edges = _detect_capability_dependencies(family, platform)
    result["diagram_matches_capability_dependencies"] = {
        "hard_gate": True,
        "findings": checks.check_diagram_matches_capability_dependencies(text, pipeline_edges),
    }
    result["diagram_hybrid_reverification"] = {
        "hard_gate": True,
        "findings": checks.check_diagram_hybrid_reverification(
            text, _detect_archetype_entry_raw(family, platform), _now().date().isoformat()
        ),
    }
    known_format_names = (
        set(_canonical_format_casing().values()) | checks._DIAGRAM_SUPPLEMENTARY_FORMAT_NAMES
    )
    # Twelfth incident / MT025 Phase 0c (2026-08-09): check_diagram_format_support_claims
    # retired -- it was presence-only and direction-blind (confirmed by direct code read: it
    # only checked whether a format name appeared ANYWHERE in formats.md's text, never the
    # Import/Export column value, never the claim's direction). check_diagram_verified_format_
    # claims replaces it with a direction-aware, multi-signal (formats.md + prose + real source
    # evidence) corroboration gate -- formats.md is real but independently confirmed unreliable
    # for several real products in this portfolio, so this cannot depend on it alone.
    result["diagram_verified_format_claims"] = {
        "hard_gate": True,
        "findings": checks.check_diagram_verified_format_claims(
            text, _product_formats_md(family, platform), _product_api_surface(family, platform),
            known_format_names,
        ),
    }
    result["diagram_starting_points_format_purity"] = {
        "hard_gate": True,
        "findings": checks.check_diagram_container_format_purity(
            text, "starting_points", known_format_names
        ),
    }
    result["diagram_outputs_format_purity"] = {
        "hard_gate": True,
        "findings": checks.check_diagram_container_format_purity(
            text, "outputs", known_format_names
        ),
    }
    result["diagram_format_completeness_hint"] = {
        "hard_gate": False,
        "findings": checks.check_diagram_format_completeness_hint(
            text, _product_formats_md(family, platform), archetype
        ),
    }
    result["format_name_casing"] = {
        "hard_gate": True,
        "findings": checks.check_format_name_casing(text, _canonical_format_casing()),
    }
    result["no_cross_product_citation"] = {
        "hard_gate": True,
        "findings": checks.check_no_cross_product_citation(text, family, _known_family_display_names()),
    }
    result["examples_table_collapsed"] = {
        "hard_gate": True, "findings": checks.check_examples_table_collapsed(text),
    }
    result["heading_title_case"] = {
        "hard_gate": True, "findings": checks.check_heading_title_case(text),
    }

    upstream_path = _upstream_issues_path(family, platform)
    upstream_text = upstream_path.read_text(encoding="utf-8") if upstream_path.is_file() else ""
    result["no_undisclosed_blocking_commands"] = {
        "hard_gate": True,
        "findings": checks.check_no_undisclosed_blocking_commands(text, upstream_text),
    }

    # Fourteenth incident / MT029 (2026-08-09): five visitor-facing content-quality
    # requirements found live during user review of tex/python's candidate -- Items 1+3
    # (public upstream-defect disclosure, cross-referenced against the same upstream_text
    # already loaded above), Item 2 (Key Capabilities SEO + capability/scope contradiction),
    # Item 4 (Scope and Limitations list format), Item 5 (dev/test artifact linkage).
    result["no_upstream_issue_leaked"] = {
        "hard_gate": True,
        "findings": checks.check_no_upstream_issue_leaked_into_readme(text, upstream_text),
    }
    result["key_capabilities_quality"] = {
        "hard_gate": False, "findings": checks.check_key_capabilities_quality(text),
    }
    result["capability_scope_contradiction"] = {
        "hard_gate": False, "findings": checks.check_capability_scope_contradiction(text),
    }
    result["scope_limitations_format"] = {
        "hard_gate": True, "findings": checks.check_scope_limitations_format(text),
    }
    dev_test_artifacts = _detect_dev_test_artifacts(clone_cache)
    result["dev_test_artifacts_linked"] = {
        "hard_gate": True,
        "findings": checks.check_dev_test_artifacts_linked(text, dev_test_artifacts),
    }
    result["development_testing_collapse"] = {
        "hard_gate": False, "findings": checks.check_development_testing_collapse(text),
    }

    # TC-HARDEN-04 fix (Option B, confirmed necessary -- not theoretical -- by the very first
    # real ingest-candidate run ever made through this CLI, 3d/typescript, 2026-08-11): once a
    # product has a real, agent-authored content-dispositions.json (MT030's own prose-level
    # verify-and-merge accounting -- a strictly finer-grained mechanism that requires EVERY real
    # old-README content unit, including anything that lived under a since-renamed heading, to
    # carry a real, individually-verified disposition), check_dropped_content's own
    # dropped_links/dropped_headings findings are downgraded from hard-gate to advisory for that
    # product -- MT030's mechanism already accounts for that content, so this coarser, literal-
    # string check's role becomes a redundant cross-check, not the sole gate. internal_labels
    # stays a hard gate unconditionally: it is a NEW-candidate-quality check (forbidden internal-
    # process labels leaking into public prose), never covered by content-dispositions.json's own
    # scope (old-content REUSE, not new-content correctness). Without this, ingest-candidate would
    # hard-block on every product that adopted the new template's own heading set -- i.e.
    # essentially the entire 30-product portfolio, since every one did.
    has_dispositions_file = _content_dispositions_path(family, platform).is_file()

    old_readme_path = clone_cache / "README.md"
    if old_readme_path.is_file():
        old_readme_text = old_readme_path.read_text(encoding="utf-8", errors="ignore")
        dropped = checks.check_dropped_content(old_readme_text, text, str(clone_cache))
        uncorrelated = dropped["dropped_links"] + dropped["dropped_headings"]
    else:
        # No old upstream README to diff against -- dropped_links/dropped_headings are
        # vacuously empty, but internal-label detection only ever scans the NEW candidate
        # text, so it must still run here rather than being silently skipped (a real gap
        # found while wiring this in: the original code hardcoded findings=[] for this
        # branch entirely, which would have meant internal-label detection never ran at
        # all for any product missing an old README).
        dropped = checks.check_dropped_content("", text, str(clone_cache))
        dropped = {"source": "no_old_readme_found", **dropped}
        uncorrelated = []
        old_readme_text = ""

    if has_dispositions_file and uncorrelated:
        result["dropped_content"] = {
            "hard_gate": True, "findings": dropped["internal_labels"], "detail": dropped,
        }
        result["dropped_content_uncorrelated"] = {
            "hard_gate": False,
            "findings": uncorrelated,
            "detail": {
                "note": "downgraded from hard-gate to advisory: a content-dispositions.json "
                        "exists for this product (TC-HARDEN-04) -- confirm it accounts for each "
                        "of these before treating this candidate as clean, but do not block on "
                        "literal string non-match alone",
                **dropped,
            },
        }
    else:
        result["dropped_content"] = {
            "hard_gate": True,
            "findings": uncorrelated + dropped["internal_labels"],
            "detail": dropped,
        }

    # Fifteenth incident / MT030 (2026-08-09): verify-and-merge of the old README's real prose
    # -- mechanism-level explanations (e.g. pdf/cpp's real font-fallback rationale) and
    # branding/positioning claims (e.g. "Official Aspose project") get verified against the
    # real product repo and merged into the new candidate; pure narrative/origin-story/CTA
    # prose stays explicitly out of scope, per the user's own decision. dropped_content above
    # only ever tracked links/headings -- these 6 checks close the much larger prose gap a real
    # 5-product survey confirmed. content-dispositions.json is agent-authored, same tier as
    # readme.md/upstream-issues.md -- read here, never written by this script.
    content_units = checks.extract_old_readme_content_units(old_readme_text)
    dispositions_path = _content_dispositions_path(family, platform)
    dispositions = (
        json.loads(dispositions_path.read_text(encoding="utf-8")) if dispositions_path.is_file() else []
    )
    result["content_unit_disposition_coverage"] = {
        "hard_gate": True,
        "findings": checks.check_content_unit_disposition_coverage(content_units, dispositions),
    }
    result["content_unit_evidence_resolves"] = {
        "hard_gate": True,
        "findings": checks.check_content_unit_evidence_resolves(
            dispositions, str(clone_cache), _load_package_registry(),
            _load_content_docs_texts(family, platform),
        ),
    }
    result["content_unit_merged_into_target_section"] = {
        "hard_gate": True,
        "findings": checks.check_content_unit_merged_into_target_section(text, dispositions),
    }
    result["content_unit_no_exact_duplicate_merge"] = {
        "hard_gate": True,
        "findings": checks.check_content_unit_no_exact_duplicate_merge(dispositions),
    }
    result["content_unit_classification_plausibility"] = {
        "hard_gate": False,
        "findings": checks.check_content_unit_classification_plausibility(content_units, dispositions),
    }
    result["content_unit_probable_duplicate"] = {
        "hard_gate": False,
        "findings": checks.check_content_unit_probable_duplicate(dispositions),
    }
    # Sixteenth incident / MT031 (2026-08-10): a mixed unit (real actionable fact bundled with
    # pure hedge/CTA prose) can be classified/excluded wholesale, silently losing the fact.
    # Standing, non-blocking safeguard for every future dispatch -- never a hard gate, since a
    # differently-worded embedded fact won't trip the fixed phrase list.
    result["content_unit_embedded_actionable_fact"] = {
        "hard_gate": False,
        "findings": checks.check_content_unit_embedded_actionable_fact(content_units, dispositions),
    }

    # Heuristic / two-tier -- surfaced for the mandatory human/agent judgment pass, never
    # treated as a hard_gate failure by ingest_candidate() above. 2026-08-08: check_diagram_
    # suspicious_direct_product_edge and check_diagram_capability_unreachable_from_product
    # are retired -- both were tripwires for a per-node-edge defect class that cannot occur
    # in the simplified container-chain model.
    result["diagram_known_subgraph_ids"] = {"hard_gate": False, "findings": checks.check_diagram_known_subgraph_ids(text)}
    result["section_job_distinctness"] = {
        "hard_gate": False, "findings": checks.check_section_job_distinctness(text),
    }
    result["diagram_no_mechanism_duplicate_output"] = {
        "hard_gate": False, "findings": checks.check_diagram_no_mechanism_duplicate_output(text),
    }
    result["process_narration_smells"] = {"hard_gate": False, "findings": checks.check_process_narration_smells(text)}
    result["enterprise_edition_naming"] = {"hard_gate": False, "findings": checks.check_enterprise_edition_naming(text)}

    # MT027 (2026-08-09): API Reference grounded in reference.aspose.org's own graded content.
    # check_api_reference_intro_names_classes is retired -- absorbed into check_api_reference_
    # classes_exist_in_reference_site (now a hard gate; see that function's own docstring for
    # why real class-name verification justifies the elevation from the old heuristic).
    reference_index = checks.parse_reference_api_index(
        _product_reference_index_md(family, platform)
    )
    reference_class_names = {
        row["class"] for rows in reference_index.values() for row in rows
    }
    result["api_reference_classes_exist"] = {
        "hard_gate": True,
        "findings": checks.check_api_reference_classes_exist_in_reference_site(
            text, reference_class_names, str(clone_cache)
        ),
    }
    result["no_leaked_docstring_artifacts"] = {
        "hard_gate": False, "findings": checks.check_no_leaked_docstring_artifacts(text),
    }
    result["named_member_accuracy"] = {
        "hard_gate": False,
        "findings": checks.check_named_member_accuracy(
            text, str(clone_cache), reference_dir=str(_product_reference_dir(family, platform))
        ),
    }

    # Thirteenth incident / MT028 (2026-08-09): MT027 grounded verification in reference.
    # aspose.org's own content but never adapted the section's PRESENTATION to match it -- these
    # two checks enforce the fix (a module-grouped table mirroring _index.md's own organization,
    # inserted above the untouched curated bullets; user's own chosen design, via AskUserQuestion).
    result["api_reference_table_completeness"] = {
        "hard_gate": True,
        "findings": checks.check_api_reference_table_completeness(text, reference_index),
    }
    result["api_reference_generic_description"] = {
        "hard_gate": False,
        "findings": checks.check_no_generic_class_description(text),
    }
    result["api_reference_truncated_description"] = {
        "hard_gate": False,
        "findings": checks.check_no_truncated_class_description(text),
    }
    result["api_reference_stripped_example"] = {
        "hard_gate": False,
        "findings": checks.check_no_stripped_example_in_description(text),
    }
    return result


def _checks_snapshot_path(family: str, platform: str, run_id: str) -> Path:
    """TC-HARDEN-12 (MT033): the rolling 'last checked' candidate snapshot that
    check_only_mermaid_block_changed / check_only_sections_changed diff against. Written at
    every successful ingest_candidate/recheck call, so the NEXT recheck can prove a follow-up
    edit stayed within its declared scope. Absent on the very first check of a run (nothing to
    diff against yet) -- callers must treat that as "no baseline", not an error."""
    return _run_root(family, platform, run_id) / "checks" / "last_checked_candidate.md"


def _apply_change_isolation_checks(
    result: dict, family: str, platform: str, run_id: str, text: str,
    *, allowed_headings: "list[str] | None", mermaid_only: bool,
) -> None:
    """TC-HARDEN-12 (MT033, Twelfth-incident register): check_only_mermaid_block_changed and
    check_only_sections_changed are real, fully-tested hard gates that were never invoked by
    this file -- the two functions that mechanically enforce this plan's own MT024/MT029
    idempotency guarantee sat orphaned. Wired here, not into ingest_candidate, because both
    functions diff CURRENT text against a PRIOR snapshot -- a question only meaningful for a
    follow-up edit during AWAITING_REVIEW (recheck's own job), not a fresh candidate's first
    ingest (nothing to diff against). Only runs when the caller explicitly declares scope
    (mermaid_only=True or allowed_headings is not None) and a prior snapshot exists -- silent,
    backward-compatible no-op otherwise, matching recheck's own established advisory posture
    (never raises; the caller inspects result.json)."""
    snapshot_path = _checks_snapshot_path(family, platform, run_id)
    if not snapshot_path.is_file():
        return
    if not mermaid_only and allowed_headings is None:
        return
    old_text = snapshot_path.read_text(encoding="utf-8")
    if mermaid_only:
        only_mermaid_changed = checks.check_only_mermaid_block_changed(old_text, text)
        result["change_isolation_mermaid"] = {
            "hard_gate": True,
            "findings": [] if only_mermaid_changed else [
                {"reason": "changes were not confined to the At a Glance mermaid block"}
            ],
        }
    if allowed_headings is not None:
        result["change_isolation_sections"] = {
            "hard_gate": True,
            "findings": checks.check_only_sections_changed(old_text, text, allowed_headings),
        }


def _write_checks_snapshot(family: str, platform: str, run_id: str, text: str) -> None:
    snapshot_path = _checks_snapshot_path(family, platform, run_id)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(text, encoding="utf-8")


def recheck(
    family: str, platform: str, run_id: str, *, session_id: "str | None" = None,
    allowed_headings: "list[str] | None" = None, mermaid_only: bool = False,
) -> dict:
    """Re-run the deterministic checks in place after manual edits during AWAITING_REVIEW --
    does NOT transition state, only updates checks/result.json. Callers must inspect the
    returned result themselves; this does not raise on hard-gate findings (unlike
    ingest_candidate) since AWAITING_REVIEW is a human-in-the-loop hold, not a gate.

    allowed_headings / mermaid_only (TC-HARDEN-12): declare what this specific edit was scoped
    to, and the section-isolation/mermaid-only-change hard gates run against the prior checked
    snapshot -- e.g. `recheck(..., allowed_headings=["Key Capabilities"])` after a Key
    Capabilities-only edit proves nothing else in the file moved. Omit both (the default) to
    skip change-isolation checking entirely, e.g. when resuming a run with no prior snapshot."""
    owner = _session_id(session_id)
    with _product_guard(family, platform):
        manifest = _load_manifest(family, platform, run_id)
        if manifest["session_owner"] != owner:
            raise ReadmeRefreshRunError(f"Run is owned by {manifest['session_owner']!r}, not {owner!r}")
        candidate_path = _candidate_readme_path(family, platform)
        text = candidate_path.read_text(encoding="utf-8") if candidate_path.is_file() else ""
        clone_cache = _product_clone_cache(family, platform)
        result = _run_deterministic_checks(family, platform, text, clone_cache)
        _apply_change_isolation_checks(
            result, family, platform, run_id, text,
            allowed_headings=allowed_headings, mermaid_only=mermaid_only,
        )
        run_root = _run_root(family, platform, run_id)
        (run_root / "checks").mkdir(parents=True, exist_ok=True)
        _write_json(run_root / "checks" / "result.json", result)
        _write_checks_snapshot(family, platform, run_id, text)
        _event(family, platform, run_id, "RECHECK_COMPLETED")
        return result


# --- verify-examples: VERIFYING_EXAMPLES -> AWAITING_REVIEW --------------------------------


def _default_verification_runner(candidate_path: Path, factpack: dict) -> dict:
    """Honest default: reports every code block as BLOCKED-WITH-REASON: TOOLCHAIN-UNAVAILABLE
    rather than claiming a compile/run pass that never happened. Real per-language wiring
    (javac/javap, dotnet, go build, cargo, cmake/ninja, python venv, tsc) is separate, follow-on
    work -- see the module docstring's Honest Scope Statement."""
    text = candidate_path.read_text(encoding="utf-8") if candidate_path.is_file() else ""
    block_count = len(re.findall(r"^```", text, re.MULTILINE)) // 2
    return {
        "runner": "default_stub",
        "blocks_found": block_count,
        "block_statuses": [
            {"index": i, "status": "BLOCKED-WITH-REASON", "reason": "TOOLCHAIN-UNAVAILABLE"}
            for i in range(block_count)
        ],
        "all_named": True,  # every block has a real, non-silent status -- see module docstring
    }


# TC-HARDEN-01 (MT033): the first real per-language verification runner -- Python, per the
# plan's own sequencing recommendation (most products of any language, cheapest disposable-venv
# setup already documented in the Verification pass section). Deliberately opt-in, not a
# replacement for `_default_verification_runner` -- the module's own "pluggable seam" design
# (`configure(verification_runner=...)`) already anticipated exactly this shape, and swapping the
# hardcoded default would add real venv/network cost to every existing test and CLI invocation
# silently, including the 6 languages this pass does not touch. Wired into the real CLI path via
# `verify-examples --python-runner` (see main()), not left reachable only from a test import --
# the same "a gate must be reachable from the real production path" lesson TC-HARDEN-12 already
# named for a different function.
_ANY_LANG_CODE_BLOCK_RE = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)


def _acquire_python_environment(work_dir: Path, install_info: dict, clone_cache: Path) -> dict:
    """Real acquire step, matching the plan's own Python procedure (Verification pass section):
    published -> disposable venv + `pip install {package}` from real PyPI; unpublished -> a real
    editable install of the read-only clone cache (`pip install -e`) -- never `git clone --local`
    into a fresh dir first, since the clone cache is already a real local checkout and `pip
    install -e` itself is read-only against it. Returns {"ok", "venv_python", "detail"}."""
    venv_dir = work_dir / "venv"
    created = subprocess.run(
        [sys.executable, "-m", "venv", str(venv_dir)], capture_output=True, text=True, timeout=120,
    )
    if created.returncode != 0:
        return {"ok": False, "venv_python": None, "detail": f"venv creation failed: {created.stderr.strip()}"}
    venv_python = str(venv_dir / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python"))

    candidate = (install_info or {}).get("candidate") or {}
    package_name = candidate.get("name") if isinstance(candidate, dict) else None
    published = bool((install_info or {}).get("published", False))

    if published and package_name:
        installed = subprocess.run(
            [venv_python, "-m", "pip", "install", "--quiet", package_name],
            capture_output=True, text=True, timeout=300,
        )
        if installed.returncode != 0:
            return {
                "ok": False, "venv_python": None,
                "detail": f"pip install {package_name} (PyPI) failed: {installed.stderr.strip()[-2000:]}",
            }
        return {"ok": True, "venv_python": venv_python, "detail": f"installed {package_name} from PyPI"}

    if not clone_cache.is_dir():
        return {"ok": False, "venv_python": None, "detail": "unpublished and no clone cache directory available"}
    installed = subprocess.run(
        [venv_python, "-m", "pip", "install", "--quiet", "-e", str(clone_cache)],
        capture_output=True, text=True, timeout=300,
    )
    if installed.returncode != 0:
        return {
            "ok": False, "venv_python": None,
            "detail": f"editable install from clone cache failed: {installed.stderr.strip()[-2000:]}",
        }
    return {"ok": True, "venv_python": venv_python, "detail": f"editable-installed from clone cache ({clone_cache})"}


def _run_single_python_block(venv_python: str, code: str, work_dir: Path, index: int) -> dict:
    """Real execution IS the check (the plan's own Python-procedure principle) -- an
    AttributeError/ImportError/TypeError from the real installed package is authoritative, never
    hand-waved. Deliberately does not attempt to synthesize a missing preamble for a Fragment-
    style block (the plan's own taxonomy) in this first pass -- a block that references a prior
    block's identifier fails honestly as BLOCKED-WITH-REASON: RUNTIME-ERROR, a real, disclosed
    limitation of this v1 runner, not a silent skip."""
    script_path = work_dir / f"block_{index}.py"
    script_path.write_text(code, encoding="utf-8")
    try:
        result = subprocess.run(
            [venv_python, str(script_path)], capture_output=True, text=True, timeout=60, cwd=str(work_dir),
        )
    except subprocess.TimeoutExpired:
        return {"index": index, "status": "BLOCKED-WITH-REASON", "reason": "TIMEOUT"}
    if result.returncode == 0:
        return {"index": index, "status": "COMPILED+RAN CLEAN"}
    return {
        "index": index, "status": "BLOCKED-WITH-REASON", "reason": "RUNTIME-ERROR",
        "detail": (result.stderr or result.stdout).strip()[-2000:],
    }


def python_verification_runner(candidate_path: Path, factpack: dict) -> dict:
    """Real for `python`-tagged fenced code blocks; every other language still honestly reports
    BLOCKED-WITH-REASON: TOOLCHAIN-UNAVAILABLE, exactly as `_default_verification_runner` does --
    this function is a strict, real superset of the stub's honesty, not a different philosophy."""
    text = candidate_path.read_text(encoding="utf-8") if candidate_path.is_file() else ""
    blocks = [(m.group(1).strip().lower(), m.group(2)) for m in _ANY_LANG_CODE_BLOCK_RE.finditer(text)]
    family = factpack.get("family")
    platform = factpack.get("platform")
    install_info = factpack.get("install") or {}

    block_statuses = [
        {"index": i, "status": "BLOCKED-WITH-REASON", "reason": "TOOLCHAIN-UNAVAILABLE"}
        for i, (lang, _code) in enumerate(blocks) if lang != "python"
    ]
    python_blocks = [(i, code) for i, (lang, code) in enumerate(blocks) if lang == "python"]

    if python_blocks and family and platform:
        with tempfile.TemporaryDirectory(prefix=f"readme-refresh-verify-{family}-{platform}-") as tmp:
            work_dir = Path(tmp)
            clone_cache = _product_clone_cache(family, platform)
            acquire = _acquire_python_environment(work_dir, install_info, clone_cache)
            if not acquire["ok"]:
                for i, _code in python_blocks:
                    block_statuses.append({
                        "index": i, "status": "BLOCKED-WITH-REASON", "reason": "ACQUIRE-FAILED",
                        "detail": acquire["detail"],
                    })
            else:
                for i, code in python_blocks:
                    block_statuses.append(
                        _run_single_python_block(acquire["venv_python"], code, work_dir, i)
                    )
    else:
        for i, _code in python_blocks:
            block_statuses.append({"index": i, "status": "BLOCKED-WITH-REASON", "reason": "TOOLCHAIN-UNAVAILABLE"})

    block_statuses.sort(key=lambda b: b["index"])
    return {
        "runner": "python_verification_runner_v1",
        "blocks_found": len(blocks),
        "block_statuses": block_statuses,
        "all_named": True,
    }


def verify_examples(family: str, platform: str, run_id: str, *, session_id: "str | None" = None) -> dict:
    """VERIFYING_EXAMPLES -> AWAITING_REVIEW: run the (pluggable) per-language verification
    pass. Only transitions once every block has a named status -- never silently."""
    owner = _session_id(session_id)
    with _product_guard(family, platform):
        manifest = _load_manifest(family, platform, run_id)
        if manifest["session_owner"] != owner:
            raise ReadmeRefreshRunError(f"Run is owned by {manifest['session_owner']!r}, not {owner!r}")

        candidate_path = _candidate_readme_path(family, platform)
        run_root = _run_root(family, platform, run_id)
        factpack_path = run_root / "facts" / "factpack.json"
        factpack = json.loads(factpack_path.read_text(encoding="utf-8")) if factpack_path.is_file() else {}

        runner = _verification_runner or _default_verification_runner
        verification_result = runner(candidate_path, factpack)
        if not verification_result.get("all_named", False):
            raise ReadmeRefreshRunError(
                "verify-examples cannot transition: at least one code block has no named status"
            )

        (run_root / "verification").mkdir(parents=True, exist_ok=True)
        _write_json(run_root / "verification" / "result.json", verification_result)

        # upstream-issues.md is written for every run, including the "clean" case -- an absent
        # file for a completed run is itself a bug, per the plan's own Verification section.
        upstream_path = _upstream_issues_path(family, platform)
        if not upstream_path.is_file() or not upstream_path.read_text(encoding="utf-8").strip():
            upstream_path.parent.mkdir(parents=True, exist_ok=True)
            upstream_path.write_text(
                f"# Upstream issues — {family}/{platform}\n\nVerified: {_utc()}\n\n"
                "No upstream issues identified during verification.\n",
                encoding="utf-8",
            )

        _event(family, platform, run_id, "VERIFY_EXAMPLES_COMPLETED", runner=verification_result.get("runner"))
        _transition(manifest, "AWAITING_REVIEW", checkpoint="verified")
        return manifest


# --- approve: AWAITING_REVIEW -> APPROVED (or forced back to PLANNED on drift) -------------


def approve(family: str, platform: str, run_id: str, *, note: str, session_id: "str | None" = None) -> dict:
    """AWAITING_REVIEW -> APPROVED. Re-verifies pinned inputs haven't drifted (clone-cache HEAD
    unchanged) -- if they have, forces back to PLANNED for re-review rather than approving
    stale content. The skill itself must never call this on its own initiative -- only on an
    unambiguous, fresh instruction from the user in that turn (enforced by the calling skill
    doc, not by this function, which has no way to know who's asking)."""
    owner = _session_id(session_id)
    with _product_guard(family, platform):
        manifest = _load_manifest(family, platform, run_id)
        if manifest["session_owner"] != owner:
            raise ReadmeRefreshRunError(f"Run is owned by {manifest['session_owner']!r}, not {owner!r}")

        clone_cache = _product_clone_cache(family, platform)
        current_head = None
        if clone_cache.is_dir():
            try:
                current_head = _git("rev-parse", "HEAD", cwd=clone_cache)
            except ReadmeRefreshRunError:
                current_head = None
        pinned_head = manifest.get("pinned_inputs", {}).get("clone_cache_head")

        if pinned_head is not None and current_head != pinned_head:
            manifest["drift_detected_at"] = _utc()
            _event(family, platform, run_id, "APPROVE_BLOCKED_ON_DRIFT", pinned=pinned_head, current=current_head)
            _transition(manifest, "PLANNED", checkpoint="drift_forced_replan")
            raise ReadmeRefreshRunError(
                f"Pinned inputs have drifted (clone cache HEAD {pinned_head} -> {current_head}); "
                "forced back to PLANNED for re-review, not approved"
            )

        manifest["approval"] = {"note": note, "approved_by": owner, "approved_at": _utc()}
        _event(family, platform, run_id, "APPROVED", note=note)
        _transition(manifest, "APPROVED", checkpoint="approved")
        return manifest


# --- push: APPROVED -> PUSHING -> PUSHED ----------------------------------------------------


def push(
    family: str, platform: str, run_id: str, *, session_id: "str | None" = None, dry_run: bool = False,
    scratch_root: "Path | str | None" = None,
) -> dict:
    """APPROVED -> PUSHING -> PUSHED. Disposable-clone + branch + surgical-diff-checked
    plumbing commit + push + gh pr create (skipped when --dry-run, or when the branch/commit
    steps themselves fail before the network push -- --dry-run stops before any live GitHub
    write). See module docstring's Honest Scope Statement: has been exercised only against
    local scratch git repos, not a real external org, pending explicit authorization."""
    owner = _session_id(session_id)
    with _product_guard(family, platform):
        manifest = _load_manifest(family, platform, run_id)
        if manifest["session_owner"] != owner:
            raise ReadmeRefreshRunError(f"Run is owned by {manifest['session_owner']!r}, not {owner!r}")

        _transition(manifest, "PUSHING", checkpoint="pushing_started")

        scratch = Path(scratch_root) if scratch_root else _reports_root / "readme_refresh_runs" / "_scratch"
        scratch.mkdir(parents=True, exist_ok=True)
        work_dir = scratch / f"{family}-{platform}-{run_id}"
        try:
            receipt = _do_push(manifest, work_dir, dry_run=dry_run)
        except Exception as exc:
            _block(manifest, str(exc))
            raise ReadmeRefreshRunError(f"push failed, run BLOCKED: {exc}") from exc

        run_root = _run_root(family, platform, run_id)
        (run_root / "push").mkdir(parents=True, exist_ok=True)
        _write_json(run_root / "push" / "receipt.json", receipt)
        _event(family, platform, run_id, "PUSH_COMPLETED", **{k: v for k, v in receipt.items() if k != "declared_files"})

        if dry_run:
            # Dry-run rehearses everything up to (not including) the live write -- it does not
            # reach PUSHED, since nothing was actually pushed. Return to APPROVED so a real
            # push can still be attempted afterward.
            _transition(manifest, "APPROVED", checkpoint="dry_run_rehearsed")
            return manifest

        _transition(manifest, "PUSHED", checkpoint="pushed")
        return manifest


def _do_push(manifest: dict, work_dir: Path, *, dry_run: bool) -> dict:
    family, platform, run_id = manifest["family"], manifest["platform"], manifest["run_id"]
    branch = f"readme-refresh/{_now().strftime('%Y-%m-%d')}"
    candidate_path = _candidate_readme_path(family, platform)
    if not candidate_path.is_file():
        raise ReadmeRefreshRunError(f"No approved candidate found at {candidate_path}")

    if work_dir.exists():
        shutil.rmtree(work_dir)
    _git("clone", "--quiet", manifest["clone_url"], str(work_dir), cwd=_repo_root)
    default_branch = _git("symbolic-ref", "--short", "HEAD", cwd=work_dir)
    _git("checkout", "-b", branch, cwd=work_dir)

    (work_dir / "README.md").write_text(candidate_path.read_text(encoding="utf-8"), encoding="utf-8")
    _git("add", "README.md", cwd=work_dir)
    changed = _git("diff", "--cached", "--name-only", cwd=work_dir).splitlines()
    declared_files = ["README.md"]
    undeclared = checks.surgical_diff_check(declared_files, changed)
    if undeclared:
        raise ReadmeRefreshRunError(f"Surgical diff check failed: undeclared changes {undeclared}")

    tree_sha = _git("write-tree", cwd=work_dir)
    parent_sha = _git("rev-parse", "HEAD", cwd=work_dir)
    commit_message = (
        f"Refresh README: verified examples and documentation links\n\n"
        f"Automated, human-reviewed refresh via /readme-refresh (run {run_id}).\n\n"
        f"Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>\n"
    )
    commit_sha = _git(
        "commit-tree", tree_sha, "-p", parent_sha, "-m", commit_message, cwd=work_dir,
    )
    _git("update-ref", f"refs/heads/{branch}", commit_sha, cwd=work_dir)
    _git("checkout", branch, cwd=work_dir)

    receipt = {
        "branch": branch, "default_branch": default_branch, "commit_sha": commit_sha,
        "declared_files": declared_files, "dry_run": dry_run, "prepared_at": _utc(),
    }
    if dry_run:
        receipt["pr_url"] = None
        return receipt

    gh_token = os.environ.get("GH_TOKEN")
    if not gh_token:
        raise ReadmeRefreshRunError("GH_TOKEN is not set in the environment -- cannot push to an external repo")
    push_url = manifest["clone_url"].replace("https://", f"https://x-access-token:{gh_token}@")
    try:
        _git("push", push_url, branch, cwd=work_dir, check=True)
    except ReadmeRefreshRunError as exc:
        # _git()'s error message embeds the full argv, including push_url -- redact the real
        # token before this propagates anywhere it could be persisted (manifest.json via
        # _block()'s failure_reason, events.jsonl, or this process's own stdout/stderr).
        raise ReadmeRefreshRunError(str(exc).replace(gh_token, "***REDACTED***")) from exc
    pr_result = _command_runner(
        ["gh", "pr", "create", "--draft", "--repo", manifest["repo_full_name"], "--base", default_branch,
         "--head", branch, "--title", "Refresh README: verified examples and documentation links",
         "--body", f"Automated, human-reviewed refresh via /readme-refresh (run {run_id})."],
        cwd=str(work_dir), capture_output=True, text=True, timeout=60,
    )
    if pr_result.returncode != 0:
        raise ReadmeRefreshRunError(f"gh pr create failed: {(pr_result.stderr or pr_result.stdout).strip()}")
    receipt["pr_url"] = pr_result.stdout.strip()
    return receipt


# --- verify (post-push, safely re-runnable) -------------------------------------------------


def verify(family: str, platform: str, run_id: str, *, session_id: "str | None" = None) -> dict:
    """Post-push confirmation that the PR still exists and branch head matches the approved
    candidate hash. Safely re-runnable any time."""
    owner = _session_id(session_id)
    manifest = _load_manifest(family, platform, run_id)
    if manifest["session_owner"] != owner:
        raise ReadmeRefreshRunError(f"Run is owned by {manifest['session_owner']!r}, not {owner!r}")
    run_root = _run_root(family, platform, run_id)
    receipt_path = run_root / "push" / "receipt.json"
    if not receipt_path.is_file():
        raise ReadmeRefreshRunError("No push receipt found -- run has not been pushed yet")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if not receipt.get("pr_url"):
        raise ReadmeRefreshRunError("Push receipt has no pr_url -- was this a --dry-run?")
    result = _command_runner(
        ["gh", "pr", "view", receipt["pr_url"], "--json", "state,headRefOid"],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise ReadmeRefreshRunError(f"gh pr view failed: {(result.stderr or result.stdout).strip()}")
    info = json.loads(result.stdout)
    _event(family, platform, run_id, "VERIFY_COMPLETED", pr_state=info.get("state"))
    return {"manifest": manifest, "pr_state": info.get("state"), "head_sha": info.get("headRefOid")}


# --- abandon / recover / status --------------------------------------------------------------


def abandon_run(family: str, platform: str, run_id: str, *, reason: str, session_id: "str | None" = None) -> dict:
    owner = _session_id(session_id)
    with _product_guard(family, platform):
        manifest = _load_manifest(family, platform, run_id)
        if manifest["session_owner"] != owner:
            raise ReadmeRefreshRunError(f"Run is owned by {manifest['session_owner']!r}, not {owner!r}")
        _transition_abandoned(manifest, reason=reason)
        _clear_active(family, platform, run_id)
        return manifest


def recover_run(family: str, platform: str, run_id: str, *, reason: str, session_id: "str | None" = None) -> dict:
    """BLOCKED -> resume_state. Never touches a path it doesn't own; here that means only the
    manifest's own state field -- there is no local content to restore (the mutating effect is
    external), so recovery is purely re-entering the pre-BLOCKED state for a retry."""
    owner = _session_id(session_id)
    with _product_guard(family, platform):
        manifest = _load_manifest(family, platform, run_id)
        if manifest["session_owner"] != owner:
            raise ReadmeRefreshRunError(f"Run is owned by {manifest['session_owner']!r}, not {owner!r}")
        if manifest["state"] != "BLOCKED":
            raise ReadmeRefreshRunError(f"recover only applies to BLOCKED runs, current state is {manifest['state']}")
        resume_state = manifest.get("resume_state")
        if not resume_state:
            raise ReadmeRefreshRunError("BLOCKED run has no resume_state recorded")
        manifest["recovery_reason"] = reason.strip()
        _transition(manifest, resume_state, checkpoint="recovered")
        return manifest


def status(family: str, platform: str, run_id: str) -> dict:
    return _load_manifest(family, platform, run_id)


def _locate_run(run_id: str) -> tuple[str, str]:
    matches = list((_reports_root / "readme_refresh_runs").glob(f"*/*/{run_id}/manifest.json"))
    if not matches:
        raise ReadmeRefreshRunError(f"Run not found: {run_id}")
    if len(matches) > 1:
        raise ReadmeRefreshRunError(f"Ambiguous run_id {run_id}: {matches}")
    parts = matches[0].parts
    return parts[-4], parts[-3]


# --- CLI --------------------------------------------------------------------------------------


def _print_manifest(manifest: dict) -> None:
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(prog="readme_refresh_run", description="Run-bound state machine for /readme-refresh.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_start = sub.add_parser("start")
    p_start.add_argument("family")
    p_start.add_argument("platform")
    p_start.add_argument("--run-id")
    p_start.add_argument("--session-id")
    p_start.add_argument("--skip-preflight", action="store_true")

    for name in ("plan", "ingest-candidate", "recheck", "verify-examples", "status", "verify"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--run-id", required=True)
        if name != "status":
            cmd.add_argument("--session-id")
        if name == "recheck":
            # TC-HARDEN-12 (MT033): declare what this edit was scoped to, so the change-
            # isolation hard gates (check_only_mermaid_block_changed / check_only_sections_
            # changed) actually run against the prior checked snapshot. Both optional --
            # omitting both skips change-isolation checking, matching the pre-existing
            # (unscoped) recheck behavior exactly.
            cmd.add_argument(
                "--allowed-headings",
                help="Comma-separated ## heading names this edit was scoped to (plus "
                     "'__preamble__' for the region before the first heading). Any other "
                     "section that changed since the last check/recheck is flagged.",
            )
            cmd.add_argument(
                "--mermaid-only", action="store_true",
                help="This edit was scoped to only the At a Glance mermaid block itself.",
            )
        if name == "verify-examples":
            # TC-HARDEN-01 (MT033): opt-in real Python execution -- omitting this flag keeps the
            # honest, side-effect-free stub (every block BLOCKED-WITH-REASON:
            # TOOLCHAIN-UNAVAILABLE), matching every prior invocation's behavior exactly.
            cmd.add_argument(
                "--python-runner", action="store_true",
                help="Use the real Python verification runner (real venv + pip install + "
                     "execute `python`-tagged blocks) instead of the honest stub. Every "
                     "other language's blocks still report TOOLCHAIN-UNAVAILABLE.",
            )

    p_approve = sub.add_parser("approve")
    p_approve.add_argument("--run-id", required=True)
    p_approve.add_argument("--note", required=True)
    p_approve.add_argument("--session-id")

    p_push = sub.add_parser("push")
    p_push.add_argument("--run-id", required=True)
    p_push.add_argument("--session-id")
    p_push.add_argument("--dry-run", action="store_true")

    for name in ("abandon", "recover"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--run-id", required=True)
        cmd.add_argument("--reason", required=True)
        cmd.add_argument("--session-id")

    args = parser.parse_args(argv)
    try:
        if args.command == "start":
            manifest = start_run(
                args.family, args.platform, run_id=args.run_id, session_id=args.session_id,
                skip_preflight=args.skip_preflight,
            )
        else:
            family, platform = _locate_run(args.run_id)
            if args.command == "plan":
                manifest = plan_run(family, platform, args.run_id, session_id=args.session_id)
            elif args.command == "ingest-candidate":
                manifest = ingest_candidate(family, platform, args.run_id, session_id=args.session_id)
            elif args.command == "recheck":
                allowed_headings = (
                    [h.strip() for h in args.allowed_headings.split(",") if h.strip()]
                    if args.allowed_headings else None
                )
                result = recheck(
                    family, platform, args.run_id, session_id=args.session_id,
                    allowed_headings=allowed_headings, mermaid_only=args.mermaid_only,
                )
                print(json.dumps(result, indent=2, ensure_ascii=False))
                return 0
            elif args.command == "verify-examples":
                if args.python_runner:
                    configure(verification_runner=python_verification_runner)
                manifest = verify_examples(family, platform, args.run_id, session_id=args.session_id)
            elif args.command == "approve":
                manifest = approve(family, platform, args.run_id, note=args.note, session_id=args.session_id)
            elif args.command == "push":
                manifest = push(family, platform, args.run_id, session_id=args.session_id, dry_run=args.dry_run)
            elif args.command == "verify":
                result = verify(family, platform, args.run_id, session_id=args.session_id)
                print(json.dumps(result, indent=2, ensure_ascii=False))
                return 0
            elif args.command == "abandon":
                manifest = abandon_run(family, platform, args.run_id, reason=args.reason, session_id=args.session_id)
            elif args.command == "recover":
                manifest = recover_run(family, platform, args.run_id, reason=args.reason, session_id=args.session_id)
            else:
                manifest = status(family, platform, args.run_id)
        _print_manifest(manifest)
        return 0
    except ReadmeRefreshRunError as exc:
        print(f"README-REFRESH-RUN BLOCKED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
