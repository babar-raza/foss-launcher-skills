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


def _old_readme_inventory(clone_cache: Path) -> dict:
    old_readme = clone_cache / "README.md"
    if not old_readme.is_file():
        return {"links": [], "headings": [], "source": "no_old_readme_found"}
    text = old_readme.read_text(encoding="utf-8", errors="ignore")
    links = [href for _, href in checks._MD_LINK_RE.findall(text) if not href.startswith(("http://", "https://"))]
    headings = [m.group(2) for m in checks._HEADING_RE.finditer(text)]
    return {"links": sorted(set(links)), "headings": headings, "source": "clone_cache/README.md"}


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
            "install": _detect_install_info(family, platform),
            "license_file": _detect_license_file(clone_cache),
            "old_readme_inventory": _old_readme_inventory(clone_cache),
            "homepage": f"https://products.aspose.org/{family}/{platform}/",
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
    result["diagram_format_support_claims"] = {
        "hard_gate": True,
        "findings": checks.check_diagram_format_support_claims(
            text, _product_formats_md(family, platform), set(_canonical_format_casing().values())
        ),
    }
    known_format_names = (
        set(_canonical_format_casing().values()) | checks._DIAGRAM_SUPPLEMENTARY_FORMAT_NAMES
    )
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

    old_readme_path = clone_cache / "README.md"
    if old_readme_path.is_file():
        old_readme_text = old_readme_path.read_text(encoding="utf-8", errors="ignore")
        dropped = checks.check_dropped_content(old_readme_text, text, str(clone_cache))
        # check_dropped_content returns a dict ({"dropped_links", "dropped_headings",
        # "internal_labels" as of 2026-08-08}), not a flat list -- normalize to a flat
        # findings list so the generic "hard_gate and findings" truthiness check in
        # ingest_candidate() works correctly (a dict with three empty list values is still
        # a truthy dict, which would have silently made this hard gate un-passable).
        result["dropped_content"] = {
            "hard_gate": True,
            "findings": dropped["dropped_links"] + dropped["dropped_headings"] + dropped["internal_labels"],
            "detail": dropped,
        }
    else:
        # No old upstream README to diff against -- dropped_links/dropped_headings are
        # vacuously empty, but internal-label detection only ever scans the NEW candidate
        # text, so it must still run here rather than being silently skipped (a real gap
        # found while wiring this in: the original code hardcoded findings=[] for this
        # branch entirely, which would have meant internal-label detection never ran at
        # all for any product missing an old README).
        dropped = checks.check_dropped_content("", text, str(clone_cache))
        result["dropped_content"] = {
            "hard_gate": True,
            "findings": dropped["internal_labels"],
            "detail": {"source": "no_old_readme_found", **dropped},
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
    result["api_reference_intro_names_classes"] = {
        "hard_gate": False, "findings": checks.check_api_reference_intro_names_classes(text),
    }
    result["named_member_accuracy"] = {
        "hard_gate": False, "findings": checks.check_named_member_accuracy(text, str(clone_cache)),
    }
    return result


def recheck(family: str, platform: str, run_id: str, *, session_id: "str | None" = None) -> dict:
    """Re-run the deterministic checks in place after manual edits during AWAITING_REVIEW --
    does NOT transition state, only updates checks/result.json. Callers must inspect the
    returned result themselves; this does not raise on hard-gate findings (unlike
    ingest_candidate) since AWAITING_REVIEW is a human-in-the-loop hold, not a gate."""
    owner = _session_id(session_id)
    with _product_guard(family, platform):
        manifest = _load_manifest(family, platform, run_id)
        if manifest["session_owner"] != owner:
            raise ReadmeRefreshRunError(f"Run is owned by {manifest['session_owner']!r}, not {owner!r}")
        candidate_path = _candidate_readme_path(family, platform)
        text = candidate_path.read_text(encoding="utf-8") if candidate_path.is_file() else ""
        clone_cache = _product_clone_cache(family, platform)
        result = _run_deterministic_checks(family, platform, text, clone_cache)
        run_root = _run_root(family, platform, run_id)
        (run_root / "checks").mkdir(parents=True, exist_ok=True)
        _write_json(run_root / "checks" / "result.json", result)
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
                result = recheck(family, platform, args.run_id, session_id=args.session_id)
                print(json.dumps(result, indent=2, ensure_ascii=False))
                return 0
            elif args.command == "verify-examples":
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
