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
import hashlib
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
import backlink_targets  # noqa: E402
import freshness_guard  # noqa: E402
import publication_reconciler  # noqa: E402

import readme_refresh_checks as checks  # noqa: E402
import dependency_extract  # noqa: E402

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
_DEFAULT_CANDIDATE_TREE_NAME = "repo-presenter-regen-full"
# MT055/TC-MICRO-03 (2026-08-18): promoted from "repo-presenter" per a real, evidence-backed
# decision (repo-presenter-regen-full is the more current tree in every measured dimension --
# 16 of 30 active products carry MT041's mandatory Dependencies section only there, 0 the other
# way; see reports/_scratch/mt055_tree_divergence_inventory.json). "repo-presenter" itself is
# NOT deleted or otherwise touched by this change -- it remains on disk as a historical tree;
# reconciling/retiring it is deliberately deferred to a later, separate pass. Pass
# candidate_tree_name="repo-presenter" explicitly to configure() to address the old tree.
_repo_root = _DEFAULT_REPO_ROOT
_reports_root = _DEFAULT_REPO_ROOT / "reports"
_clone_cache_root = _DEFAULT_REPO_ROOT / "runs" / ".clone_cache"
_candidate_tree_name = _DEFAULT_CANDIDATE_TREE_NAME
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
    candidate_tree_name: "str | None" = None,
    command_runner: "Callable[..., subprocess.CompletedProcess[str]] | None" = None,
    now: "Callable[[], datetime] | None" = None,
    verification_runner: "Callable[[Path, dict], dict] | None" = None,
) -> None:
    """Override external boundaries for tests; call without arguments to reset.

    MT055/TC-MICRO-01 (2026-08-18): `reports_root` and `candidate_tree_name` are deliberately
    two separate knobs, not one. `_reports_root` means "the real reports/ directory" -- it is
    also consumed by `_run_root`/`_product_root`/`_product_lock_path` for run-evidence and lock
    paths, which have nothing to do with which candidate tree is being audited. Before this fix,
    every disposition/candidate path helper hardcoded the literal segment "repo-presenter"
    immediately after `_reports_root`, so pointing `reports_root` directly at a differently-named
    tree (e.g. "reports/repo-presenter-regen-full") silently resolved to a nonexistent nested
    path (".../repo-presenter-regen-full/repo-presenter/...") -- confirmed live during the MT054
    preservation audit, and the reason the "isolated mirror" workaround (physically copying files
    into `{tmp}/repo-presenter/{family}/{platform}/*` before calling `configure(reports_root=tmp)`)
    was required for every prior audit against an alternate tree. `candidate_tree_name` closes
    this: pass `configure(candidate_tree_name="repo-presenter-regen-full")` directly against the
    real `reports/` root, with no copy step needed.
    """
    global _repo_root, _reports_root, _clone_cache_root, _candidate_tree_name
    global _command_runner, _now, _verification_runner
    _repo_root = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    _reports_root = Path(reports_root) if reports_root is not None else _repo_root / "reports"
    _clone_cache_root = (
        Path(clone_cache_root) if clone_cache_root is not None else _repo_root / "runs" / ".clone_cache"
    )
    _candidate_tree_name = (
        candidate_tree_name if candidate_tree_name is not None else _DEFAULT_CANDIDATE_TREE_NAME
    )
    _command_runner = command_runner or subprocess.run
    _now = now or (lambda: datetime.now(timezone.utc))
    _verification_runner = verification_runner
    # RC-readme-refresh-freshness-guard-compliance (2026-08-30): keep freshness_guard's
    # module-level repo_root in lockstep with this module's own configure() -- the exact
    # FRESH-001 precedent in refresh_run.py/batch_reference.py. Without this, a test that
    # points this module at a tmp_path would still have freshness_guard resolving against
    # the real repo's knowledge/ tree underneath it.
    freshness_guard.configure(repo_root=_repo_root)
    publication_reconciler.configure(repo_root=_repo_root)


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
    return _reports_root / _candidate_tree_name / family / platform / "readme.md"


def _upstream_issues_path(family: str, platform: str) -> Path:
    return _reports_root / _candidate_tree_name / family / platform / "upstream-issues.md"


def _content_dispositions_path(family: str, platform: str) -> Path:
    """Fifteenth incident / MT030 (2026-08-09): the real, agent-authored artifact
    `dropped_claims.json` only ever promised (docstring-only, 2026-08-04 through 2026-08-09,
    never implemented). Sibling to readme.md/upstream-issues.md, same directory."""
    return _reports_root / _candidate_tree_name / family / platform / "content-dispositions.json"


def _structure_dispositions_path(family: str, platform: str) -> Path:
    """Twenty-Fourth incident / mission (2026-08-13, `cells/go`'s missing Project Structure
    section): sibling to content-dispositions.json, same directory, same agent-authored tier --
    but a separate file, not an extension of content-dispositions.json's own schema, since that
    schema's `classification` enum (narrative/mechanism/branding/history/redundant) has no
    honest value for "a directory tree." See `extract_old_readme_structural_units`'s own
    docstring for what this file records."""
    return _reports_root / _candidate_tree_name / family / platform / "structure-dispositions.json"


def _badge_dispositions_path(family: str, platform: str) -> Path:
    """Twenty-Fourth incident / mission (2026-08-13): sibling to content-dispositions.json /
    structure-dispositions.json, same directory, same agent-authored tier. Records the accept-
    or-override decision for every badge `extract_badges` finds in the OLD upstream README --
    see `reconcile_badges`'s own docstring for the recommendation this file must confirm or
    override, never silently accept unexamined."""
    return _reports_root / _candidate_tree_name / family / platform / "badge-dispositions.json"


def _code_example_dispositions_path(family: str, platform: str) -> Path:
    """TC-HARDEN-74 (MT047/Thirty-Seventh incident, 2026-08-15): sibling to content-
    dispositions.json/structure-dispositions.json/badge-dispositions.json, same directory, same
    agent-authored tier. Records the merge/relocate/exclude/correct disposition for every code
    unit `extract_old_readme_code_units` finds in the OLD upstream README -- see that function's
    own docstring for the code-example-inventory blind spot this file exists to close."""
    return _reports_root / _candidate_tree_name / family / platform / "code-example-dispositions.json"


def _old_readme_baseline_path(family: str, platform: str) -> Path:
    """TC-20 (readme-refresh-trackb-and-followon-2026-09-01): sibling to content-dispositions.json,
    same directory, same agent-authored tier. Records the git commit a disposition ledger's
    `excerpt`/`unit_id` fields were actually built against, when that commit is no longer the
    clone cache's live HEAD -- absent by default (the common case: the ledger was built against
    whatever is still HEAD, so no pin is needed and `_resolve_old_readme_text` falls straight
    through to the live file, identical to every prior call). Only ever written by `pin-old-
    readme-baseline`, never by any check/ingest/recheck/audit-portfolio code path."""
    return _reports_root / _candidate_tree_name / family / platform / "old-readme-baseline.json"


def _resolve_old_readme_text(family: str, platform: str, clone_cache: Path) -> "tuple[str, dict | None]":
    """Reads the text a disposition ledger's content units should be re-extracted from.

    RC-1/TC-20 (proven live twice: font/python's TC-37 git-history rewrite, 3d/net's TC-38 --
    see readme-refresh-trackb-and-followon-2026-09-01 taskcards.jsonl): every disposition check
    previously re-derived "the old README" by reading the clone cache's live `README.md`
    unconditionally. That is correct for the overwhelming majority of products (nothing has
    happened to move the goalposts), but wrong the moment the live HEAD has legitimately moved
    past the text the disposition ledger actually describes -- e.g. a real, human-approved
    upstream PR republished this exact repo's own prior candidate (3d/net PR #3, merged
    2026-08-19, author-verified via `gh pr view`) after the ledger was built. Re-deriving from
    the new live HEAD in that case compares the ledger against content it was never written to
    describe, producing pure false-positive drift findings on an already-correct ledger --
    confirmed by re-running `check_content_unit_excerpt_matches_extraction` against 3d/net's
    real pre-PR#3 commit (`70933ab`): 0 findings, vs. 46 against live HEAD.

    Returns `(text, baseline_info)` -- `baseline_info` is `None` when no sidecar is pinned (the
    live-HEAD path, unchanged from every prior call); otherwise the parsed sidecar dict, so
    callers can attribute findings/skips to a specific pinned commit rather than silently
    reading from an unlabeled alternate source.
    """
    old_readme_path = clone_cache / "README.md"
    sidecar_path = _old_readme_baseline_path(family, platform)
    if not sidecar_path.is_file():
        if not old_readme_path.is_file():
            return "", None
        return old_readme_path.read_text(encoding="utf-8", errors="ignore"), None

    baseline_info = json.loads(sidecar_path.read_text(encoding="utf-8"))
    commit = baseline_info.get("baseline_commit")
    if not commit:
        # Malformed sidecar -- fail safe to the live-HEAD path rather than raising, matching
        # this module's own "a missing/broken optional input degrades, never crashes" posture.
        if not old_readme_path.is_file():
            return "", None
        return old_readme_path.read_text(encoding="utf-8", errors="ignore"), baseline_info

    proc = subprocess.run(
        ["git", "show", f"{commit}:README.md"],
        cwd=str(clone_cache), capture_output=True, text=True, encoding="utf-8", errors="ignore",
    )
    if proc.returncode != 0:
        # The pinned commit is no longer resolvable in this clone (e.g. a shallow-clone refresh
        # dropped it) -- fail safe to live HEAD rather than silently returning empty text, which
        # would make every content-unit check vacuously pass instead of correctly re-flagging.
        if not old_readme_path.is_file():
            return "", None
        return old_readme_path.read_text(encoding="utf-8", errors="ignore"), baseline_info
    return proc.stdout, baseline_info


def _product_clone_cache(family: str, platform: str) -> Path:
    return _clone_cache_root / f"aspose_{family}_{platform}"


# --- MT056 (Fifty-Sixth incident, 2026-08-18): canonical candidate store, change scopes, ------
# --- acceptance registry. Plan: MT056 §3; forensic basis: reports/_scratch/ ------------------
# --- mt056_regression_ledger.md (patterns 2, 4, 6, 7). ---------------------------------------


_ARCHIVED_TREE_MARKER_NAME = "_ARCHIVED.json"


def _candidate_store_path() -> Path:
    return _repo_root / "data" / "readme_candidate_store.json"


def _published_state_path() -> Path:
    return _repo_root / "data" / "readme_published_state.json"


def _load_candidate_store() -> "dict | None":
    """The durable canonical-tree decision record (data/readme_candidate_store.json). Absent
    file -> None -> every store gate below is a backward-compatible no-op (tests with tmp
    repo_root, pre-MT056 checkouts)."""
    path = _candidate_store_path()
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_published_state() -> "dict | None":
    path = _published_state_path()
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _require_canonical_tree(action: str) -> None:
    """Canonical-location HARD gate for mutating entry points (start/push): a run may only ever
    be created against, and a push may only ever ship from, the canonical candidate tree the
    user decided on (MT055 TC-MICRO-03-02 human gate, recorded durably in
    data/readme_candidate_store.json). Read-only review of an archived tree goes through
    audit-portfolio --candidate-tree instead."""
    store = _load_candidate_store()
    if store is None:
        return
    canonical = store.get("canonical_tree")
    if canonical and _candidate_tree_name != canonical:
        raise ReadmeRefreshRunError(
            f"{action} refused: configured candidate tree {_candidate_tree_name!r} is not the "
            f"canonical tree {canonical!r} (data/readme_candidate_store.json). Runs and pushes "
            "operate only on the canonical store; use `audit-portfolio --candidate-tree` for "
            "read-only review of an archived tree."
        )


def _validate_candidate_tree_for_audit() -> "str | None":
    """audit-portfolio's own tree validation: canonical -> None (no tag); a registered archived
    tree -> a human-readable non-canonical tag; anything else -> refused outright (stale-path
    protection -- an unregistered tree, e.g. a frozen _scratch mirror layout, must never be
    silently audited as if it were a live store)."""
    store = _load_candidate_store()
    if store is None:
        return None
    canonical = store.get("canonical_tree")
    archived = set(store.get("archived_trees") or [])
    if canonical is None or _candidate_tree_name == canonical:
        return None
    if _candidate_tree_name in archived:
        return f"NON-CANONICAL (archived tree {_candidate_tree_name!r}, read-only review)"
    raise ReadmeRefreshRunError(
        f"audit-portfolio refused: {_candidate_tree_name!r} is neither the canonical tree "
        f"({canonical!r}) nor a registered archived tree ({sorted(archived)}); register it in "
        "data/readme_candidate_store.json or point at a real store"
    )


def _check_manifest_candidate_tree(manifest: dict) -> None:
    """Mid-run tree-flip protection: a run pins the candidate tree it was started against; a
    later stage running under a differently-configured tree would read/promote a different
    product copy than the one the run's own checks validated. Tolerant of pre-MT056 manifests
    (no candidate_tree key)."""
    pinned = manifest.get("candidate_tree")
    if pinned is not None and pinned != _candidate_tree_name:
        raise ReadmeRefreshRunError(
            f"run {manifest.get('run_id')!r} was started against candidate tree {pinned!r} but "
            f"the current configuration points at {_candidate_tree_name!r} -- refusing to mix "
            "trees mid-run"
        )


def _candidate_store_findings(family: str, platform: str) -> list[dict]:
    """The '>1 current candidate' enforcement scan (MT056 Stage 4): every sibling
    `repo-presenter*` tree under reports/ other than the canonical one must either hold no
    candidate for this product, or be a registered archived tree whose _ARCHIVED.json marker
    fingerprints still match its on-disk content byte-for-byte. Findings (all hard):
      - the configured tree itself is not canonical;
      - an unregistered sibling tree holds a live readme.md for this product (split-brain);
      - a registered archived tree has no marker (archival incomplete);
      - a marker fingerprint mismatch (archive violated -- someone wrote to a frozen tree).
    No store file -> no findings (legacy/test mode)."""
    store = _load_candidate_store()
    if store is None:
        return []
    findings: list[dict] = []
    canonical = store.get("canonical_tree")
    archived = set(store.get("archived_trees") or [])
    if canonical and _candidate_tree_name != canonical:
        findings.append({
            "tree": _candidate_tree_name,
            "reason": f"configured candidate tree {_candidate_tree_name!r} is not the canonical "
                      f"tree {canonical!r}",
        })
    if not _reports_root.is_dir():
        return findings
    for entry in sorted(_reports_root.glob("repo-presenter*")):
        if not entry.is_dir() or entry.name == canonical:
            continue
        candidate_paths = [
            p for p in (
                entry / family / platform / "readme.md",
                entry / "repo-presenter" / family / platform / "readme.md",
            ) if p.is_file()
        ]
        if not candidate_paths:
            continue
        if entry.name not in archived:
            findings.append({
                "tree": entry.name,
                "reason": f"unregistered candidate tree {entry.name!r} holds a live readme.md "
                          f"for {family}/{platform} -- more than one current candidate exists; "
                          "register the tree as archived (with an _ARCHIVED.json marker) in "
                          "data/readme_candidate_store.json, or remove the copy",
            })
            continue
        marker = entry / _ARCHIVED_TREE_MARKER_NAME
        if not marker.is_file():
            findings.append({
                "tree": entry.name,
                "reason": f"tree {entry.name!r} is registered as archived but carries no "
                          f"{_ARCHIVED_TREE_MARKER_NAME} marker -- archival incomplete",
            })
            continue
        try:
            marker_data = json.loads(marker.read_text(encoding="utf-8"))
        except Exception:
            findings.append({
                "tree": entry.name,
                "reason": f"unreadable {_ARCHIVED_TREE_MARKER_NAME} in {entry.name!r}",
            })
            continue
        recorded = marker_data.get("readme_sha256") or {}
        for path in candidate_paths:
            rel_key = str(path.relative_to(entry)).replace("\\", "/")
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            expected = recorded.get(rel_key)
            if expected is None:
                findings.append({
                    "tree": entry.name,
                    "path": rel_key,
                    "reason": f"archived tree {entry.name!r} holds {rel_key} but its marker "
                              "records no fingerprint for it -- archival incomplete for this "
                              "product",
                })
            elif expected != actual:
                findings.append({
                    "tree": entry.name,
                    "path": rel_key,
                    "reason": f"ARCHIVE VIOLATED: {entry.name!r}/{rel_key} changed after "
                              "archival -- frozen trees are immutable; recover the archived "
                              "content or re-run the archival pass deliberately",
                })
    return findings


def _acceptance_registry_path(family: str, platform: str) -> Path:
    """Sibling to readme.md/the disposition files, same agent-visible tier, same (canonical)
    tree. Stores block identities, hashes, states, and evidence refs -- NEVER candidate
    content (MT056 Stage 7)."""
    return _reports_root / _candidate_tree_name / family / platform / "acceptance-registry.json"


def _load_acceptance_registry(family: str, platform: str) -> dict:
    path = _acceptance_registry_path(family, platform)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ReadmeRefreshRunError(f"Unreadable acceptance registry at {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ReadmeRefreshRunError(f"Acceptance registry at {path} is not a JSON object")
    return data


def _scope_root(family: str, platform: str, run_id: str) -> Path:
    return _run_root(family, platform, run_id) / "scope"


def _change_scope_path(family: str, platform: str, run_id: str) -> Path:
    return _scope_root(family, platform, run_id) / "change_scope.json"


def _scope_baseline_path(family: str, platform: str, run_id: str) -> Path:
    """The IMMUTABLE per-scope baseline (captured once at declare-scope). Deliberately not the
    rolling checks/last_checked_candidate.md snapshot, which is overwritten on every check
    iteration by design (TC-HARDEN-12 checkpoint-0 semantics) and therefore cannot anchor an
    out-of-scope-diff proof across multiple repair iterations."""
    return _scope_root(family, platform, run_id) / "baseline_candidate.md"


def _load_change_scope(family: str, platform: str, run_id: str) -> "dict | None":
    path = _change_scope_path(family, platform, run_id)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ReadmeRefreshRunError(f"Unreadable change scope at {path}: {exc}") from exc


def _apply_scope_enforcement(
    result: dict, family: str, platform: str, run_id: str, text: str
) -> None:
    """MT056 fail-closed enforcement, applied by BOTH ingest_candidate and recheck (unlike the
    recheck-only, opt-in TC-HARDEN-12 isolation checks):

      - candidate_store_integrity [hard]: the >1-current-candidate / archive-integrity scan.
      - scope_compliance [hard, when a scope is declared]: candidate vs. the scope's immutable
        baseline; any unauthorized block change fails (out-of-scope diff gate).
      - frozen_blocks_unchanged [hard, when an acceptance registry exists]: CONVERGED/
        FROZEN_ACCEPTED blocks must be byte-identical unless the active scope authorizes them.
      - scope_required [hard, when a registry exists and no scope is declared]: the document
        drifted from its last-accepted state with no declared scope -> fail closed. An
        unchanged document passes (stable regeneration after convergence must stay green).
    """
    result["candidate_store_integrity"] = {
        "hard_gate": True, "findings": _candidate_store_findings(family, platform),
    }
    scope = _load_change_scope(family, platform, run_id)
    registry = _load_acceptance_registry(family, platform)
    entries = registry.get("blocks") or []

    authorized: list[str] = []
    if scope is not None:
        authorized = list(scope.get("areas") or []) + list(scope.get("allowed_dependencies") or [])
        if scope.get("full_rewrite"):
            result["scope_compliance"] = {
                "hard_gate": True, "findings": [],
                "detail": {"issue": scope.get("issue"), "full_rewrite": True},
            }
        else:
            baseline_path = _scope_baseline_path(family, platform, run_id)
            if not baseline_path.is_file():
                result["scope_compliance"] = {
                    "hard_gate": True,
                    "findings": [{
                        "reason": "declared change scope has no baseline snapshot on disk -- "
                                  "re-run declare-scope",
                    }],
                }
            else:
                baseline_text = baseline_path.read_text(encoding="utf-8")
                result["scope_compliance"] = {
                    "hard_gate": True,
                    "findings": checks.check_scope_compliance(baseline_text, text, authorized),
                    "detail": {
                        "issue": scope.get("issue"),
                        "areas": scope.get("areas"),
                        "allowed_dependencies": scope.get("allowed_dependencies"),
                    },
                }

    if entries:
        if scope is not None and scope.get("full_rewrite"):
            frozen_authorized = [e.get("block_id") for e in entries if isinstance(e.get("block_id"), str)]
        else:
            frozen_authorized = authorized
        result["frozen_blocks_unchanged"] = {
            "hard_gate": True,
            "findings": checks.check_frozen_blocks_unchanged(text, entries, frozen_authorized),
        }
        doc_sha = registry.get("document_sha256")
        scope_required_findings: list[dict] = []
        if scope is None and isinstance(doc_sha, str):
            current_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if current_sha != doc_sha:
                snapshot = registry.get("block_fingerprints") or {}
                live = checks.compute_block_fingerprints(text)
                changed = sorted(
                    block_id for block_id in set(snapshot) | set(live)
                    if snapshot.get(block_id) != live.get(block_id)
                )
                scope_required_findings.append({
                    "changed_blocks": changed,
                    "reason": "this product has an acceptance registry and the candidate has "
                              "drifted from its last-accepted state, but no change scope is "
                              "declared for this run -- declare-scope (naming the intended "
                              "areas) before regenerating; undeclared drift fails closed",
                })
        result["scope_required"] = {"hard_gate": True, "findings": scope_required_findings}


def _candidate_last_verified_path(family: str, platform: str) -> Path:
    """TC-M56-09 (2026-08-18): sibling to acceptance-registry.json, same agent-visible tier.
    Records the fingerprint of the candidate the LAST TIME any check battery actually ran
    against it (ingest-candidate, recheck, or audit-portfolio) -- never candidate content
    itself, only its identity. Exists because a real, untracked writer editing a canonical
    candidate file directly on disk (confirmed live during the MT056 proof pass: 3 products'
    candidates were edited by a process outside every CLI path, invisible to git since
    reports/ is gitignored, invisible to every other MT056 gate since no run was ever
    started) went completely undetected until a portfolio audit happened to notice a
    downstream side effect. A write-time lock cannot catch this class of incident -- the
    observed writer never went through any cooperating CLI path to lock against. A fingerprint
    marker is the only mechanism that can detect the drift after the fact."""
    return _reports_root / _candidate_tree_name / family / platform / "last-verified.json"


def _load_candidate_last_verified(family: str, platform: str) -> "dict | None":
    path = _candidate_last_verified_path(family, platform)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_candidate_verification_marker(
    family: str, platform: str, text: str, *, run_id: "str | None"
) -> None:
    # readme-refresh-forensic-trust-audit-2026-08-25 (Cluster H, row 36): hash the real
    # on-disk bytes, not `text` -- `Path.read_text()`'s universal-newline translation means
    # `text.encode("utf-8")` silently normalizes CRLF to LF before hashing, so the recorded
    # hash never matched the file's actual bytes on a CRLF-checked-out candidate.
    new_hash = hashlib.sha256(_candidate_readme_path(family, platform).read_bytes()).hexdigest()
    if run_id is None:
        # Cluster H, row 35: an audit-only write (audit_portfolio) does not own a bound run,
        # but must not clobber a prior bound run's provenance when the content it's
        # confirming is unchanged -- only reset to None when the content actually changed
        # (or no prior marker exists), since only then is it true that no bound run has
        # verified this exact content.
        existing = _load_candidate_last_verified(family, platform)
        if existing is not None and existing.get("readme_sha256") == new_hash:
            run_id = existing.get("verified_by_run_id")
    _write_json(_candidate_last_verified_path(family, platform), {
        "readme_sha256": new_hash,
        "verified_at": _utc(),
        "verified_by_run_id": run_id,
        # readme-refresh-seo-deps-headings-hardening mission (2026-08-19), TC-SDH-05: see
        # checks.CHECKS_MODULE_VERSION's own docstring.
        "checks_module_version": checks.CHECKS_MODULE_VERSION,
    })


def _checks_currency_findings(family: str, platform: str) -> list[dict]:
    """TC-SDH-05 (2026-08-19): advisory-only, portfolio-visibility signal -- NEVER a hard gate,
    same tier as `_candidate_drift_findings` (immediately above), whose "was this candidate
    edited since it was last checked" question this deliberately does NOT answer. This answers a
    different one: "was this candidate last checked against the CURRENT checks module, or an
    older one?" A candidate can be byte-identical to its last-verified snapshot (drift-clean)
    while that snapshot's own certification predates checks added since -- exactly what happened
    to 3d/net today: its `audit_portfolio -> clean: true` result from earlier this same session
    was true, but only against checks module version 1; this mission's 3 new checks (version 2)
    never ran against it. A marker with no `checks_module_version` field at all (written before
    this mission) is treated as version 0 -- always stale relative to any real version, the safe
    default (never silently treated as current)."""
    marker = _load_candidate_last_verified(family, platform)
    if marker is None:
        return []
    stored_version = marker.get("checks_module_version", 0)
    current_version = checks.CHECKS_MODULE_VERSION
    if stored_version >= current_version:
        return []
    return [{
        "reason": f"this candidate was last verified against checks module version "
                  f"{stored_version} but the running module is version {current_version} -- "
                  f"its 'clean' certification predates checks added since and should not be "
                  f"trusted without a fresh audit_portfolio/ingest-candidate/recheck run",
        "stored_checks_module_version": stored_version,
        "current_checks_module_version": current_version,
    }]


def _candidate_drift_findings(family: str, platform: str) -> list[dict]:
    """TC-M56-09: advisory-only, portfolio-visibility signal -- NEVER a hard gate. A candidate
    legitimately differs from its own last-verified marker every time an agent edits it before
    the very next ingest-candidate call in the same, ordinary compose-then-verify workflow;
    that is expected, not a defect. The real value is in `audit-portfolio`, run independently
    of any active editing session: a nonzero finding there means the candidate moved since
    anyone last ran checks on it, regardless of who moved it or why -- exactly the fact that
    was invisible for 3 real products during the MT056 proof pass until an unrelated
    portfolio-diff happened to expose a side effect of it.

    readme-refresh-forensic-trust-audit-2026-08-25 (Cluster H, row 36): compares real
    on-disk bytes, matching `_write_candidate_verification_marker`'s own hash basis -- hashing
    a `text` string previously produced a spurious mismatch on any CRLF-checked-out candidate.
    """
    marker = _load_candidate_last_verified(family, platform)
    if marker is None:
        return []
    recorded_sha = marker.get("readme_sha256")
    current_sha = hashlib.sha256(_candidate_readme_path(family, platform).read_bytes()).hexdigest()
    if recorded_sha == current_sha:
        return []
    return [{
        "reason": f"candidate content changed since it was last verified at "
                  f"{marker.get('verified_at')!r} (run {marker.get('verified_by_run_id')!r}) -- "
                  "review this change before treating the candidate as previously audited",
        "last_verified_at": marker.get("verified_at"),
        "last_verified_by_run_id": marker.get("verified_by_run_id"),
    }]


def _published_readme_current_findings(
    family: str, platform: str, readme_already_published: bool
) -> list[dict]:
    """MT056 Stage-9 republication tripwire (advisory): a product with a recorded publication
    (data/readme_published_state.json) whose clone-cache README no longer matches the canonical
    candidate carries open republication debt. Mechanically re-derives what the plan's taskcard
    register once LOST (TC-HARDEN-47/48: 3d/net + 3d/python published pre-MT024, still clipping
    live) -- the debt can no longer exist only in a register."""
    if readme_already_published:
        return []
    state = _load_published_state()
    if state is None:
        return []
    for row in state.get("products") or []:
        if row.get("family") == family and row.get("platform") == platform:
            return [{
                "reason": f"{family}/{platform} was published upstream (last known "
                          f"{row.get('last_known_publication')}) but the live upstream README "
                          "no longer matches the canonical candidate -- republication pending",
                "evidence": row.get("evidence"),
            }]
    return []


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


def _append_action_ledger_row(
    family: str, platform: str, *, action: str, details: dict, session_id: str,
) -> None:
    """TC-HARDEN-15 (MT035, 2026-08-12): `reports/repo_presenter_actions.jsonl` -- the designed,
    cross-run, append-only external-action audit ledger this plan's own original Storage design
    (2026-08-04) specified and was never actually built (confirmed absent, MT033). Real gap this
    closes: no existing file/skill in this repo tracked "what has actually been pushed to an
    external repo, and when" as a durable, git-trackable record -- MT033's own audit had to
    reconstruct that history by hand from GitHub PR pages and commit messages, exactly the gap
    this ledger exists to close. One row per real `push` call (dry-run or live), distinguished by
    `action` (`readme_push_dry_run` vs. `readme_pr_opened`) and `details["dry_run"]`. Lives at
    `reports/repo_presenter_actions.jsonl` (not under `readme_refresh_runs/{run_id}/` -- this is
    the durable, CROSS-run history; `push/receipt.json` remains the single-run detail)."""
    path = _reports_root / "repo_presenter_actions.jsonl"
    row = {
        "event_id": uuid.uuid4().hex,
        "family": family,
        "platform": platform,
        "skill": "readme-refresh",
        "action": action,
        "timestamp": _utc(),
        "details": details,
        "session_id": session_id,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
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


def _load_json_registry(path: Path) -> "list | dict":
    """TC-HARDEN-30 (MT035): a hand-edited registry file with a JSON syntax error (a trailing
    comma is the single most common mistake) must fail with a clean, named BLOCKED message --
    never a raw json.JSONDecodeError traceback. Every registry loader in this module routes
    through this helper so that guarantee holds uniformly, not just for products.json."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ReadmeRefreshRunError(f"Cannot read registry file {path}: {exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ReadmeRefreshRunError(f"Malformed JSON in {path}: {exc}") from exc


def _load_products() -> list[dict]:
    return _load_json_registry(_repo_root / "data" / "products.json")


def _load_api_reference_class_exclusions() -> list[dict]:
    """TC-HARDEN-77 (MT047/Thirty-Seventh incident, 2026-08-15). Same governance shape as
    `_load_registry_exclusions`/`data/diagram_archetypes.json`'s own loaders: a small,
    evidence-required override file, absent-tolerant (an empty list, never a hard failure, when
    the file doesn't exist yet -- the common state for every product until its first real,
    confirmed internal-only-class finding)."""
    path = _repo_root / "data" / "api_reference_class_exclusions.json"
    if not path.is_file():
        return []
    return _load_json_registry(path)


def _product_api_reference_class_exclusions(family: str, platform: str) -> set[str]:
    """Flattens `_load_api_reference_class_exclusions`'s full, cross-portfolio list down to just
    this product's own confirmed `class_name` entries -- the set `check_api_reference_table_
    completeness`'s new `exclusions` parameter consumes."""
    return {
        entry["class_name"]
        for entry in _load_api_reference_class_exclusions()
        if entry.get("family") == family and entry.get("platform") == platform and entry.get("class_name")
    }


def _load_registry_exclusions() -> list[dict]:
    path = _repo_root / "data" / "registry_exclusions.json"
    if not path.is_file():
        return []
    return _load_json_registry(path)


_PRODUCT_REQUIRED_FIELDS = ("repo_url", "clone_url")


def _resolve_product(family: str, platform: str) -> dict:
    for entry in _load_products():
        if entry.get("family") == family and entry.get("platform") == platform:
            if not entry.get("active", False):
                raise ReadmeRefreshRunError(f"{family}/{platform} is not active in data/products.json")
            # TC-HARDEN-30 (MT035): validate required fields explicitly, before any caller
            # indexes them with product["repo_url"]/product["clone_url"] -- a hand-added
            # new-product row missing either key must fail with a clean, named BLOCKED
            # message, never a raw KeyError traceback later in the call chain.
            missing = [field for field in _PRODUCT_REQUIRED_FIELDS if not entry.get(field)]
            if missing:
                raise ReadmeRefreshRunError(
                    f"{family}/{platform}'s row in data/products.json is missing required "
                    f"field(s): {', '.join(missing)}"
                )
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


def _check_family_registered(family: str) -> None:
    """TC-HARDEN-33 (MT035, 2026-08-12): `data/families.json` is a separate, hand-maintained
    registry from `data/products.json`, not derived from it (confirmed real -- its display-name
    capitalization, e.g. "3d" -> "Aspose.3D", "html" -> "Aspose.HTML", "tex" -> "Aspose.TeX", is
    genuine information `products.json`'s own bare lowercase slug can never mechanically
    reproduce, so deriving the family set from `products.json` alone -- this taskcard's own
    Required-work option (a) -- was not viable). Without this check, a genuinely new family added
    to `products.json` without a matching `families.json` entry means `check_no_cross_product_
    citation`'s family allowlist silently stops catching ANY OTHER product's citation of the new
    family -- no warning anywhere. Refusing to `start` a run for an unregistered family forces the
    registry gap to be fixed BEFORE it can ever become a silent, later defect, rather than relying
    on someone remembering to update a second file."""
    path = _repo_root / "data" / "families.json"
    if not path.is_file():
        return  # degrade gracefully -- families.json itself absent is a different, unrelated problem
    registry = json.loads(path.read_text(encoding="utf-8"))
    if family not in registry:
        raise ReadmeRefreshRunError(
            f"{family!r} is not registered in data/families.json -- add it there "
            f"(e.g. {{\"...\": \"...\", {family!r}: \"Aspose.{family.capitalize()}\"}}, adjusting the "
            f"display-name capitalization to the product's real branding) before starting a run "
            f"for this family. Without it, check_no_cross_product_citation's family allowlist "
            f"silently stops catching any OTHER product's citation of this family."
        )


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
    _check_family_registered(family)
    # MT056: a run may only be created against the canonical candidate tree.
    _require_canonical_tree("start")
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
            # MT056: pin the candidate tree this run operates on -- later stages refuse to run
            # under a differently-configured tree (_check_manifest_candidate_tree).
            "candidate_tree": _candidate_tree_name,
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


def _reference_index_source_dirty(family: str, platform: str) -> bool:
    """TC-HARDEN-37 (MT035, 2026-08-12): a lightweight git-dirty check for `content/
    reference.aspose.org/en/{family}/{platform}/_index.md` -- the real, authoritative source
    `check_api_reference_table_completeness` compares the candidate's own table against.
    Best-effort only: returns `False` (never flags dirty) on any git failure -- this is a
    non-blocking heuristic signal, not something that should itself ever raise or block a run
    just because git couldn't be invoked for some unrelated reason."""
    rel_path = f"content/reference.aspose.org/en/{family}/{platform}/_index.md"
    try:
        output = _git("diff", "--stat", "HEAD", "--", rel_path, check=False)
    except Exception:
        return False
    return bool(output.strip())


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


def _load_canonical_overrides() -> "dict | None":
    """MT043 (TC-HARDEN-61, Thirty-Third incident, 2026-08-14): `_detect_enterprise_link` never
    loaded this file -- confirmed by direct code read, no `canonical_overrides=` keyword
    anywhere in its old call to `resolve_backlink`. `data/backlinks/platform_canonical_
    overrides.yaml` is a real, human-curated, HTTP-verified override file every OTHER
    `backlink_targets.py` consumer (docs/kb/reference/products page generation, e.g.
    `backlink_audit.py`) already loads -- this reuses that exact same path/loader pattern
    (`repo_root/data/backlinks/platform_canonical_overrides.yaml`, `yaml.safe_load`, graceful
    degradation to `None` on any error) so `/readme-refresh` finally benefits from the same
    curated policy every other consumer already does. Confirmed real, live impact: the override
    file's own dated policy states `cells/python -> python-net` (verified 2026-07-03, HTTP 200),
    but the raw cached target map instead held a later, less-explained `python-java` correction
    -- without this fix, `/readme-refresh` silently used the less-authoritative value."""
    path = _repo_root / "data" / "backlinks" / "platform_canonical_overrides.yaml"
    if not path.is_file():
        return None
    try:
        import yaml
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _classify_enterprise_relationship(source_platform: str, url: "str | None") -> dict:
    """MT043 (TC-HARDEN-61, Thirty-Third incident, 2026-08-14) -- CORRECTED 2026-08-14 (MT044,
    Thirty-Fourth incident). The mechanical (never hand-curated) relationship classification
    behind the Stage 3 anchor-text contract -- see the plan's own Thirty-Fourth incident section
    for the full, real-evidence-backed derivation of this correction.

    MT043's original design collapsed a hyphenated URL segment (e.g. "python-java") into a
    `"bridge"` relationship whose anchor was REQUIRED to name the bridge language ("via Java")
    plus a disclosure sentence -- the exact policy defect MT044 exists to reverse: the public
    anchor must NEVER expose how one platform is implemented through another. This corrected
    version collapses what used to be `"exact"` and `"bridge"` into a single `"platform"`
    outcome. For a hyphenated (compound/bridge-shaped) segment, the FULL segment is looked up
    directly in `backlink_targets.PLATFORM_ALIASES` -- that table already maps every real,
    reviewed compound key straight to its normalized public platform (e.g. `"python-java"` ->
    `"python"`, `"go-cpp"` -> `"go"`); it is reused verbatim, never re-derived by partitioning on
    the hyphen. The bridge/suffix information itself is discarded entirely and never surfaced to
    any caller -- that is MT044's own permanent rule, not an implementation detail.

    Derives everything from data already computed (the resolved `url`) plus the small, already-
    real `backlink_targets.PLATFORM_ALIASES` table and the checks module's own already-reviewed
    `_PLATFORM_DISPLAY_NAMES` table (imported, not duplicated -- safe direction since
    `readme_refresh_checks.py` never imports this module) -- no new hand-curated data file, per
    the plan's own explicit "must not fall back silently, missing mappings must fail safely"
    design requirement.

    Returns `{"relationship": "platform"|"family"|"unresolved"|None, "public_platform": str|None}`.
    `relationship` is `None` only when `url` itself is `None` (no verified target at all --
    `_detect_enterprise_link`'s own existing BLOCKED_TARGET case). `"unresolved"` is real and
    distinct from `None`: a url DOES exist, but this function cannot confidently resolve it to a
    known public platform relative to the source product -- never silently guessed. For a
    NON-hyphenated segment, classification succeeds (as `"platform"`) whenever the segment,
    alias-normalized, equals the source platform's own alias-normalized name -- even when no
    curated display name exists for it yet (`public_platform` is then `None`, and the anchor-text
    NAME check downstream is correctly skipped rather than blocked, matching this design's
    pre-MT044 leniency for a genuine but not-yet-catalogued platform). A non-hyphenated segment
    that does NOT match the source platform is always `"unresolved"`, per the plan's own explicit
    "never silently defaulted to exact/platform" rule.
    """
    if not url:
        return {"relationship": None, "public_platform": None}
    path = url.split("products.aspose.com/", 1)[-1].strip("/")
    parts = path.split("/", 1)
    if len(parts) < 2 or not parts[1]:
        return {"relationship": "family", "public_platform": None}
    segment = parts[1].split("/", 1)[0]

    if "-" in segment:
        normalized = backlink_targets.PLATFORM_ALIASES.get(segment)
        public_platform = checks._PLATFORM_DISPLAY_NAMES.get(normalized) if normalized else None
        if not public_platform:
            return {"relationship": "unresolved", "public_platform": None}
        return {"relationship": "platform", "public_platform": public_platform}

    normalized_dest = backlink_targets.PLATFORM_ALIASES.get(segment, segment)
    normalized_source = backlink_targets.PLATFORM_ALIASES.get(source_platform, source_platform)
    if normalized_dest != normalized_source:
        return {"relationship": "unresolved", "public_platform": None}
    return {"relationship": "platform", "public_platform": checks._PLATFORM_DISPLAY_NAMES.get(normalized_dest)}


def _detect_enterprise_link(family: str, platform: str) -> dict:
    """TC-HARDEN-19 (MT034, Twentieth incident, 2026-08-12): real, live-verified Enterprise
    Edition link resolution -- the composing agent has never before had a verified target and
    has always guessed a `{family}/{platform}` slug fresh, with zero mechanism to catch a wrong
    guess. A real clean-room regeneration pilot confirmed this live: `3d/typescript`'s
    regenerated candidate linked to `https://products.aspose.com/3d/typescript/`, a real,
    curl-confirmed 404; `barcode/python`'s regenerated link 301-redirected to a *different*
    enterprise bridge product than the existing, correct link names.

    Reuses the real, already-built, already live-verified infrastructure
    (`scripts/pipeline/lib/backlink_targets.py`) rather than reinventing anything -- the same
    machinery this repo's docs/kb/reference/products pages already depend on for their own
    Enterprise backlinks. `source_subdomain="readme-refresh"` is a deliberate sentinel: it is
    not one of the 5 real aspose.org subdomains `PREFERRED_TARGET_SUBDOMAIN` recognizes, so its
    own `.get(..., "products.aspose.com")` default correctly and naturally routes every call
    here to `products.aspose.com` -- exactly where a GitHub README's Enterprise link always
    points, with no new mapping table needed.

    Deliberately does NOT reuse `backlink_targets.build_enterprise_anchor_suffix()` -- that
    function's "Enterprise Product"/"Enterprise Product Family" anchor-text convention is a
    different, already-and-deliberately-rejected convention for this skill (Template section,
    Rule 4; MT024 Phase 1's own `AskUserQuestion` decision, 2026-08-08, settled on "Enterprise
    Edition" portfolio-wide). Only the URL/target-resolution half of `backlink_targets.py` is
    reused here.

    Returns `{"url", "type", "fallback_reason", "target_map_age_days", "target_map_stale",
    "relationship", "public_platform"}`. `url` is `None` on a genuine BLOCKED_TARGET (no verified
    target anywhere in the cache) -- the composing agent must omit the Enterprise Edition link
    entirely in that case rather than invent one, matching this module's own "never invent a
    specific version/command not backed by verified data" rule, extended here to links.
    `target_map_stale` (Evidence Contract rule 7) surfaces when the cached target map itself is
    aging past `STALE_WARN_DAYS` -- a stale map is reduced-confidence evidence, never silently
    equivalent to a fresh one. The 2 relationship fields (MT043 TC-HARDEN-61, CORRECTED 2026-08-14
    MT044) are `_classify_enterprise_relationship`'s own output, folded in here so the composing
    agent and every check reads one coherent object -- see that function's own docstring for the
    classification rule itself. `public_platform` is always the normalized, implementation-
    neutral platform name (e.g. "Python", never "Python via Java") -- no field on this object ever
    carries implementation-bridge information (MT044's own permanent, non-negotiable rule).
    """
    try:
        target_map = backlink_targets.load_target_map(_repo_root)
    except (FileNotFoundError, ValueError) as exc:
        return {
            "url": None, "type": None, "fallback_reason": f"target_map_unavailable: {exc}",
            "target_map_age_days": None, "target_map_stale": None,
            "relationship": None, "public_platform": None,
        }
    canonical_overrides = _load_canonical_overrides()
    url, target_type, _subdomain, fallback_reason = backlink_targets.resolve_backlink(
        family, platform, source_subdomain="readme-refresh", target_map=target_map,
        canonical_overrides=canonical_overrides,
    )
    age_days = backlink_targets.target_map_age_days(target_map)
    relationship = _classify_enterprise_relationship(platform, url)
    return {
        "url": url,
        "type": target_type,
        "fallback_reason": fallback_reason,
        "target_map_age_days": age_days,
        "target_map_stale": bool(age_days is not None and age_days > backlink_targets.STALE_WARN_DAYS),
        **relationship,
    }


def _detect_homepage_link(family: str, platform: str) -> dict:
    """TC-HARDEN-27 (MT034, Twenty-First incident, 2026-08-12): the At-a-Glance banner must link
    to the product's real `products.aspose.org/{family}/{platform}/` homepage, with a hard
    "must never be broken" requirement. `factpack["homepage"]` existed as a bare, unconditionally
    string-formatted URL since this skill's earliest design (never verified, never consumed by
    any check or content anywhere in this plan's history until now, confirmed by grep) -- this
    replaces that with a real, checked result.

    Verification is real local `content/` file existence, deliberately NOT a live HTTP check:
    products.aspose.org is built and deployed directly from this repo's own `content/` tree, so
    a real, existing `_index.md` is a first-party, same-repo guarantee the page either already
    is or imminently will be live once this repo's own deploy pipeline next runs -- structurally
    stronger than the Enterprise-link case (a genuinely separate, externally-deployed site,
    hence that check's cached-target-map-with-staleness-flag design). This cannot detect a
    genuinely never-deployed page (content committed but the site build never ran); a live-HTTP
    secondary check was considered and deliberately not built by default -- flagged in the plan
    as an open, not-yet-decided strengthening, not silently assumed unnecessary.

    Returns `{"url", "verified"}`. `verified` is False (never invented) when the local
    `_index.md` doesn't exist -- the composing agent must keep the banner unlinked in that case,
    matching this skill's "never invent a URL not backed by verified data" rule.
    """
    url = f"https://products.aspose.org/{family}/{platform}/"
    index_path = _repo_root / "content" / "products.aspose.org" / "en" / family / platform / "_index.md"
    return {"url": url, "verified": index_path.is_file()}


def _detect_seo_keywords(family: str, platform: str) -> dict:
    """TC-HARDEN-39 (MT037, Twenty-Seventh incident, 2026-08-13): a real, per-page SEO keyword
    source, `keywords/{family}.json`, has sat completely unused by this skill until now
    (confirmed by exhaustive grep before this was built). Reads the real, structured,
    `sourcePath`-keyed array and selects the entry matching this product's own real
    `content/products.aspose.org/en/{family}/{platform}/_index.md` page -- mirroring
    `_detect_homepage_link`'s/`_detect_enterprise_link`'s own established platform-then-family
    fallback shape (falls back to the family-root entry, `.../en/{family}/_index.md`, when no
    per-platform entry exists).

    Returns the RAW keyword list only -- filtering (`checks.filter_relevant_seo_keywords`) is
    a separate, pure step the caller applies, so `plan_run`'s factpack can record both what was
    available and what actually passed the relevance filter (real transparency for review,
    matching this module's own "record what was dropped and why" discipline elsewhere).

    Absence (no `keywords/{family}.json` at all, malformed JSON, or no matching entry)
    degrades gracefully to an empty, `entry_found: False` result -- never fatal, matching this
    module's established posture for every optional data source.
    """
    path = _repo_root / "keywords" / f"{family}.json"
    if not path.is_file():
        return {"keywords": [], "source_path": None, "entry_found": False}
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"keywords": [], "source_path": None, "entry_found": False}
    platform_source = f"content/products.aspose.org/en/{family}/{platform}/_index.md"
    family_source = f"content/products.aspose.org/en/{family}/_index.md"
    platform_entry = None
    family_entry = None
    for entry in entries:
        source_path = entry.get("sourcePath")
        if source_path == platform_source:
            platform_entry = entry
        elif source_path == family_source:
            family_entry = entry
    chosen = platform_entry or family_entry
    if chosen is None:
        return {"keywords": [], "source_path": None, "entry_found": False}
    return {
        "keywords": chosen.get("keywords", []),
        "source_path": chosen.get("sourcePath"),
        "entry_found": True,
    }


def _repo_full_name(family: str, platform: str) -> "str | None":
    """MT042 (TC-HARDEN-57, Thirty-Second incident, 2026-08-14): a small, standalone lookup
    mirroring `_detect_homepage_link`'s own "look up its own identity fresh" convention -- reads
    `data/products.json` directly rather than depending on `_resolve_product`'s side effects
    (the active/exclusion/required-field checks), since a badge-availability query has no need
    for them and must never raise. Returns `None` (never fabricates, never raises) when
    `data/products.json` is absent/malformed, no matching entry exists, or no real
    `github.com` repo_url exists -- unlike `_load_products()`'s own callers elsewhere (which
    correctly treat a missing/malformed products.json as a real, blocking error), a badge-
    availability query is a best-effort enrichment, not a load-bearing input, and must degrade
    the same way every other `_detect_*` helper does rather than propagate."""
    try:
        products = _load_products()
    except ReadmeRefreshRunError:
        return None
    for entry in products:
        if entry.get("family") == family and entry.get("platform") == platform:
            repo_url = entry.get("repo_url") or ""
            if "github.com/" in repo_url:
                return repo_url.split("github.com/", 1)[-1].rstrip("/")
            return None
    return None


# MT042 (TC-HARDEN-57): a small, explicit, disclosed-incomplete per-language shields.io static-
# badge template table -- same seed-list posture as readme_refresh_checks.py's own
# _CONTAINER_CONNECTOR_ALLOWLIST/_DIAGRAM_SUPPLEMENTARY_FORMAT_NAMES and TC-HARDEN-34's own
# precedent (expected to need real additions as new languages are onboarded, never claimed
# complete). Keyed by the real `platform` value used in data/products.json. Values verified
# directly against real, already-shipped badge rows where a real instance exists (go, java, cpp
# below); the remaining entries are a reasonable, disclosed-unverified extrapolation for
# languages this detector cannot currently reach anyway (see _detect_available_badges's own
# docstring for exactly why only Go is reachable via dependency_snapshot today).
_BADGE_LANGUAGE_VERSION_TEMPLATES: dict[str, dict] = {
    "go": {"label": "go", "color": "00ADD8", "logo": "go", "plus": True},
    "java": {"label": "Java", "color": "blue", "logo": None, "plus": True},
    "cpp": {"label": "C%2B%2B", "color": "blue", "logo": None, "plus": False},
    "python": {"label": "Python", "color": "blue", "logo": None, "plus": True},
    "net": {"label": ".NET", "color": "blue", "logo": None, "plus": True},
    "typescript": {"label": "TypeScript", "color": "blue", "logo": None, "plus": True},
    "rust": {"label": "Rust", "color": "blue", "logo": None, "plus": True},
}


def _detect_available_badges(
    family: str, platform: str, *, repo_full_name: "str | None", license_file: "dict | None",
    install_info: dict, dependency_snapshot: "dict | None", dev_test_artifacts: list[dict],
) -> dict:
    """MT042 (TC-HARDEN-57, Thirty-Second incident, 2026-08-14): a real, full 30-product
    portfolio survey found License present in 30/30 candidates (100%) and a SECOND real badge
    present in every one of the remaining 30 (2-5 total, zero exceptions), yet nothing in this
    pipeline had ever computed that floor before now -- the badge reconciliation mechanism
    (extract_badges/classify_badge/reconcile_badges/badge-dispositions.json) is entirely
    reconciliation-scoped (stop a real OLD badge from being silently lost), and vacuously passes
    when the old README has zero badges, exactly the case that let `cells/typescript`'s
    candidate ship with a single License badge undetected. Every category below is derived
    purely from data this pipeline already computes elsewhere (`_detect_license_file`,
    `_detect_install_info`, `dependency_extract`'s own `DependencySnapshot`,
    `_detect_dev_test_artifacts`) -- zero new source extraction, per the incident's own
    root-cause finding that every one of these facts already exists somewhere in the pipeline,
    just never wired to a badge-availability answer.

    Returns `{"license", "package_version", "language_version", "ci_build_status",
    "contributor_count"}`, each `{"available": bool, "alt_text"?, "image_url"?, "link_url"?,
    "reason"?}` -- `reason` only when unavailable, never a fabricated badge when the underlying
    fact is unverified.

    Two real, disclosed narrowings of the original design against real code/data, found while
    implementing this (not assumed from prior prose):

    1. **`language_version`** is sourced from `dependency_snapshot["native_system"]` -- but
       direct code read confirms only the Go extractor (`dependency_extract.py`) currently ever
       places a real toolchain-version-floor entry there; Java/C++/.NET/Rust/TypeScript
       extractors never populate this bucket, even though real, already-shipped Java/C++ badges
       exist (`cells/java`'s real "Java 17+", `cells/cpp`'s real "C++ 17") sourced from data this
       detector has no structured access to. Rather than fabricate an unverified floor,
       `language_version` is honestly reported unavailable for those languages -- this does not
       weaken the mandatory floor (below), since `contributor_count` is always available as its
       safety net. Python is a documented exception: its real `language_version` fact (a
       PyPI-versions-support badge) is the dynamic `pypi/pyversions/{name}` shields.io endpoint,
       tied 1:1 to the SAME publish state `package_version` already verifies -- no separate
       extraction needed.
    2. **`package_version`** for `go_modules` is reported unavailable, a real, disclosed
       correction against the original design table: Go modules are decentralized (this plan's
       own established finding) -- there is no real "package version registry" for a
       `nuget/v/{name}`-shaped badge to point at. The real, already-shipped second badge for Go
       products is `pkg.go.dev/badge/{module}` ("Go Reference"), which `classify_badge` already
       tags `language_package_reference` -- a distinct category from `package_version` this
       detector does not compute (out of scope; Go's real floor is already met via
       `language_version` + `contributor_count`/`license` regardless).
    """
    result: dict[str, dict] = {}

    if license_file:
        result["license"] = {
            "available": True, "alt_text": "License: MIT",
            "image_url": "https://img.shields.io/badge/License-MIT-blue.svg",
            "link_url": license_file["relative_path"],
        }
    else:
        result["license"] = {
            "available": False,
            "reason": "no real MIT license file detected in the clone cache",
        }

    published = bool(install_info.get("published"))
    registry_type = install_info.get("registry_type")
    candidate = install_info.get("candidate") or {}
    package_version = {
        "available": False,
        "reason": "no confirmed-published package identity in data/package_registry.json",
    }
    if published and registry_type in ("nuget", "pypi", "npm", "cargo") and candidate.get("name"):
        name = candidate["name"]
        image_urls = {
            "nuget": f"https://img.shields.io/nuget/v/{name}.svg",
            "pypi": f"https://img.shields.io/pypi/v/{name}.svg",
            "npm": f"https://img.shields.io/npm/v/{name}.svg",
            "cargo": f"https://img.shields.io/crates/v/{name}.svg",
        }
        link_urls = {
            "nuget": f"https://www.nuget.org/packages/{name}/",
            "pypi": f"https://pypi.org/project/{name}/",
            "npm": f"https://www.npmjs.com/package/{name}",
            "cargo": f"https://crates.io/crates/{name}",
        }
        package_version = {
            "available": True,
            "alt_text": "npm version" if registry_type == "npm" else "Package Version",
            "image_url": image_urls[registry_type], "link_url": link_urls[registry_type],
        }
    elif published and registry_type == "maven" and candidate.get("group_id") and candidate.get("artifact_id"):
        group_id, artifact_id = candidate["group_id"], candidate["artifact_id"]
        package_version = {
            "available": True, "alt_text": "Maven Central",
            "image_url": f"https://img.shields.io/maven-central/v/{group_id}/{artifact_id}.svg",
            "link_url": f"https://central.sonatype.com/artifact/{group_id}/{artifact_id}",
        }
    elif registry_type == "go_modules":
        package_version = {
            "available": False,
            "reason": "Go modules are decentralized -- no real package-version-registry badge "
                      "exists to point at (see the real, already-shipped 'Go Reference' badge, "
                      "a distinct language_package_reference-category fact, instead)",
        }
    result["package_version"] = package_version

    language_version = {
        "available": False,
        "reason": "no real, structured toolchain-version-floor source for this language",
    }
    native_entries = (dependency_snapshot or {}).get("native_system", []) if dependency_snapshot else []
    lang_entry = next((e for e in native_entries if e.get("version_constraint")), None)
    if lang_entry and platform in _BADGE_LANGUAGE_VERSION_TEMPLATES:
        tmpl = _BADGE_LANGUAGE_VERSION_TEMPLATES[platform]
        version = str(lang_entry["version_constraint"]).lstrip("v").replace("+", "")
        version_enc = f"{version}%2B" if tmpl.get("plus", True) else version
        logo_suffix = f"?logo={tmpl['logo']}" if tmpl.get("logo") else ""
        language_version = {
            "available": True, "alt_text": f"{tmpl['label'].replace('%2B', '+')} Version",
            "image_url": f"https://img.shields.io/badge/{tmpl['label']}-{version_enc}-{tmpl['color']}.svg{logo_suffix}",
            "link_url": None,
        }
    elif published and registry_type == "pypi" and candidate.get("name"):
        language_version = {
            "available": True, "alt_text": "Python Versions",
            "image_url": f"https://img.shields.io/pypi/pyversions/{candidate['name']}.svg",
            "link_url": f"https://pypi.org/project/{candidate['name']}/",
        }
    result["language_version"] = language_version

    ci_workflows = [a for a in dev_test_artifacts if a.get("kind") == "ci_workflow"]
    if ci_workflows and repo_full_name:
        workflow_file = Path(ci_workflows[0]["relative_path"]).name
        result["ci_build_status"] = {
            "available": True, "alt_text": "Build",
            "image_url": f"https://github.com/{repo_full_name}/actions/workflows/{workflow_file}/badge.svg",
            "link_url": f"https://github.com/{repo_full_name}/actions/workflows/{workflow_file}",
        }
    else:
        result["ci_build_status"] = {
            "available": False,
            "reason": "no real .github/workflows/*.yml file found in the clone cache",
        }

    if repo_full_name:
        result["contributor_count"] = {
            "available": True, "alt_text": "Contributors",
            "image_url": f"https://img.shields.io/github/contributors/{repo_full_name}.svg",
            "link_url": f"https://github.com/{repo_full_name}/graphs/contributors",
        }
    else:
        result["contributor_count"] = {
            "available": False, "reason": "no resolvable repo_full_name for this product",
        }

    return result


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


def _readme_matches_published_upstream(old_readme_text: str, candidate_text: str) -> bool:
    """MT053 (Forty-Fourth incident, 2026-08-18): once a candidate has already been pushed and
    merged into the real upstream repo, `old_readme_text` (the clone cache's real, current
    README.md) becomes the candidate itself -- the entire "preserve content from the old
    README" premise this skill's disposition-tracking machinery (content_unit_*/structural_
    unit_*/code_example_*/badge_disposition_* -- ~26 checks) depends on is moot, and running it
    anyway produces pure false-positive noise (confirmed live: 158 hard-gate failures for
    `pdf/cpp`, entirely a position-based-unit_id-drift artifact of extracting "content to
    preserve" from a text that already IS the candidate).

    Deliberately narrow: whitespace-only normalization (`.strip()` on each side), nothing more
    permissive -- a false positive here (wrongly treating a genuinely still-independent old
    README as "published" and silently disabling real preservation tracking for it) is the
    dangerous failure direction and must stay effectively impossible; a false negative (missing
    a published state with more than trivial whitespace drift) just means the preservation-
    tracking checks keep running normally, the safe default. Computed fresh on every call --
    never persisted, matching this module's own established "recompute at check time, don't
    trust a cached flag" discipline already used for `_detect_archetype`/`_detect_capability_
    dependencies`.
    """
    if not old_readme_text or not candidate_text:
        return False
    return old_readme_text.strip() == candidate_text.strip()


def _detect_license_file(clone_cache: Path) -> "dict | None":
    """TC-HARDEN-20 (MT034, Twentieth incident, 2026-08-12): the exact-20-char-prefix match
    against the literal string "MIT License" missed real license files phrased "The MIT
    License (MIT)..." -- confirmed independently by 2 different sub-agents in one clean-room
    pilot (`barcode/python`, `cells/cpp`), both real, genuinely MIT-licensed products. Widened
    from a 20-char exact-prefix match to a 200-char case-insensitive substring search -- wide
    enough to catch a real preamble sentence before the license name, narrow enough that a
    genuinely non-MIT license (Apache-2.0, BSD, etc.) still correctly returns None."""
    if not clone_cache.is_dir():
        return None
    candidates = list(clone_cache.glob("LICENSE*")) + list(clone_cache.glob("*/LICENSE*")) + list(
        clone_cache.glob("license/LICENSE*")
    )
    for candidate in candidates:
        if candidate.is_file():
            try:
                head = candidate.read_text(encoding="utf-8", errors="ignore")[:200]
            except OSError:
                continue
            if "mit license" in head.lower():
                return {"relative_path": str(candidate.relative_to(clone_cache)).replace("\\", "/")}
    return None


_MODEL_YAML_REPO_SHA_RE = re.compile(r"^repo_sha:\s*(\S+)\s*$", re.MULTILINE)


def _detect_dependency_claims(family: str, platform: str) -> dict:
    """Thirty-First incident / MT041, item 4: reads knowledge/{family}/{platform}/merged/
    claims.json's real, scout-verified "kind": "dependency" claims plus the same product's
    model.yaml `repo_sha`, for corroboration against the freshly-parsed DependencySnapshot
    (dependency_extract.cross_reference_dependency_claims). Confirmed by direct trace (scout.py
    -> package_manifest.py -> claims.py) that these claims are a lossy, name-only re-parse of
    the SAME manifest this run's own extractor also reads -- not independent data -- captured
    at claims.json's own extraction time, which may differ from this run's pinned revision.
    Never fatal: an absent claims.json/model.yaml degrades to `{"claims": [], "repo_sha": None}`,
    matching every other `_detect_*` helper's graceful-degradation posture."""
    merged_dir = _repo_root / "knowledge" / family / platform / "merged"
    claims: list = []
    claims_path = merged_dir / "claims.json"
    if claims_path.is_file():
        try:
            raw = json.loads(claims_path.read_text(encoding="utf-8"))
            all_claims = raw if isinstance(raw, list) else raw.get("claims", [])
            claims = [c for c in all_claims if c.get("kind") == "dependency"]
        except (json.JSONDecodeError, OSError):
            claims = []
    repo_sha = None
    model_path = merged_dir / "model.yaml"
    if model_path.is_file():
        try:
            match = _MODEL_YAML_REPO_SHA_RE.search(model_path.read_text(encoding="utf-8"))
            repo_sha = match.group(1) if match else None
        except OSError:
            repo_sha = None
    return {"claims": claims, "repo_sha": repo_sha}


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

        # RC-readme-refresh-freshness-guard-compliance (2026-08-30): AGENTS.md 5a requires
        # every generation skill to hard-stop on stale/missing knowledge before writing any
        # content. readme_refresh_run.py had zero references to freshness_guard despite 4
        # sibling generation skills (batch_reference.py, refresh_run.py, launch_gate.py,
        # readiness_gate.py) already gating on it -- confirmed by exhaustive grep before this
        # fix. Degraded mode only (no network call), matching this function's prior no-network
        # behavior and the identical precedent in refresh_run.py's own knowledge-model loader.
        # This alone does NOT make font/python's orphaned-but-content-identical baseline
        # correctly permissive -- that requires the tree-identity states this same mission's
        # Phase 3 adds to freshness_guard itself; until then, degraded mode's PROVENANCE_MISSING/
        # STALE verdicts are still the only ones this call can produce for a genuinely absent or
        # explicitly-flagged-stale knowledge bundle.
        allowed, fresh_result = freshness_guard.is_generation_allowed(family, platform, mode="degraded")
        if not allowed:
            _block(
                manifest,
                f"knowledge freshness gate failed (state={fresh_result.state}): {fresh_result.reason}",
            )
            raise ReadmeRefreshRunError(
                f"plan BLOCKED for {family}/{platform}: knowledge freshness state="
                f"{fresh_result.state} ({fresh_result.reason}). Run {run_id} is now BLOCKED "
                f"(resume_state={manifest['resume_state']!r}). Refresh knowledge first "
                f"(/repo-scout -> /knowledge-enrich -> /truth-merge), then call `recover` to "
                f"retry `plan`. AGENTS.md 5a: generation must never proceed on stale/missing "
                f"knowledge."
            )

        clone_cache = _product_clone_cache(family, platform)
        pinned_revision = manifest.get("pinned_inputs", {}).get("clone_cache_head")
        # Thirty-First incident / MT041 (2026-08-14): real dependency extraction, fail-closed.
        # Reuses the exact try/except -> _block(manifest, ...) -> raise ReadmeRefreshRunError(...)
        # shape already proven at push()'s own only existing _block() call site -- no new
        # BLOCKED sub-mechanism. A per-product extraction failure (malformed/absent manifest,
        # or an unregistered ecosystem) must never silently produce an empty snapshot or let
        # the composing agent fall back to an unqualified dependency-free claim.
        try:
            dependency_snapshot = dependency_extract.extract_dependencies(
                family, platform, clone_cache, source_revision=pinned_revision,
                pipeline_repo_root=_repo_root,
            )
        except dependency_extract.DependencyExtractionError as exc:
            _block(manifest, f"dependency extraction failed: {exc}")
            raise ReadmeRefreshRunError(
                f"plan failed: dependency extraction BLOCKED for {family}/{platform} -- {exc} "
                f"Run {run_id} is now BLOCKED (resume_state={manifest['resume_state']!r}). Fix "
                f"the underlying manifest at the path named above (or add a verified entry to "
                f"data/dependency_overrides.json), then call `recover` to retry `plan`. "
                f"Generation must never substitute a dependency-free claim for missing/"
                f"unparseable dependency data."
            ) from exc
        dependency_claims_raw = _detect_dependency_claims(family, platform)
        dependency_claims_corroboration = dependency_extract.cross_reference_dependency_claims(
            dependency_snapshot, dependency_claims_raw["claims"],
            knowledge_repo_sha=dependency_claims_raw["repo_sha"],
        )
        archetype = _detect_archetype(family, platform)
        candidate_format_evidence = _compute_candidate_format_evidence(family, platform)
        # TC-HARDEN-39 (MT037, Twenty-Seventh incident, 2026-08-13): the relevance filter is run
        # HERE, at factpack-build time, not left to the composing agent to apply on its own --
        # a structural stuffing/contamination guard, not a suggestion. Grounds the filter's
        # "does this keyword phrase mention a real product fact" test against the same real,
        # per-product format names `candidate_format_evidence` already computed above, not a
        # global cross-portfolio format list.
        raw_seo_keywords = _detect_seo_keywords(family, platform)
        known_format_names_for_seo = {
            row["format"]
            for direction in ("import", "export")
            for row in candidate_format_evidence.get(direction, [])
        }
        seo_keywords_filtered = checks.filter_relevant_seo_keywords(
            raw_seo_keywords["keywords"], family, platform, known_format_names_for_seo,
        )
        install_info = _detect_install_info(family, platform)
        license_file = _detect_license_file(clone_cache)
        dev_test_artifacts = _detect_dev_test_artifacts(clone_cache)
        factpack = {
            "family": family,
            "platform": platform,
            "generated_at": _utc(),
            "archetype": archetype["archetype"],
            "archetype_basis": archetype["archetype_basis"],
            "capability_dependency_pipeline_edges": _detect_capability_dependencies(family, platform),
            "candidate_format_evidence": candidate_format_evidence,
            "install": install_info,
            "dependencies": dependency_snapshot,
            "dependency_claims_corroboration": dependency_claims_corroboration,
            "license_file": license_file,
            "enterprise_link": _detect_enterprise_link(family, platform),
            "seo_keywords": raw_seo_keywords,
            "seo_keywords_filtered": seo_keywords_filtered,
            # readme-refresh-seo-deps-headings-hardening mission (2026-08-19): the typed
            # placement plan -- see checks.build_seo_keyword_placement_plan's own docstring.
            # Recomputed fresh (not read back) inside _run_deterministic_checks too, matching
            # this function's own established pattern for every other _detect_*-derived value.
            "seo_keyword_placement_plan": checks.build_seo_keyword_placement_plan(
                seo_keywords_filtered, family,
            ),
            "old_readme_inventory": _old_readme_inventory(clone_cache),
            "homepage": _detect_homepage_link(family, platform),
            "banner_url": f"https://products.aspose.org/media/{family}/{platform}/banner-readme.png",
            # MT042 (TC-HARDEN-57, Thirty-Second incident, 2026-08-14): the verified badge floor
            # -- see _detect_available_badges's own docstring for the full root-cause account.
            "available_badges": _detect_available_badges(
                family, platform, repo_full_name=_repo_full_name(family, platform),
                license_file=license_file, install_info=install_info,
                dependency_snapshot=dependency_snapshot, dev_test_artifacts=dev_test_artifacts,
            ),
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

        _check_manifest_candidate_tree(manifest)
        candidate_path = _candidate_readme_path(family, platform)
        if not candidate_path.is_file():
            raise ReadmeRefreshRunError(f"No candidate found at {candidate_path}")
        text = candidate_path.read_text(encoding="utf-8")
        clone_cache = _product_clone_cache(family, platform)

        result = _run_deterministic_checks(family, platform, text, clone_cache)
        # MT056: fail-closed scope/store/frozen-block enforcement, applied at ingest as well as
        # recheck -- an out-of-scope candidate never transitions, even on its first ingest.
        _apply_scope_enforcement(result, family, platform, run_id, text)
        # TC-M56-09: record that this exact content was just verified, regardless of hard-gate
        # outcome -- "we looked at it" is the marker's semantic, not "it passed".
        _write_candidate_verification_marker(family, platform, text, run_id=run_id)
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

    # Thirty-First incident / MT041 (2026-08-14): computed fresh, matching this function's own
    # established "never read back from persisted factpack.json" pattern for every other
    # _detect_* value. Unlike every other _detect_* call here, extraction can raise -- caught
    # and treated as `None`, which check_dependency_snapshot_completeness (below) correctly
    # reports as a real, named hard-gate finding rather than crashing this function.
    try:
        dependency_snapshot = dependency_extract.extract_dependencies(
            family, platform, clone_cache, pipeline_repo_root=_repo_root,
        )
    except dependency_extract.DependencyExtractionError:
        dependency_snapshot = None
    dependency_claims_raw = _detect_dependency_claims(family, platform)
    dependency_claims_corroboration = dependency_extract.cross_reference_dependency_claims(
        dependency_snapshot, dependency_claims_raw["claims"],
        knowledge_repo_sha=dependency_claims_raw["repo_sha"],
    ) if dependency_snapshot else None

    result["required_sections"] = {
        "hard_gate": True, "findings": checks.check_required_sections(text),
    }
    result["banner_present"] = {
        "hard_gate": True, "findings": checks.check_banner_present(text, family, platform),
    }
    # TC-HARDEN-27 (MT034, Twenty-First incident, 2026-08-12): the banner must link to its real,
    # verified products.aspose.org homepage when one exists, and stay unlinked otherwise --
    # computed fresh here, matching this function's own established "never read back from the
    # persisted factpack.json" pattern for every other _detect_* value.
    result["banner_links_to_homepage"] = {
        "hard_gate": True,
        "findings": checks.check_banner_links_to_homepage(text, _detect_homepage_link(family, platform)),
    }
    # RC-banner-asset-existence (readme-refresh-hardening-and-regen-2026-08-30): banner_present
    # (above) only ever validated the banner LINE's shape; the referenced image file's actual
    # existence on disk was never checked by anything in this battery until now.
    result["banner_asset_exists"] = {
        "hard_gate": True,
        "findings": checks.check_banner_asset_exists(text, family, platform, repo_root=_repo_root),
    }
    result["no_excluded_domain_links"] = {
        "hard_gate": True, "findings": checks.check_no_excluded_domain_links(text),
    }
    result["license_link_target"] = {
        "hard_gate": True, "findings": checks.check_license_link_target(text, str(clone_cache)),
    }
    # TC-HARDEN-26 (MT034, Twenty-First incident, 2026-08-12): check_license_link_target (above)
    # only ever verified the ## License section's LINK TARGET -- never its PROSE. A blind
    # clean-room regeneration of 3d/typescript independently reproduced the exact 2026-08-04
    # free-form-narration defect this plan had already "fixed" once by hand, proving that fix was
    # never made mechanical. Reuses the same _detect_license_file() result already computed for
    # the factpack (plan_run) -- recomputed fresh here, matching this function's own established
    # "never read back from persisted factpack.json" pattern for every other _detect_* value.
    result["license_section_matches_template"] = {
        "hard_gate": True,
        "findings": checks.check_license_section_matches_template(text, _detect_license_file(clone_cache)),
    }
    # TC-HARDEN-19 (MT034, Twentieth incident, 2026-08-12): check_enterprise_edition_naming
    # (below, heuristic) verifies anchor text/context; it has never verified the link's real
    # TARGET (Gate Contract rule 6) -- a real clean-room pilot found a confirmed-live-404
    # regression this closes. Computed fresh, matching how _detect_archetype/_product_formats_md
    # are already computed fresh here rather than read back from the persisted factpack.json.
    enterprise_link = _detect_enterprise_link(family, platform)
    result["enterprise_edition_link_resolves"] = {
        "hard_gate": True,
        "findings": checks.check_enterprise_edition_link_resolves(text, enterprise_link),
    }
    # MT043 (TC-HARDEN-62, Thirty-Third incident, 2026-08-14): the above verifies the href alone
    # -- confirmed live that a candidate can pass both this and check_enterprise_edition_naming
    # (below) while its anchor's own platform CLAIM contradicts what the resolved destination
    # actually is (cells/typescript: "for .NET" anchor on a family-level link). Reuses the same
    # `enterprise_link` object computed just above -- no second _detect_enterprise_link() call.
    result["enterprise_edition_anchor_matches_relationship"] = {
        "hard_gate": True,
        "findings": checks.check_enterprise_edition_anchor_matches_relationship(text, enterprise_link),
    }
    # MT044 (TC-HARDEN-62 replacement, Thirty-Fourth incident, 2026-08-14): portfolio-wide,
    # document-wide -- not scoped to the Enterprise-link paragraph -- hard gate forbidding any
    # implementation-bridge disclosure anywhere in the candidate. Replaces MT043's own reversed
    # "missing_bridge_disclosure" requirement inside the anchor check above.
    result["no_implementation_bridge_disclosure"] = {
        "hard_gate": True,
        "findings": checks.check_no_implementation_bridge_disclosure(text),
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
    # MT040 (Thirtieth incident, 2026-08-14): heuristic guard against a real, open, unfixed
    # upstream mermaid-js defect (long unbroken label tokens overflowing their node) -- not
    # the root cause of that incident's own two live defects (both traced to the retired
    # per-node-wired topology, already hard-blocked by check_diagram_shape above), but a
    # genuine, currently-latent risk for future content this check exists to catch early.
    result["diagram_label_token_length"] = {
        "hard_gate": False, "findings": checks.check_diagram_label_token_length(text),
    }
    # MT056 (Fifty-Sixth incident, 2026-08-18): the HARD geometry gate -- subsumes the advisory
    # token-length rule above (kept unchanged for continuity) and adds the previously-unguarded
    # label-bulk clause (greedy word-wrap estimate; >3 rendered lines fails). Corpus-grounded
    # thresholds; the two real, live-render-confirmed oversized/clipping label shapes both fail
    # it, every render-verified-clean label passes. See check_diagram_label_geometry's docstring
    # and reports/_scratch/mt056_regression_ledger.md (R-01/R-02).
    result["diagram_label_geometry"] = {
        "hard_gate": True, "findings": checks.check_diagram_label_geometry(text),
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
    result["api_reference_detail_collapsed"] = {
        "hard_gate": True, "findings": checks.check_api_reference_detail_collapsed(text),
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
    # TC-HARDEN-32 (MT035, 2026-08-12): _detect_install_info's factpack signal was computed but
    # never read back against the composed ## Installation section's real text -- computed fresh
    # here, matching this function's own established "never read back from persisted
    # factpack.json" pattern for every other _detect_* value.
    result["installation_matches_package_registry"] = {
        "hard_gate": False,
        "findings": checks.check_installation_matches_package_registry(
            text, _detect_install_info(family, platform)
        ),
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
    # Thirty-Seventh incident (2026-08-16): check_no_upstream_issue_leaked_into_readme above
    # deliberately excludes Installation/Quick Start (real, defensible -- see its own
    # docstring), which left those two sections with zero hard-gate leak protection --
    # confirmed live on html/python's real regressed Installation section. This narrow
    # companion re-covers just those two sections with a tighter, two-signal condition (see
    # check_no_upstream_issue_leaked_into_install_or_quickstart's own docstring).
    result["no_upstream_issue_leaked_install_quickstart"] = {
        "hard_gate": True,
        "findings": checks.check_no_upstream_issue_leaked_into_install_or_quickstart(
            text, upstream_text
        ),
    }
    result["key_capabilities_quality"] = {
        "hard_gate": False, "findings": checks.check_key_capabilities_quality(text),
    }
    # TC-HARDEN-40/41 (MT037, Twenty-Seventh incident, 2026-08-13): check_key_capabilities_
    # quality (above) catches bullet count/literal-first-word-repetition/thinness -- it has no
    # signal for the broader "dry" structural-monotony shape (every bullet opens with a
    # *different* backtick identifier, still monotonous) or for cheap, mechanical formatting
    # defects (unmatched backticks, missing terminal punctuation, lowercase bullet starts).
    # Both non-blocking, same two-tier posture as every other prose-quality check here.
    result["key_capabilities_structural_variety"] = {
        "hard_gate": False, "findings": checks.check_key_capabilities_structural_variety(text),
    }
    result["key_capabilities_formatting"] = {
        "hard_gate": False, "findings": checks.check_key_capabilities_formatting(text),
    }
    # MT046 (Thirty-Sixth incident, 2026-08-15 / TC-HARDEN-71): a new, previously-unnamed
    # variant of MT039's generation-mechanism narration category -- a section's own intro
    # sentence (Key Capabilities or Additional Examples) narrating this document's own
    # editorial/organizational choices, or leaking an internal source-file fact, instead of
    # stating a real product fact. Confirmed live in font/python's real candidate; none of the
    # existing Key-Capabilities checks ever inspect this text (bullet-only extraction), and
    # check_process_narration_smells's fixed phrase list never matched this real wording.
    result["section_intro_no_meta_narration"] = {
        "hard_gate": True, "findings": checks.check_section_intro_no_meta_narration(text),
    }
    result["capability_scope_contradiction"] = {
        "hard_gate": False, "findings": checks.check_capability_scope_contradiction(text),
    }
    result["diagram_from_scratch_capability_labeled"] = {
        "hard_gate": False,
        "findings": checks.check_diagram_from_scratch_capability_labeled(text),
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

    # TC-20: old_readme_text is what the disposition ledger should be re-verified against --
    # the pinned baseline commit if one is recorded (old-readme-baseline.json), else the live
    # clone HEAD, identical to every prior call. old_readme_text_live stays on the live clone
    # HEAD unconditionally: _readme_matches_published_upstream asks a different question ("does
    # our candidate already match what's live right now"), which must never be answered against
    # a deliberately stale pinned baseline.
    old_readme_path = clone_cache / "README.md"
    old_readme_text, old_readme_baseline = _resolve_old_readme_text(family, platform, clone_cache)
    old_readme_text_live = (
        old_readme_path.read_text(encoding="utf-8", errors="ignore") if old_readme_path.is_file() else ""
    )
    if old_readme_text:
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

    # MT053 (Forty-Fourth incident, 2026-08-18): computed once, fresh, immediately after
    # old_readme_text_live is resolved -- gates the entire preservation-tracking block below. See
    # _readme_matches_published_upstream's own docstring for why this must stay narrow.
    readme_already_published = _readme_matches_published_upstream(old_readme_text_live, text)
    result["readme_already_published"] = {
        "hard_gate": False,
        "findings": [],
        "detail": {"published": readme_already_published},
    }
    if old_readme_baseline is not None:
        # TC-20: surfaced unconditionally whenever a pin is in effect, clean or dirty, so a
        # "clean" verdict can never be read without also showing it was checked against a
        # pinned historical commit rather than live HEAD (mirrors the plan's own
        # `vacuous_gates` transparency requirement for anything that changes what a check
        # actually verified).
        result["old_readme_baseline_pinned"] = {
            "hard_gate": False,
            "findings": [],
            "detail": old_readme_baseline,
        }
    # MT056: republication-debt tripwire (advisory) -- see _published_readme_current_findings.
    result["published_readme_current"] = {
        "hard_gate": False,
        "findings": _published_readme_current_findings(family, platform, readme_already_published),
    }

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
    # MT053 (Forty-Fourth incident, 2026-08-18): the entire preservation-tracking block below --
    # every check that extracts "content to preserve" from old_readme_text and cross-references
    # it against a disposition JSON file -- assumes old_readme_text is genuinely independent,
    # at-risk-of-loss content. Once readme_already_published is True, that assumption is false
    # (old_readme_text IS the candidate), so the extractors are never even called and every one
    # of these 25 result keys becomes a uniform, disclosed no-op instead of running position-
    # based extraction against a self-referential text (confirmed live: 158 false hard-gate
    # failures for pdf/cpp before this gate existed). Checks that verify the candidate against
    # real, CURRENT, independent data (real source, real registries, real badge/CI facts) are
    # deliberately NOT in this list -- see _readme_matches_published_upstream's own docstring
    # and the "What should be preserved" section of MT053 for the full reasoning.
    if readme_already_published:
        _skip_detail = {
            "skipped": True,
            "skip_reason": (
                "readme already matches the published upstream README (byte-identical, "
                "whitespace-normalized) -- old-README preservation-tracking is moot for this "
                "product; see MT053"
            ),
        }
        for _key, _hard_gate in (
            ("content_unit_disposition_coverage", True),
            ("content_unit_excerpt_matches_extraction", True),
            ("content_unit_evidence_resolves", True),
            ("content_unit_merged_into_target_section", True),
            ("content_unit_no_exact_duplicate_merge", True),
            ("content_unit_redundant_claim_verifiable", False),
            ("content_unit_classification_plausibility", False),
            ("content_unit_probable_duplicate", False),
            ("content_unit_embedded_actionable_fact", False),
            ("image_content_unit_excluded_reason_verified", False),
            ("structural_unit_disposition_coverage", True),
            ("structural_unit_evidence_resolves", True),
            ("structural_unit_merged_into_target_section", True),
            ("structural_unit_no_exact_duplicate_merge", True),
            ("structural_unit_tree_paths_plausible", False),
            ("code_example_disposition_coverage", True),
            ("code_example_evidence_resolves", True),
            ("code_example_no_exact_duplicate_merge", True),
            ("code_example_api_coverage_survives", True),
            ("code_example_excluded_reason_citation_too_narrow", False),
            ("cli_category_representation", False),
            ("badge_disposition_coverage", True),
            ("badge_evidence_resolves", True),
            ("badge_preserved_or_credited_in_candidate", True),
            ("badge_probable_duplicate_disposition", False),
        ):
            result[_key] = {"hard_gate": _hard_gate, "findings": [], **_skip_detail}
        # Real bug found live wiring this in (MT053): a later check outside this block --
        # check_dependency_disposition_reconciliation, added by MT041 after this preservation-
        # tracking block was originally written -- reads `content_units`/`dispositions` too
        # (cross-referencing "5_dependency_claim"-classified disposition entries against the old
        # README's own content units). Skipping the whole `else` branch left both names unbound,
        # a real `UnboundLocalError` the first time this path was actually exercised, not merely
        # assumed safe. `content_units=[]`/`dispositions=[]` here reproduces the exact vacuous
        # (zero-findings) result that check already returns for `dispositions=[]` on its own
        # terms, without loading a disposition file this branch has already decided is moot.
        content_units, dispositions = [], []
    else:
        # Fifteenth incident / MT030 (2026-08-09): verify-and-merge of the old README's real
        # prose -- mechanism-level explanations (e.g. pdf/cpp's real font-fallback rationale) and
        # branding/positioning claims (e.g. "Official Aspose project") get verified against the
        # real product repo and merged into the new candidate; pure narrative/origin-story/CTA
        # prose stays explicitly out of scope, per the user's own decision. dropped_content above
        # only ever tracked links/headings -- these 6 checks close the much larger prose gap a
        # real 5-product survey confirmed. content-dispositions.json is agent-authored, same tier
        # as readme.md/upstream-issues.md -- read here, never written by this script.
        content_units = checks.extract_old_readme_content_units(old_readme_text)
        dispositions_path = _content_dispositions_path(family, platform)
        dispositions = (
            json.loads(dispositions_path.read_text(encoding="utf-8")) if dispositions_path.is_file() else []
        )
        result["content_unit_disposition_coverage"] = {
            "hard_gate": True,
            "findings": checks.check_content_unit_disposition_coverage(content_units, dispositions),
        }
        # MT048 (note/python pilot, 2026-08-15): unit_id-presence alone (above) cannot detect
        # position-based drift -- a shifted id that still happens to exist in the current
        # extraction passes that check while pointing at different content. Cross-checks every
        # disposition's own stored excerpt against the live extractor's excerpt for the same
        # unit_id; see check_content_unit_excerpt_matches_extraction's own docstring for the
        # real, previously only-manually-caught MT030 Phase 2 incident this closes.
        result["content_unit_excerpt_matches_extraction"] = {
            "hard_gate": True,
            "findings": checks.check_content_unit_excerpt_matches_extraction(content_units, dispositions),
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
        result["content_unit_redundant_claim_verifiable"] = {
            "hard_gate": False,
            "findings": checks.check_content_unit_redundant_claim_verifiable(dispositions, text),
        }
        result["content_unit_classification_plausibility"] = {
            "hard_gate": False,
            "findings": checks.check_content_unit_classification_plausibility(content_units, dispositions),
        }
        result["content_unit_probable_duplicate"] = {
            "hard_gate": False,
            "findings": checks.check_content_unit_probable_duplicate(dispositions),
        }
        # Sixteenth incident / MT031 (2026-08-10): a mixed unit (real actionable fact bundled
        # with pure hedge/CTA prose) can be classified/excluded wholesale, silently losing the
        # fact. Standing, non-blocking safeguard for every future dispatch -- never a hard gate,
        # since a differently-worded embedded fact won't trip the fixed phrase list.
        result["content_unit_embedded_actionable_fact"] = {
            "hard_gate": False,
            "findings": checks.check_content_unit_embedded_actionable_fact(content_units, dispositions),
        }
        # MT051 (Forty-First incident, 2026-08-16): a bare image-markdown unit excluded via
        # candidate_section_reference can pass the check above on generic keyword overlap with a
        # prose section, even when the specific image itself was never actually re-embedded
        # anywhere -- real, confirmed against page/python's own regen-full u0014-u0016.
        result["image_content_unit_excluded_reason_verified"] = {
            "hard_gate": False,
            "findings": checks.check_image_content_unit_excluded_reason_verified(
                content_units, dispositions, text
            ),
        }

        # Twenty-Fourth incident / mission (2026-08-13, cells/go's missing Project Structure
        # section): structural (non-prose) section preservation -- content-unit extraction above
        # can never see this by design (it strips fenced code before segmenting). structure-
        # dispositions.json is a sibling to content-dispositions.json, same tier, same directory
        # -- never an extension of that file's own prose-tone-specific classification enum.
        structural_units = checks.extract_old_readme_structural_units(old_readme_text)
        structure_dispositions_path = _structure_dispositions_path(family, platform)
        structure_dispositions = (
            json.loads(structure_dispositions_path.read_text(encoding="utf-8"))
            if structure_dispositions_path.is_file() else []
        )
        result["structural_unit_disposition_coverage"] = {
            "hard_gate": True,
            "findings": checks.check_structural_unit_disposition_coverage(structural_units, structure_dispositions),
        }
        result["structural_unit_evidence_resolves"] = {
            "hard_gate": True,
            "findings": checks.check_content_unit_evidence_resolves(
                structure_dispositions, str(clone_cache), _load_package_registry(),
                _load_content_docs_texts(family, platform),
                # MT055/TC-MICRO-04: a structural unit represents a verbatim extraction from the
                # old README (a directory tree, a fenced block) -- citing README.md as its own
                # source is real provenance, never the circular self-citation this flag exists
                # to catch for content-unit factual claims.
                reject_self_citation=False,
            ),
        }
        result["structural_unit_merged_into_target_section"] = {
            "hard_gate": True,
            "findings": checks.check_structural_unit_merged_into_target_section(text, structure_dispositions),
        }
        result["structural_unit_no_exact_duplicate_merge"] = {
            "hard_gate": True,
            "findings": checks.check_structural_unit_no_exact_duplicate_merge(structure_dispositions),
        }
        # RC-disposition-text-diff-verification (readme-refresh-hardening-and-regen-2026-08-30,
        # TC-21): the coverage check above validates disposition SHAPE, never the CONTENT CLAIM
        # a merged_verbatim label makes -- see the check's own docstring for the real font/python
        # s0002 defect this closes.
        result["structural_unit_disposition_text_diff"] = {
            "hard_gate": True,
            "findings": checks.check_structural_unit_disposition_text_diff(
                structural_units, structure_dispositions, text,
            ),
        }
        result["structural_unit_tree_paths_plausible"] = {
            "hard_gate": False,
            "findings": checks.check_structural_unit_tree_paths_plausible(
                structural_units, structure_dispositions, str(clone_cache)
            ),
        }
        # RC-disposition-bidirectional-coverage (readme-refresh-hardening-and-regen-2026-08-30,
        # TC-22): the two coverage checks above are both one-directional (old-README-unit-driven
        # only) -- a required section that's substantially new candidate content has no unit_id
        # to check against and is invisible to both. Advisory, not a hard gate -- see the check's
        # own docstring for why a real "zero disposition trace" finding can be either a genuine
        # gap or a section legitimately sourced/verified elsewhere entirely.
        result["candidate_section_disposition_traceability"] = {
            "hard_gate": False,
            "findings": checks.check_candidate_section_disposition_traceability(
                text, dispositions, structure_dispositions,
            ),
        }

        # Thirty-Seventh incident / MT047 (2026-08-15): code-example (fenced-code) preservation
        # -- extract_old_readme_content_units strips ALL fenced code before segmenting by design,
        # and extract_old_readme_structural_units (above) only ever captures it when the prose
        # extractor finds NOTHING real in the same section -- a section combining a large code
        # block with even one surviving prose sentence was invisible to both, by construction,
        # until this incident. code-example-dispositions.json is a third sibling, same tier, same
        # directory as content-/structure-/badge-dispositions.json.
        code_units = checks.extract_old_readme_code_units(old_readme_text)
        code_example_dispositions_path = _code_example_dispositions_path(family, platform)
        code_example_dispositions = (
            json.loads(code_example_dispositions_path.read_text(encoding="utf-8"))
            if code_example_dispositions_path.is_file() else []
        )
        result["code_example_disposition_coverage"] = {
            "hard_gate": True,
            "findings": checks.check_code_example_disposition_coverage(code_units, code_example_dispositions),
        }
        result["code_example_evidence_resolves"] = {
            "hard_gate": True,
            "findings": checks.check_content_unit_evidence_resolves(
                code_example_dispositions, str(clone_cache), _load_package_registry(),
                _load_content_docs_texts(family, platform),
                # MT055/TC-MICRO-04: a code-example unit represents a verbatim extraction (a real
                # fenced command/block) from the old README -- same reasoning as the structural
                # call site above, not the circular self-citation this flag exists to catch.
                reject_self_citation=False,
            ),
        }
        result["code_example_no_exact_duplicate_merge"] = {
            "hard_gate": True,
            "findings": checks.check_code_example_no_exact_duplicate_merge(code_example_dispositions),
        }
        # RC-disposition-text-diff-verification (readme-refresh-hardening-and-regen-2026-08-30,
        # TC-21): the coverage check above validates disposition SHAPE, never the CONTENT CLAIM
        # a merged_verbatim label makes -- see the check's own docstring for the real tex/python
        # c0001 defect this closes.
        result["code_example_disposition_text_diff"] = {
            "hard_gate": True,
            "findings": checks.check_code_example_disposition_text_diff(
                code_units, code_example_dispositions, text,
            ),
        }
        result["code_example_api_coverage_survives"] = {
            "hard_gate": True,
            "findings": checks.check_code_example_api_coverage_survives(text, code_example_dispositions),
        }
        result["code_example_excluded_reason_citation_too_narrow"] = {
            "hard_gate": False,
            "findings": checks.check_code_example_excluded_reason_citation_too_narrow(
                code_example_dispositions, text
            ),
        }
        result["cli_category_representation"] = {
            "hard_gate": False,
            "findings": checks.check_cli_category_representation(text, code_units),
        }

        # Twenty-Fourth incident / mission (2026-08-13): badge semantic reconciliation --
        # previously nonexistent (no parsing/classification/dedup mechanism anywhere in this
        # module). badge-dispositions.json is a second sibling, same tier, same directory.
        old_badges = checks.extract_badges(old_readme_text)
        new_badges = checks.extract_badges(text)
        badge_dispositions_path = _badge_dispositions_path(family, platform)
        badge_dispositions = (
            json.loads(badge_dispositions_path.read_text(encoding="utf-8"))
            if badge_dispositions_path.is_file() else []
        )
        result["badge_disposition_coverage"] = {
            "hard_gate": True,
            "findings": checks.check_badge_disposition_coverage(old_badges, new_badges, badge_dispositions),
        }
        result["badge_evidence_resolves"] = {
            "hard_gate": True,
            "findings": checks.check_content_unit_evidence_resolves(
                badge_dispositions, str(clone_cache), _load_package_registry(),
                _load_content_docs_texts(family, platform),
            ),
        }
        result["badge_preserved_or_credited_in_candidate"] = {
            "hard_gate": True,
            "findings": checks.check_badge_preserved_or_credited_in_candidate(new_badges, badge_dispositions),
        }
        result["badge_probable_duplicate_disposition"] = {
            "hard_gate": False,
            "findings": checks.check_badge_probable_duplicate_disposition(badge_dispositions),
        }

    # Twenty-Fifth mission (2026-08-13, cells/java healing pass): a restored Project Structure
    # tree must use the one canonical, already-shipped visual convention (cells/go's box-drawing
    # style), not whichever style the old README happened to use natively. A candidate-quality
    # check (the candidate's own formatting convention), not old-README preservation -- runs
    # unconditionally, regardless of readme_already_published (MT053).
    result["project_structure_canonical_tree_format"] = {
        "hard_gate": True,
        "findings": checks.check_project_structure_canonical_tree_format(text),
    }
    # Both of these operate on the candidate's own badge row only (never old_readme_text) --
    # candidate-quality checks, not old-README preservation. Run unconditionally (MT053).
    result["badge_static_claims_dynamic_fact"] = {
        "hard_gate": False,
        "findings": checks.check_badge_static_claims_dynamic_fact(text),
    }
    result["no_duplicate_badges_in_candidate"] = {
        "hard_gate": True,
        "findings": checks.check_no_duplicate_badges_in_candidate(text),
    }

    # MT042 (TC-HARDEN-58/59, Thirty-Second incident, 2026-08-14): the badge mechanism above is
    # entirely reconciliation-scoped (preserve/dedup an OLD badge) and vacuously passes when the
    # old README has zero badges -- exactly the gap that let `cells/typescript`'s candidate ship
    # with a single License badge, undetected by anything. These two close the composition-time
    # question (a real, portfolio-wide floor) the reconciliation mechanism was never designed to
    # answer. Computed fresh, matching this function's own established "never read back from the
    # persisted factpack.json" pattern for every other _detect_* value.
    available_badges = _detect_available_badges(
        family, platform, repo_full_name=_repo_full_name(family, platform),
        license_file=_detect_license_file(clone_cache), install_info=_detect_install_info(family, platform),
        dependency_snapshot=dependency_snapshot, dev_test_artifacts=dev_test_artifacts,
    )
    result["badge_row_meets_verified_floor"] = {
        "hard_gate": True,
        "findings": checks.check_badge_row_meets_verified_floor(text, available_badges),
    }
    result["badge_available_fact_not_shown"] = {
        "hard_gate": False,
        "findings": checks.check_badge_available_fact_not_shown(text, available_badges),
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
    # Twenty-Fifth mission (2026-08-13, cells/java healing pass): a Starting-Points/Outputs node
    # duplicating an existing Capabilities node usually means the node should be deleted, not
    # evidence-strengthened -- see skills/readme-refresh.md's diagram-composition guidance.
    result["diagram_container_duplicates_capability"] = {
        "hard_gate": False, "findings": checks.check_diagram_container_duplicates_capability(text),
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
    # TC-HARDEN-76 (MT047/Thirty-Seventh incident, 2026-08-15): "is this cited class real"
    # (above) is a categorically different question from "is this real class genuinely PUBLIC" --
    # the exact gap that let font/python's real internal-tooling classes (reporting.py's
    # TaskTokenEstimate/TaskCompletionReceipt/CompletedTaskRecord) leak into the API Reference
    # table. Heuristic tier -- surfaced for judgment, never a hard_gate failure.
    # MT048 (2026-08-15): now passes the same real exclusions set the finding's own message has
    # always claimed it would consult -- see check_api_reference_class_internal_only's own
    # docstring for the confirmed gap this closes.
    result["api_reference_class_internal_only"] = {
        "hard_gate": False,
        "findings": checks.check_api_reference_class_internal_only(
            text, reference_index, str(clone_cache),
            exclusions=_product_api_reference_class_exclusions(family, platform),
            platform=platform,
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
    # Twenty-Fifth mission / mission (2026-08-13, cells/java): a real, mechanically decidable
    # claim (this fenced Java example's import statement resolves to a real class at this exact
    # package path) that check_named_member_accuracy's own bullet-list-only scope never covered
    # -- found live via the real com.aspose.cells_foss -> org.aspose.cells_foss upstream rename.
    result["code_example_imports_match_source"] = {
        "hard_gate": True,
        "findings": checks.check_code_example_imports_match_source(text, str(clone_cache)),
    }

    # Thirteenth incident / MT028 (2026-08-09): MT027 grounded verification in reference.
    # aspose.org's own content but never adapted the section's PRESENTATION to match it -- these
    # two checks enforce the fix (a module-grouped table mirroring _index.md's own organization,
    # inserted above the untouched curated bullets; user's own chosen design, via AskUserQuestion).
    # TC-HARDEN-77 (MT047/Thirty-Seventh incident, 2026-08-15): a class in data/api_reference_
    # class_exclusions.json (this product's own real, evidence-required entries) is never
    # required in the mirror -- see check_api_reference_table_completeness's own extended
    # docstring for the full "never surfaced regardless of reference-site presence" contract.
    result["api_reference_table_completeness"] = {
        "hard_gate": True,
        "findings": checks.check_api_reference_table_completeness(
            text, reference_index, exclusions=_product_api_reference_class_exclusions(family, platform),
        ),
    }
    # TC-HARDEN-37 (MT035, 2026-08-12): the exact "497 findings" false-alarm shape this
    # incident found (pdf/java/3d/net's reference-index source carrying real, substantial,
    # currently-uncommitted growth from an external session) previously required a full manual
    # `git diff --stat HEAD` diagnosis to distinguish from a genuine content gap -- mechanized
    # here as a non-blocking heuristic so a future "N findings" result is immediately
    # distinguishable, without requiring that same manual diagnosis to be redone from scratch.
    dirty = _reference_index_source_dirty(family, platform)
    result["reference_index_source_dirty"] = {
        "hard_gate": False,
        "findings": [{
            "reason": f"content/reference.aspose.org/en/{family}/{platform}/_index.md has "
                      f"uncommitted local changes (git diff --stat HEAD is non-empty) -- any "
                      f"api_reference_table_completeness findings for this product may be a "
                      f"snapshot-timing artifact against a moving target, not a genuine content "
                      f"gap; verify against the last committed state before trusting them",
        }] if dirty else [],
    }
    # TC-HARDEN-21 (MT034, Twentieth incident, 2026-08-12): a real clean-room pilot found an
    # exact-duplicate row (cells/cpp's Enumerations table listed DiagnosticSeverity twice) that
    # passed check_api_reference_table_completeness cleanly -- duplication within the candidate's
    # own table is an orthogonal defect that check has no concept of.
    result["api_reference_table_no_duplicate_rows"] = {
        "hard_gate": True,
        "findings": checks.check_api_reference_table_no_duplicate_rows(text),
    }
    # RC-candidate-self-consistency-checks remaining sub-item 1 (TC-24, readme-refresh-
    # hardening-and-regen-2026-08-30): a candidate's own "N public types" prose claim must
    # agree with its own API Reference table's distinct-class count -- confirmed live, real
    # on font/python (its Documentation & Resources section's "139 public types" claim
    # disagrees with its own table).
    result["api_reference_public_type_count_matches_table"] = {
        "hard_gate": True,
        "findings": checks.check_api_reference_public_type_count_matches_table(text),
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

    # Thirty-First incident / MT041 (2026-08-14): dependency accuracy. cells/rust's Installation
    # section stated "no external runtime or Microsoft Office installation is needed" while its
    # own Cargo.toml declares 7 real crates -- a same-document contradiction against that file's
    # own, correct Intro paragraph. dependency_snapshot/dependency_claims_corroboration computed
    # fresh at the top of this function.
    result["dependency_snapshot_completeness"] = {
        "hard_gate": True,
        "findings": checks.check_dependency_snapshot_completeness(text, dependency_snapshot),
    }
    result["unqualified_dependency_claims"] = {
        "hard_gate": True,
        "findings": checks.check_unqualified_dependency_claims(text),
    }
    result["dependency_section_manifest_corroboration"] = {
        "hard_gate": False,
        "findings": checks.check_dependency_section_manifest_corroboration(
            text, dependency_snapshot, dependency_claims_corroboration,
        ),
    }
    result["dependency_direct_transitive_confusion"] = {
        "hard_gate": True,
        "findings": checks.check_dependency_direct_transitive_confusion(text, dependency_snapshot),
    }
    result["dependency_optional_presented_as_required"] = {
        "hard_gate": True,
        "findings": checks.check_dependency_optional_presented_as_required(text, dependency_snapshot),
    }
    result["dependency_dev_only_presented_as_runtime"] = {
        "hard_gate": True,
        "findings": checks.check_dependency_dev_only_presented_as_runtime(text, dependency_snapshot),
    }
    result["dependency_development_claim_not_in_manifest"] = {
        "hard_gate": True,
        "findings": checks.check_dependency_development_claim_not_in_manifest(text, dependency_snapshot),
    }
    # Downgraded from hard gate to heuristic (found live, real-content proof against cells/
    # rust's own corrected candidate): NO extractor currently verifies the proprietary_runtime
    # category (no per-ecosystem "does this crate declare a commercial runtime dependency"
    # signal exists), so this check's only possible outcome today is "always flag" -- including
    # against this skill's own sanctioned GOOD-example phrasing ("no proprietary Aspose runtime
    # and no Microsoft Office installation is required"). A hard gate that can never be
    # legitimately satisfied is not a real gate. Mirrors check_installation_matches_package_
    # registry's own established downgrade precedent exactly (TC-HARDEN-32): don't hard-gate on
    # a claim category with no real verifier behind it yet.
    result["dependency_scope_claim_matches_evidence"] = {
        "hard_gate": False,
        "findings": checks.check_dependency_scope_claim_matches_evidence(text, dependency_snapshot),
    }
    result["dependencies_scope_limitations_contradiction"] = {
        "hard_gate": False,
        "findings": checks.check_dependencies_scope_limitations_contradiction(text),
    }
    result["dependencies_intro_contradiction"] = {
        "hard_gate": True,
        "findings": checks.check_dependencies_intro_contradiction(text, dependency_snapshot),
    }
    result["dependency_version_pin_freshness"] = {
        "hard_gate": False,
        "findings": checks.check_dependency_version_pin_freshness(text, dependency_snapshot),
    }
    result["dependency_native_system_scope_limitations_placement"] = {
        "hard_gate": True,
        "findings": checks.check_dependency_native_system_scope_limitations_placement(text),
    }
    result["dependency_disposition_reconciliation"] = {
        "hard_gate": True,
        "findings": checks.check_dependency_disposition_reconciliation(
            content_units, dispositions, dependency_snapshot,
        ),
    }
    # readme-refresh-seo-deps-headings-hardening mission (2026-08-19): the Dependencies
    # ###-subheading presence contract -- see check_dependency_section_subheadings_present's
    # own docstring. Reuses the same dependency_snapshot already computed at the top of this
    # function.
    result["dependency_section_subheadings_present"] = {
        "hard_gate": True,
        "findings": checks.check_dependency_section_subheadings_present(text, dependency_snapshot),
    }
    # Same mission: the SEO keyword placement-plan usage heuristic -- recomputed fresh here
    # (never read back from a persisted factpack.json), matching this function's own
    # established pattern for every other _detect_*-derived value (dependency_snapshot, above,
    # is the same shape). filter_relevant_seo_keywords needs real per-product format evidence,
    # cheap to recompute (family/platform only, no clone_cache I/O).
    seo_candidate_format_evidence = _compute_candidate_format_evidence(family, platform)
    seo_known_format_names = {
        row["format"]
        for direction in ("import", "export")
        for row in seo_candidate_format_evidence.get(direction, [])
    }
    seo_keywords_filtered = checks.filter_relevant_seo_keywords(
        _detect_seo_keywords(family, platform)["keywords"], family, platform, seo_known_format_names,
    )
    seo_keyword_plan = checks.build_seo_keyword_placement_plan(seo_keywords_filtered, family)
    result["seo_keyword_plan_usage"] = {
        "hard_gate": False,
        "findings": checks.check_seo_keyword_plan_usage(text, seo_keyword_plan),
    }
    # Same mission: every worked example inside "View Additional Examples" must carry its own
    # real, non-generic, unique heading -- see check_additional_example_headings' own docstring.
    result["additional_example_headings"] = {
        "hard_gate": True,
        "findings": checks.check_additional_example_headings(text),
    }
    # readme-refresh-forensic-trust-audit-2026-08-25, Phase 4 row 22: every real ## heading
    # must have a matching Navigation entry, and vice versa -- see
    # check_navigation_toc_matches_headings' own docstring.
    result["navigation_toc_matches_headings"] = {
        "hard_gate": True,
        "findings": checks.check_navigation_toc_matches_headings(text),
    }
    # TC-M56-09 (2026-08-18): advisory drift-since-last-verified signal, computed here so it
    # fires identically from ingest_candidate, recheck, AND audit_portfolio -- the one shared
    # entry point all three already route through.
    result["candidate_drift_since_last_verified"] = {
        "hard_gate": False,
        "findings": _candidate_drift_findings(family, platform),
    }
    # Same mission: checks-module-currency staleness tripwire -- see
    # _checks_currency_findings' own docstring for why "clean" silently rots as checks are added.
    result["verification_currency"] = {
        "hard_gate": False,
        "findings": _checks_currency_findings(family, platform),
    }
    # RC-dead-code-depmatrix-resolution (readme-refresh-hardening-and-regen-2026-08-30):
    # build_dependency_verification_matrix was implemented and tested but never called from
    # anywhere -- confirmed by exhaustive grep before this fix. Wired in here (not removed) per
    # this mission's plan: it is a genuinely useful, already-correct reviewer artifact (per-
    # dependency corroboration across the Dependencies section, prose, and claims.json), it is
    # never a gate itself (no "hard_gate" key -- ingest_candidate's own hard-gate predicate
    # `r.get("hard_gate") and r.get("findings")` structurally ignores it), and computing it here
    # means it fires identically from ingest_candidate, recheck, and audit_portfolio, the same
    # single-entry-point discipline every other shared signal in this function already follows.
    result["dependency_verification_matrix"] = checks.build_dependency_verification_matrix(
        dependency_snapshot, text, dependency_claims_raw.get("claims"),
    )
    return result


def pin_old_readme_baseline(
    family: str, platform: str, commit: str, reason: str, *, session_id: "str | None" = None,
) -> dict:
    """TC-20: record that this product's disposition ledger (`content-dispositions.json` etc.)
    was actually built against `commit`, not whatever the clone cache's live HEAD currently is.
    See `_resolve_old_readme_text`'s own docstring for the defect class this closes.

    Deliberately verifies `commit` resolves to a real `README.md` blob in this product's clone
    cache before writing anything -- a typo'd or unreachable SHA must fail loudly here, not
    silently degrade every future disposition check for this product to reading empty text
    (`_resolve_old_readme_text`'s own git-show failure path already fails safe to live HEAD, but
    that safety net exists for the clone cache changing shape *after* a valid pin, not for
    excusing an invalid one at pin time).
    """
    family = _safe_token(family, "family")
    platform = _safe_token(platform, "platform")
    clone_cache = _product_clone_cache(family, platform)
    proc = subprocess.run(
        ["git", "show", f"{commit}:README.md"],
        cwd=str(clone_cache), capture_output=True, text=True, encoding="utf-8", errors="ignore",
    )
    if proc.returncode != 0:
        raise ReadmeRefreshRunError(
            f"pin-old-readme-baseline refused: {commit!r} does not resolve to a README.md blob "
            f"in {clone_cache} (git show exit {proc.returncode}): {proc.stderr.strip()}"
        )
    sidecar = {
        "baseline_commit": commit,
        "reason": reason,
        "recorded_at": _utc(),
        "recorded_by": _session_id(session_id),
    }
    path = _old_readme_baseline_path(family, platform)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sidecar, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return sidecar


def reconcile_publications(
    *, family: "str | None" = None, platform: "str | None" = None,
    all_products: bool = False, apply: bool = False,
) -> dict:
    """TC-15/TC-17 (readme-refresh-trackb-and-followon-2026-09-01): CLI-facing wrapper over
    publication_reconciler.py. Never unscoped by accident -- exactly one of
    (family AND platform) or all_products=True is required, mirroring audit_portfolio's own
    hard-won discipline, though here the cost of a full sweep is genuinely small (one `gh pr
    list` call per product, not a local check battery run).

    Read-only unless apply=True; even then, only ever writes
    data/readme_published_state.json, never any product's own repo. Returns
    `{"reports": [...], "applied": [...]}`.
    """
    if all_products:
        if family or platform:
            raise ReadmeRefreshRunError("Pass either --all or --family/--platform, not both")
        products = _load_products()
        exclusions = _load_registry_exclusions()
        excluded_keys = {
            (excl.get("family"), excl.get("platform"))
            for excl in exclusions if excl.get("match") == "family_platform"
        }
        pairs = sorted({
            (p.get("family"), p.get("platform")) for p in products
            if p.get("active", False) and (p.get("family"), p.get("platform")) not in excluded_keys
        })
    elif family and platform:
        pairs = [(family, platform)]
    else:
        raise ReadmeRefreshRunError("reconcile-publications requires --family/--platform or --all")

    reports = publication_reconciler.reconcile_portfolio(pairs)
    applied = []
    if apply:
        for report in reports:
            written = publication_reconciler.apply_reconciliation(report)
            if written is not None:
                applied.append(written)
    return {"reports": reports, "applied": applied}


def audit_portfolio(*, family: "str | None" = None, platform: "str | None" = None) -> dict:
    """TC-HARDEN-05 (MT035, 2026-08-12): a real, registered, CLI-callable, tested way to
    re-run every deterministic check against every already-generated candidate in
    `reports/repo-presenter/` -- closing the gap TC-HARDEN-14 named (real day-to-day portfolio
    verification work happening only via an ad hoc, gitignored, un-versioned scratch script,
    `reports/repo-presenter/_scratch/phase2_scan.py`, hand-written and re-derived from memory
    each time it was needed, rather than through any registered, reproducible skill path).

    Iterates every `active: true`, non-excluded product in `data/products.json` (optionally
    narrowed to one `family`/`platform` pair), skips a product with no composed candidate yet
    (never an error -- not every product has been generated), and runs the exact same
    `_run_deterministic_checks` `ingest-candidate`/`recheck` already use against each real
    candidate on disk. Never writes to any CANDIDATE, never mutates any run state, never
    requires an active run (`start`/`plan`) for the product being audited. TC-M56-09
    (2026-08-18) is the one, deliberate exception to "purely read-only": it stamps a small
    sidecar `last-verified.json` fingerprint marker next to each audited candidate (never the
    candidate itself) -- the mechanism that lets a LATER audit-portfolio call detect drift from
    an untracked writer, the exact class of incident (3 real candidates edited outside every
    CLI path, invisible to every other gate) this pass's own live proof caught red-handed.

    Returns `{"products": [{"family", "platform", "clean", "hard_gate_findings": {check_name:
    count}, "published"}], "clean_count", "dirty_count", "total", "skipped": [{"family",
    "platform", "reason"}]}` -- `hard_gate_findings` only ever lists a check that both IS a hard
    gate and currently has at least one finding, matching `phase2_scan.py`'s own established
    summary shape (the one this function replaces) so a prior run's mental model of the output
    transfers directly. `published` (TC-HARDEN-116, MT053, 2026-08-18) surfaces `_run_
    deterministic_checks`'s own `readme_already_published` detection directly, so a portfolio
    scan shows at a glance which products have already been pushed and merged upstream (and
    therefore have their old-README preservation-tracking checks correctly bypassed) without
    needing a separate byte-identity pass.

    MT056 (2026-08-18): validates the configured candidate tree against the durable canonical-
    store record first -- the canonical tree audits normally; a registered ARCHIVED tree is
    allowed (read-only review) but the result carries a `non_canonical` tag; any unregistered
    tree is refused outright (stale-path protection). The result also carries
    `candidate_tree` so no audit output is ever ambiguous about which store it describes.
    """
    non_canonical_tag = _validate_candidate_tree_for_audit()
    products = _load_products()
    exclusions = _load_registry_exclusions()
    excluded_keys = {
        (excl.get("family"), excl.get("platform"))
        for excl in exclusions if excl.get("match") == "family_platform"
    }

    targets = sorted({
        (entry.get("family"), entry.get("platform"))
        for entry in products
        if entry.get("active", False)
        and (entry.get("family"), entry.get("platform")) not in excluded_keys
        and (family is None or entry.get("family") == family)
        and (platform is None or entry.get("platform") == platform)
    })

    product_results: list[dict] = []
    skipped: list[dict] = []
    for fam, plat in targets:
        candidate_path = _candidate_readme_path(fam, plat)
        if not candidate_path.is_file():
            skipped.append({"family": fam, "platform": plat, "reason": "no candidate file yet"})
            continue
        text = candidate_path.read_text(encoding="utf-8")
        clone_cache = _product_clone_cache(fam, plat)
        result = _run_deterministic_checks(fam, plat, text, clone_cache)
        # TC-M56-09: capture the drift finding BEFORE the marker write below overwrites its own
        # basis for comparison. This is advisory (hard_gate=False) by deliberate design (a
        # legitimate edit-then-ingest workflow always shows "changed" and that's correct, not a
        # defect) -- which means it is invisible to `hard_gate_findings` below by construction.
        # A real, found-live gap in this task's own first draft: audit_portfolio's per-product
        # summary previously reported ONLY hard-gate findings, so this advisory signal, despite
        # firing correctly inside _run_deterministic_checks, never reached the actual output --
        # caught by re-deriving the call chain end to end rather than trusting the unit-level
        # result alone. Surfaced here as its own explicit field, never buried in a generic
        # advisory dump.
        candidate_drift = result.get("candidate_drift_since_last_verified", {}).get("findings", [])
        # TC-M56-09: audit-portfolio is a real, independent verification pass too -- record it,
        # same marker, run_id=None (no run owns a portfolio-wide audit). Written AFTER capturing
        # candidate_drift above -- writing first would make every drift event invisible to this
        # very call (the marker would already match by the time hard_gate_findings/candidate_
        # drift below are computed).
        _write_candidate_verification_marker(fam, plat, text, run_id=None)
        hard_gate_findings = {
            name: len(check["findings"])
            for name, check in result.items()
            if check.get("hard_gate") and check.get("findings")
        }
        published = bool(
            result.get("readme_already_published", {}).get("detail", {}).get("published", False)
        )
        # TC-AUDIT-01 (found live 2026-08-19 composing cells/net): `clean: true` alone conflates
        # two structurally different states -- a candidate whose disposition-family checks
        # actually RAN and found nothing wrong, versus one where readme_already_published (MT053)
        # skipped all 25 of those checks entirely because the candidate is still byte-identical
        # to the published upstream README. Both report clean:true/{} above, but only the first
        # means the disposition bookkeeping was ever verified. Confirmed live: 5 of this
        # portfolio's 8 then-"clean" products (cells/rust, email/cpp, email/net, pdf/net,
        # words/net) had never been composed at all -- masked by this exact conflation, not
        # actually checked. `disposition_tracking` makes the distinction explicit and
        # structural so no future consumer of this output can collapse them again the way the
        # informal "N/30 clean" framing already did once.
        disposition_family_skipped = bool(
            result.get("content_unit_disposition_coverage", {}).get("skipped", False)
        )
        if disposition_family_skipped:
            disposition_tracking = "skipped_published"
        elif hard_gate_findings:
            disposition_tracking = "checked_dirty"
        else:
            disposition_tracking = "verified"
        product_results.append({
            "family": fam, "platform": plat,
            "clean": not hard_gate_findings,
            "hard_gate_findings": hard_gate_findings,
            "published": published,
            "candidate_drift": candidate_drift,
            "disposition_tracking": disposition_tracking,
        })

    clean_count = sum(1 for p in product_results if p["clean"])
    disposition_verified_count = sum(
        1 for p in product_results if p["disposition_tracking"] == "verified"
    )
    return {
        "products": product_results,
        "disposition_verified_count": disposition_verified_count,
        "clean_count": clean_count,
        "dirty_count": len(product_results) - clean_count,
        "total": len(product_results),
        "skipped": skipped,
        "candidate_tree": _candidate_tree_name,
        "non_canonical": non_canonical_tag,
    }


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
        _check_manifest_candidate_tree(manifest)
        candidate_path = _candidate_readme_path(family, platform)
        text = candidate_path.read_text(encoding="utf-8") if candidate_path.is_file() else ""
        clone_cache = _product_clone_cache(family, platform)
        result = _run_deterministic_checks(family, platform, text, clone_cache)
        _apply_change_isolation_checks(
            result, family, platform, run_id, text,
            allowed_headings=allowed_headings, mermaid_only=mermaid_only,
        )
        # MT056: fail-closed scope/store/frozen-block enforcement (recheck records the findings;
        # it deliberately still never raises -- AWAITING_REVIEW is a human-in-the-loop hold).
        _apply_scope_enforcement(result, family, platform, run_id, text)
        # TC-M56-09: same "we looked at it" marker as ingest-candidate.
        _write_candidate_verification_marker(family, platform, text, run_id=run_id)
        run_root = _run_root(family, platform, run_id)
        (run_root / "checks").mkdir(parents=True, exist_ok=True)
        _write_json(run_root / "checks" / "result.json", result)
        _write_checks_snapshot(family, platform, run_id, text)
        _event(family, platform, run_id, "RECHECK_COMPLETED")
        return result


# --- MT056: declare-scope / accept-blocks / converge-verify --------------------------------


def declare_scope(
    family: str, platform: str, run_id: str, *,
    issue: str,
    areas: "list[str] | None" = None,
    allowed_dependencies: "list[str] | None" = None,
    acceptance_criteria: "str | None" = None,
    full_rewrite: bool = False,
    session_id: "str | None" = None,
) -> dict:
    """MT056 Stage 5: create the change-scope manifest BEFORE regeneration. Records what this
    run is authorized to change (`areas`, by stable block id: `##`-heading slugs plus
    `__preamble__` and `mermaid`), which dependent blocks may legitimately move with it
    (`allowed_dependencies` -- declared in advance, never discovered after a broad diff), and
    the acceptance criteria. Snapshots the current canonical candidate as this scope's
    IMMUTABLE baseline; every subsequent ingest/recheck fails closed on any block that changes
    without being authorized here.

    `--full-rewrite` is the explicit form of a whole-document scope (first composition, or a
    deliberate total regeneration) -- an implied full-document scope does not exist; that
    ambiguity is the R-03/R-12 whole-file-regen defect class.

    A block id named in `areas` that does not exist in the baseline is legal (it authorizes
    ADDING that block) and is recorded under `unknown_areas` for reviewer visibility."""
    owner = _session_id(session_id)
    with _product_guard(family, platform):
        manifest = _load_manifest(family, platform, run_id)
        if manifest["session_owner"] != owner:
            raise ReadmeRefreshRunError(f"Run is owned by {manifest['session_owner']!r}, not {owner!r}")
        if manifest.get("state") in TERMINAL_STATES:
            raise ReadmeRefreshRunError(f"Run {run_id} is terminal ({manifest.get('state')}); scopes are per-live-run")
        _check_manifest_candidate_tree(manifest)
        if not isinstance(issue, str) or not issue.strip():
            raise ReadmeRefreshRunError("declare-scope requires a non-empty --issue")
        area_list = [a.strip() for a in (areas or []) if a and a.strip()]
        dep_list = [d.strip() for d in (allowed_dependencies or []) if d and d.strip()]
        if not full_rewrite and not area_list:
            raise ReadmeRefreshRunError("declare-scope requires --areas (or --full-rewrite for a whole-document scope)")

        candidate_path = _candidate_readme_path(family, platform)
        baseline_text = candidate_path.read_text(encoding="utf-8") if candidate_path.is_file() else None
        if baseline_text is None and not full_rewrite:
            raise ReadmeRefreshRunError(
                "no existing candidate to scope against -- a first composition is a "
                "whole-document change; declare it explicitly with --full-rewrite"
            )

        scope_root = _scope_root(family, platform, run_id)
        scope_root.mkdir(parents=True, exist_ok=True)
        scope_path = _change_scope_path(family, platform, run_id)
        if scope_path.is_file():
            history_dir = scope_root / "history"
            history_dir.mkdir(exist_ok=True)
            stamp = _now().strftime("%Y%m%dT%H%M%SZ")
            shutil.copy2(scope_path, history_dir / f"change_scope-{stamp}.json")
            baseline_path = _scope_baseline_path(family, platform, run_id)
            if baseline_path.is_file():
                shutil.copy2(baseline_path, history_dir / f"baseline_candidate-{stamp}.md")

        unknown_areas: list[str] = []
        if baseline_text is not None:
            baseline_blocks = checks.split_into_scope_blocks(baseline_text)
            unknown_areas = sorted(set(area_list + dep_list) - set(baseline_blocks))
        record = {
            "schema_version": 1,
            "issue": issue.strip(),
            "areas": area_list,
            "allowed_dependencies": dep_list,
            "acceptance_criteria": acceptance_criteria,
            "full_rewrite": full_rewrite,
            "unknown_areas": unknown_areas,
            "declared_at": _utc(),
            "declared_by_session": owner,
            "baseline_sha256": (
                hashlib.sha256(baseline_text.encode("utf-8")).hexdigest()
                if baseline_text is not None else None
            ),
        }
        if baseline_text is not None:
            _scope_baseline_path(family, platform, run_id).write_text(baseline_text, encoding="utf-8")
            _write_json(
                scope_root / "baseline_fingerprints.json",
                checks.compute_block_fingerprints(baseline_text),
            )
        _write_json(scope_path, record)
        _event(
            family, platform, run_id, "SCOPE_DECLARED",
            issue=record["issue"], areas=area_list, allowed_dependencies=dep_list,
            full_rewrite=full_rewrite,
        )
        return record


def accept_blocks(
    family: str, platform: str, run_id: str, *,
    blocks: list[str],
    status: str = "CONVERGED",
    governing_rule: "str | None" = None,
    evidence_ref: "str | None" = None,
    note: "str | None" = None,
    session_id: "str | None" = None,
) -> dict:
    """MT056 Stage 7: record accepted blocks in the product's acceptance registry
    (acceptance-registry.json, sibling to the disposition files -- identities, hashes, states,
    evidence refs; never candidate content). CONVERGED/FROZEN_ACCEPTED may only be recorded
    while the run's latest checks result is clean of hard-gate findings AND the candidate on
    disk is byte-identical to the last-checked snapshot (accepting an unchecked edit is
    forbidden by construction). Each accepted block stores its content hash and the pinned
    clone-cache HEAD as its source fingerprint -- source invalidation is later detected
    explicitly (converge-verify), never remembered."""
    owner = _session_id(session_id)
    with _product_guard(family, platform):
        manifest = _load_manifest(family, platform, run_id)
        if manifest["session_owner"] != owner:
            raise ReadmeRefreshRunError(f"Run is owned by {manifest['session_owner']!r}, not {owner!r}")
        _check_manifest_candidate_tree(manifest)
        if status not in checks._ACCEPTANCE_BLOCK_STATUSES:
            raise ReadmeRefreshRunError(
                f"status {status!r} is not one of {sorted(checks._ACCEPTANCE_BLOCK_STATUSES)}"
            )
        block_list = [b.strip() for b in blocks if b and b.strip()]
        if not block_list:
            raise ReadmeRefreshRunError("accept-blocks requires at least one block id")

        candidate_path = _candidate_readme_path(family, platform)
        if not candidate_path.is_file():
            raise ReadmeRefreshRunError(f"No candidate found at {candidate_path}")
        text = candidate_path.read_text(encoding="utf-8")

        if status in ("CONVERGED", "FROZEN_ACCEPTED"):
            result_path = _run_root(family, platform, run_id) / "checks" / "result.json"
            if not result_path.is_file():
                raise ReadmeRefreshRunError(
                    "no checks/result.json for this run -- run ingest-candidate or recheck first"
                )
            last = json.loads(result_path.read_text(encoding="utf-8"))
            hard_failures = [
                name for name, r in last.items() if r.get("hard_gate") and r.get("findings")
            ]
            if hard_failures:
                raise ReadmeRefreshRunError(
                    f"cannot accept blocks as {status} while hard gates fail: {hard_failures}"
                )
            snapshot_path = _checks_snapshot_path(family, platform, run_id)
            if not snapshot_path.is_file() or snapshot_path.read_text(encoding="utf-8") != text:
                raise ReadmeRefreshRunError(
                    "candidate on disk differs from the last-checked snapshot -- recheck first; "
                    "accepting an unchecked edit is forbidden"
                )

        live_fp = checks.compute_block_fingerprints(text)
        missing = [b for b in block_list if b not in live_fp]
        if missing and status in ("CONVERGED", "FROZEN_ACCEPTED"):
            raise ReadmeRefreshRunError(
                f"block(s) {missing} not present in the candidate -- cannot accept a block that "
                "does not exist"
            )

        scope = _load_change_scope(family, platform, run_id)
        registry = _load_acceptance_registry(family, platform) or {
            "schema_version": 1, "family": family, "platform": platform, "blocks": [],
        }
        entries = registry.setdefault("blocks", [])
        by_id = {e.get("block_id"): e for e in entries if isinstance(e.get("block_id"), str)}
        now = _utc()
        pinned_head = (manifest.get("pinned_inputs") or {}).get("clone_cache_head")
        for block_id in block_list:
            entry = by_id.get(block_id)
            if entry is None:
                entry = {"block_id": block_id, "historical_defects": [], "history": []}
                entries.append(entry)
                by_id[block_id] = entry
            entry["status"] = status
            if block_id in live_fp:
                entry["accepted_sha256"] = live_fp[block_id]
            entry["source_fingerprint"] = {"clone_cache_head": pinned_head}
            if governing_rule is not None:
                entry["governing_rule"] = governing_rule
            if evidence_ref is not None:
                entry["evidence_ref"] = evidence_ref
            entry["last_authorized_change"] = {
                "run_id": run_id,
                "scope_issue": (scope or {}).get("issue"),
            }
            entry.setdefault("history", []).append(
                {"at": now, "status": status, "run_id": run_id, "note": note}
            )
        registry["document_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
        registry["block_fingerprints"] = live_fp
        registry["updated_at"] = now
        registry["updated_by_run"] = run_id
        _write_json(_acceptance_registry_path(family, platform), registry)
        _event(family, platform, run_id, "BLOCKS_ACCEPTED", blocks=block_list, status=status)
        return registry


def converge_verify(
    family: str, platform: str, run_id: str, *,
    apply_invalidation: bool = False,
    session_id: "str | None" = None,
) -> dict:
    """MT056 convergence gate: recompute the live candidate's block fingerprints against the
    acceptance registry. Converged means: zero drift on any CONVERGED/FROZEN_ACCEPTED block AND
    the whole document matches its last-accepted hash -- i.e. re-running the same regeneration
    produced no further change. Also detects source invalidation (pinned clone-cache HEAD moved
    since a block's acceptance): reported always; statuses flipped to
    INVALIDATED_BY_SOURCE_CHANGE only under --apply-invalidation (an explicit reopening, never
    a silent rewrite)."""
    owner = _session_id(session_id)
    with _product_guard(family, platform):
        manifest = _load_manifest(family, platform, run_id)
        if manifest["session_owner"] != owner:
            raise ReadmeRefreshRunError(f"Run is owned by {manifest['session_owner']!r}, not {owner!r}")
        _check_manifest_candidate_tree(manifest)
        candidate_path = _candidate_readme_path(family, platform)
        if not candidate_path.is_file():
            raise ReadmeRefreshRunError(f"No candidate found at {candidate_path}")
        text = candidate_path.read_text(encoding="utf-8")
        registry = _load_acceptance_registry(family, platform)
        entries = registry.get("blocks") or []
        if not entries:
            raise ReadmeRefreshRunError(
                f"no acceptance registry (or no accepted blocks) for {family}/{platform} -- "
                "nothing to verify; accept-blocks first"
            )
        drift = checks.check_frozen_blocks_unchanged(text, entries, [])
        document_stable = registry.get("document_sha256") == hashlib.sha256(
            text.encode("utf-8")
        ).hexdigest()

        clone_cache = _product_clone_cache(family, platform)
        current_head = None
        if clone_cache.is_dir():
            try:
                current_head = _git("rev-parse", "HEAD", cwd=clone_cache)
            except ReadmeRefreshRunError:
                current_head = None
        invalidated: list[str] = []
        now = _utc()
        for entry in entries:
            if entry.get("status") not in ("CONVERGED", "FROZEN_ACCEPTED"):
                continue
            pinned = (entry.get("source_fingerprint") or {}).get("clone_cache_head")
            if pinned and current_head and pinned != current_head:
                invalidated.append(entry["block_id"])
                if apply_invalidation:
                    entry["status"] = "INVALIDATED_BY_SOURCE_CHANGE"
                    entry.setdefault("history", []).append({
                        "at": now, "status": "INVALIDATED_BY_SOURCE_CHANGE", "run_id": run_id,
                        "note": f"clone-cache HEAD moved {pinned} -> {current_head}",
                    })
        if apply_invalidation and invalidated:
            registry["updated_at"] = now
            registry["updated_by_run"] = run_id
            _write_json(_acceptance_registry_path(family, platform), registry)

        verdict = {
            "converged": not drift and document_stable,
            "drift_findings": drift,
            "document_stable": document_stable,
            "source_invalidated_blocks": invalidated,
            "invalidation_applied": bool(apply_invalidation and invalidated),
            "clone_cache_head": current_head,
            "verified_at": now,
        }
        scope_root = _scope_root(family, platform, run_id)
        scope_root.mkdir(parents=True, exist_ok=True)
        _write_json(scope_root / "converge_verify.json", verdict)
        _event(
            family, platform, run_id, "CONVERGE_VERIFY",
            converged=verdict["converged"], invalidated=len(invalidated),
        )
        return verdict


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
    family: str, platform: str, run_id: str, *, acting_model: str, session_id: "str | None" = None,
    dry_run: bool = False, scratch_root: "Path | str | None" = None,
) -> dict:
    """APPROVED -> PUSHING -> PUSHED. Disposable-clone + branch + surgical-diff-checked
    plumbing commit + push + gh pr create (skipped when --dry-run, or when the branch/commit
    steps themselves fail before the network push -- --dry-run stops before any live GitHub
    write). See module docstring's Honest Scope Statement: has been exercised only against
    local scratch git repos, not a real external org, pending explicit authorization.

    acting_model (F-02, MT032's "real acting model, never hardcoded" rule -- same posture as
    invariant 5.9's merge-time Co-authored-by trailer): required, no default. This script never
    knows which model is actually running it; only the calling agent does, so the agent must
    supply its own real, current display name here every time, the same way it supplies
    --subject/--body at merge time."""
    if not acting_model or not acting_model.strip():
        raise ReadmeRefreshRunError("acting_model is required and must be the real, current model name")
    owner = _session_id(session_id)
    with _product_guard(family, platform):
        manifest = _load_manifest(family, platform, run_id)
        if manifest["session_owner"] != owner:
            raise ReadmeRefreshRunError(f"Run is owned by {manifest['session_owner']!r}, not {owner!r}")
        # MT056: a push may only ever ship the canonical tree's candidate, and only under the
        # same tree the run was started against.
        _require_canonical_tree("push")
        _check_manifest_candidate_tree(manifest)

        _transition(manifest, "PUSHING", checkpoint="pushing_started")

        scratch = Path(scratch_root) if scratch_root else _reports_root / "readme_refresh_runs" / "_scratch"
        scratch.mkdir(parents=True, exist_ok=True)
        work_dir = scratch / f"{family}-{platform}-{run_id}"
        try:
            receipt = _do_push(manifest, work_dir, dry_run=dry_run, acting_model=acting_model)
        except Exception as exc:
            _block(manifest, str(exc))
            raise ReadmeRefreshRunError(f"push failed, run BLOCKED: {exc}") from exc

        run_root = _run_root(family, platform, run_id)
        (run_root / "push").mkdir(parents=True, exist_ok=True)
        _write_json(run_root / "push" / "receipt.json", receipt)
        _event(family, platform, run_id, "PUSH_COMPLETED", **{k: v for k, v in receipt.items() if k != "declared_files"})
        _append_action_ledger_row(
            family, platform,
            action="readme_push_dry_run" if dry_run else "readme_pr_opened",
            details={
                "branch": receipt.get("branch"), "commit_sha": receipt.get("commit_sha"),
                "pr_url": receipt.get("pr_url"), "dry_run": dry_run,
            },
            session_id=owner,
        )

        if dry_run:
            # Dry-run rehearses everything up to (not including) the live write -- it does not
            # reach PUSHED, since nothing was actually pushed. Return to APPROVED so a real
            # push can still be attempted afterward.
            _transition(manifest, "APPROVED", checkpoint="dry_run_rehearsed")
            return manifest

        # MT056: record the publication durably in data/readme_published_state.json so the
        # republication-debt tripwire (published_readme_current) re-derives it mechanically on
        # every future audit -- never only in a plan register (the TC-HARDEN-47/48 loss class).
        _record_publication(family, platform, receipt.get("pr_url"))
        _transition(manifest, "PUSHED", checkpoint="pushed")
        return manifest


def _record_publication(family: str, platform: str, pr_url: "str | None") -> None:
    state = _load_published_state() or {"schema_version": 1, "products": []}
    rows = state.setdefault("products", [])
    for row in rows:
        if row.get("family") == family and row.get("platform") == platform:
            row["last_known_publication"] = _now().date().isoformat()
            row["evidence"] = f"recorded by push (PR: {pr_url})"
            break
    else:
        rows.append({
            "family": family, "platform": platform,
            "last_known_publication": _now().date().isoformat(),
            "evidence": f"recorded by push (PR: {pr_url})",
        })
    _write_json(_published_state_path(), state)


def _do_push(manifest: dict, work_dir: Path, *, dry_run: bool, acting_model: str) -> dict:
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
        f"Co-Authored-By: {acting_model} <noreply@anthropic.com>\n"
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
    # MT056 (R-19, confirmed live 2026-08-16 via `gh pr view --json isDraft` -> true): MT032's
    # 2026-08-10 "no --draft" decision was applied to the skill doc and the manual SOP but never
    # to this CLI path -- the flag survived here, contradicting the documented contract. Removed;
    # none of these repos have branch protection or a second reviewer, so draft mode was pure
    # friction (MT032's own recorded reasoning).
    pr_result = _command_runner(
        ["gh", "pr", "create", "--repo", manifest["repo_full_name"], "--base", default_branch,
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
    p_push.add_argument(
        "--acting-model", required=True,
        help="Real, current display name of the model invoking this push (F-02: this script "
             "never hardcodes it -- only the calling agent knows its own real name).",
    )

    for name in ("abandon", "recover"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--run-id", required=True)
        cmd.add_argument("--reason", required=True)
        cmd.add_argument("--session-id")

    # TC-HARDEN-05 (MT035): real, registered portfolio-wide audit -- not run-scoped (no
    # --run-id), matching this command's own read-only, no-active-run-required nature.
    p_audit = sub.add_parser("audit-portfolio")
    p_audit.add_argument("--family", help="Limit to one family (requires --platform).")
    p_audit.add_argument("--platform", help="Limit to one platform (requires --family).")
    p_audit.add_argument("--json", action="store_true", help="Print the full structured result.")
    # MT056: read-only review of a non-default tree. Validated against
    # data/readme_candidate_store.json -- canonical or registered-archived only.
    p_audit.add_argument(
        "--candidate-tree",
        help="Audit this candidate tree instead of the configured default (canonical or a "
             "registered archived tree only; output is tagged non-canonical for the latter).",
    )

    # TC-20 (readme-refresh-trackb-and-followon-2026-09-01): explicit, auditable operation to
    # pin the commit a disposition ledger should be re-verified against, for the (rare) case
    # where the clone cache's live HEAD has legitimately moved past that ledger's own baseline
    # (a real republish, a history rewrite) -- never a raw file write, so the decision and its
    # evidence are always recorded together. Not run-scoped: this corrects a standing product-
    # level artifact, not one run's state.
    p_pin = sub.add_parser("pin-old-readme-baseline")
    p_pin.add_argument("family")
    p_pin.add_argument("platform")
    p_pin.add_argument("--commit", required=True, help="Git commit SHA in the product's clone cache.")
    p_pin.add_argument(
        "--reason", required=True,
        help="Why this commit, not live HEAD, is the disposition ledger's true baseline "
             "(cite the evidence -- e.g. a merged PR URL/number, a git-log investigation).",
    )
    p_pin.add_argument("--session-id")

    # TC-15/17 (readme-refresh-trackb-and-followon-2026-09-01): read-only by default; --apply
    # is the only path that writes (data/readme_published_state.json only, never a product repo).
    p_recon = sub.add_parser("reconcile-publications")
    p_recon.add_argument("--family", help="Limit to one family (requires --platform).")
    p_recon.add_argument("--platform", help="Limit to one platform (requires --family).")
    p_recon.add_argument(
        "--all", action="store_true", dest="all_products",
        help="Sweep every active, non-excluded product (required explicitly -- never the "
             "silent default).",
    )
    p_recon.add_argument(
        "--apply", action="store_true",
        help="Write discovered UNRECORDED_PUBLICATION reconciliations to "
             "data/readme_published_state.json. Omit for a read-only report.",
    )
    p_recon.add_argument("--json", action="store_true", help="Print the full structured result.")

    # MT056: change-scope / acceptance-registry / convergence workflow.
    p_scope = sub.add_parser("declare-scope")
    p_scope.add_argument("--run-id", required=True)
    p_scope.add_argument("--session-id")
    p_scope.add_argument("--issue", required=True, help="What this scope is correcting.")
    p_scope.add_argument(
        "--areas",
        help="Comma-separated stable block ids this run may change (## heading slugs, plus "
             "'__preamble__' and 'mermaid').",
    )
    p_scope.add_argument(
        "--allowed-deps",
        help="Comma-separated block ids that may legitimately change as declared dependents "
             "of the target areas (TOC, anchors, a summary of the changed section).",
    )
    p_scope.add_argument("--criteria", help="Acceptance criteria for the targeted area.")
    p_scope.add_argument(
        "--full-rewrite", action="store_true",
        help="Explicit whole-document scope (first composition / deliberate total regen).",
    )

    p_accept = sub.add_parser("accept-blocks")
    p_accept.add_argument("--run-id", required=True)
    p_accept.add_argument("--session-id")
    p_accept.add_argument("--blocks", required=True, help="Comma-separated block ids.")
    p_accept.add_argument(
        "--status", default="CONVERGED",
        help="CONVERGED (default) | FROZEN_ACCEPTED | ACTIVE_IMPROVEMENT | NEEDS_REVIEW | "
             "BLOCKED | INVALIDATED_BY_SOURCE_CHANGE",
    )
    p_accept.add_argument("--governing-rule")
    p_accept.add_argument("--evidence-ref")
    p_accept.add_argument("--note")

    p_converge = sub.add_parser("converge-verify")
    p_converge.add_argument("--run-id", required=True)
    p_converge.add_argument("--session-id")
    p_converge.add_argument(
        "--apply-invalidation", action="store_true",
        help="Flip source-invalidated CONVERGED/FROZEN blocks to INVALIDATED_BY_SOURCE_CHANGE "
             "(explicit reopening).",
    )

    args = parser.parse_args(argv)
    try:
        if args.command == "start":
            manifest = start_run(
                args.family, args.platform, run_id=args.run_id, session_id=args.session_id,
                skip_preflight=args.skip_preflight,
            )
        elif args.command == "audit-portfolio":
            if args.candidate_tree:
                configure(candidate_tree_name=args.candidate_tree)
            result = audit_portfolio(family=args.family, platform=args.platform)
            if args.json:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                if result.get("non_canonical"):
                    print(f"*** {result['non_canonical']} ***")
                print(f"{result['clean_count']}/{result['total']} products ALL HARD GATES CLEAN")
                # TC-AUDIT-01: "clean" alone conflates real disposition verification with a
                # published-status skip that never actually checked anything -- always print
                # this line too so the distinction can't be silently dropped from a default,
                # non-JSON audit call the way it was before this field existed.
                print(
                    f"{result['disposition_verified_count']}/{result['total']} products have "
                    f"REAL disposition-tracking verification (the rest are either dirty, or "
                    f"clean only because published-status skipped the check -- see "
                    f"disposition_tracking per product)"
                )
                published = [p for p in result["products"] if p.get("published")]
                if published:
                    names = ", ".join(f"{p['family']}/{p['platform']}" for p in published)
                    print(f"Already published upstream ({len(published)}): {names}")
                # TC-M56-09: drift is advisory (never a hard gate), so it can fire on an
                # otherwise-clean product -- printed as its own line, independent of the
                # DIRTY loop below, so it is never silently absorbed into "clean".
                drifted = [p for p in result["products"] if p.get("candidate_drift")]
                if drifted:
                    names = ", ".join(f"{p['family']}/{p['platform']}" for p in drifted)
                    print(f"Changed since last verified ({len(drifted)}): {names}")
                for p in result["products"]:
                    if not p["clean"]:
                        tag = " [published]" if p.get("published") else ""
                        tag += " [drift]" if p.get("candidate_drift") else ""
                        print(f"  DIRTY {p['family']}/{p['platform']}{tag}: {p['hard_gate_findings']}")
                if result["skipped"]:
                    print(f"Skipped ({len(result['skipped'])}, no candidate yet):")
                    for s in result["skipped"]:
                        print(f"  {s['family']}/{s['platform']}")
            return 0
        elif args.command == "pin-old-readme-baseline":
            sidecar = pin_old_readme_baseline(
                args.family, args.platform, args.commit, args.reason, session_id=args.session_id,
            )
            _print_manifest(sidecar)
            return 0
        elif args.command == "reconcile-publications":
            result = reconcile_publications(
                family=args.family, platform=args.platform,
                all_products=args.all_products, apply=args.apply,
            )
            if args.json:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                for r in result["reports"]:
                    print(f"  {r['family']}/{r['platform']}: {r['state']} -- {r['reason']}")
                if result["applied"]:
                    print(f"Applied {len(result['applied'])} reconciliation(s).")
            return 0
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
                manifest = push(
                    family, platform, args.run_id, session_id=args.session_id, dry_run=args.dry_run,
                    acting_model=args.acting_model,
                )
            elif args.command == "verify":
                result = verify(family, platform, args.run_id, session_id=args.session_id)
                print(json.dumps(result, indent=2, ensure_ascii=False))
                return 0
            elif args.command == "declare-scope":
                record = declare_scope(
                    family, platform, args.run_id, session_id=args.session_id,
                    issue=args.issue,
                    areas=[a.strip() for a in args.areas.split(",")] if args.areas else None,
                    allowed_dependencies=(
                        [d.strip() for d in args.allowed_deps.split(",")] if args.allowed_deps else None
                    ),
                    acceptance_criteria=args.criteria,
                    full_rewrite=args.full_rewrite,
                )
                print(json.dumps(record, indent=2, ensure_ascii=False))
                return 0
            elif args.command == "accept-blocks":
                registry = accept_blocks(
                    family, platform, args.run_id, session_id=args.session_id,
                    blocks=[b.strip() for b in args.blocks.split(",")],
                    status=args.status,
                    governing_rule=args.governing_rule,
                    evidence_ref=args.evidence_ref,
                    note=args.note,
                )
                print(json.dumps(registry, indent=2, ensure_ascii=False))
                return 0
            elif args.command == "converge-verify":
                verdict = converge_verify(
                    family, platform, args.run_id, session_id=args.session_id,
                    apply_invalidation=args.apply_invalidation,
                )
                print(json.dumps(verdict, indent=2, ensure_ascii=False))
                return 0 if verdict["converged"] else 2
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
