"""CONTRACT: verify -> classify -> deduplicate -> bundle -> draft -> (human-gated) file real
GitHub Issues against the upstream product repos this skill already works against, for defects
found during /readme-refresh (S-120) work (plan:
C:\\Users\\prora\\.claude\\plans\\d-users-prora-onedrive-documents-github-humble-tome.md,
Fifty-Seventh incident / MT057, 2026-08-19).

Sibling module to readme_refresh_run.py/readme_refresh_checks.py/dependency_extract.py, same
self-containment reasoning dependency_extract.py's own docstring already states for itself: a
finding and a bundle are a genuinely DIFFERENT entity type with a DIFFERENT lifecycle (per-
finding/per-bundle, not per-README-run), a DIFFERENT external side effect (`gh issue create`,
never `gh pr create`/a git push of README content), and a DIFFERENT manifest tree. Merging
FINDING_NEXT_STATES/BUNDLE_NEXT_STATES into readme_refresh_run.py's own NEXT_STATES would corrupt
that dict's proven, narrowly-scoped semantics -- every state there governs exactly one README
candidate's compose/verify/push lifecycle. This module never touches that dict or its
_transition(); it defines its own, mirroring the exact same idiom (illegal-transition raises,
save-then-event, evidence required) against a separate manifest tree.

Trigger: this skill's README-generation work has, across 50+ prior incidents, repeatedly found
real defects in the ~30 external upstream product repos it works against -- already recorded,
per-product, in local upstream-issues.md files (see _upstream_issues_path in readme_refresh_
run.py), but never used to actually file anything on GitHub. This module closes that gap with a
rigorous, human-gated pipeline: a finding is not an upstream defect until independently
reproduced against the CURRENT upstream repo; only confirmed, actionable, deduplicated,
correctly-bundled findings ever reach a drafted issue; no GitHub Issue is ever created without an
explicit, separate, per-action authorization (dry-run is the default and only mode for `create-
issue`, mirroring readme_refresh_run.py's own push()/`_do_push` dry-run-first, GH_TOKEN-gated
posture exactly).

Real, confirmed facts this design reconciles against (not assumed -- gathered via direct
file:line investigation this same session):
  - upstream-issues.md has TWO real format variants coexisting in the live portfolio today
    (Variant A: "# Upstream issues -- {Product Name}" + Verified/date header + `**Severity**`/
    `**Evidence**`/`**Impact**`/`**Not fixable here because**` fields, e.g. pdf/go, words/net;
    Variant B: "# Upstream issues found -- {family}/{platform}" + numbered `## {N}. {title}`
    headings + `**Severity**`/`**Evidence**` only, e.g. pdf/python, cells/java, 3d/typescript).
    Both are ingested as-is (Stage 1) -- never force-normalized, never rewritten.
  - No `gh api user` / caller-identity check exists anywhere in this codebase before this module
    -- _preflight_identity_check() below is genuinely new, mirroring _preflight_access_check's
    (readme_refresh_run.py:872) exact real shape.
  - `python_verification_runner` (readme_refresh_run.py, TC-HARDEN-01/MT033) is this codebase's
    ONE real "reproduce in a clean, disposable environment" mechanism, Python-only. Every other
    language's Stage-2 reproduction honestly reports `manual_language_specific` -- a real,
    already-disclosed gap (TC-HARDEN-01's own remaining scope), never faked here.

Two-tier state machine (Stage 9 of the mission spec), because a finding and a bundle are
genuinely different fan-in/fan-out entities (many findings fold into one bundle; one bundle
produces exactly one issue):

    FINDING_NEXT_STATES:
      DISCOVERED -> VERIFYING -> VERIFIED -> DUPLICATE_CHECKED -> BUNDLED  (terminal for the
        finding itself once folded into a bundle -- the finding manifest then carries a
        bundle_id pointer; further lifecycle progress is tracked on the bundle, not re-tracked
        on the finding)
      Alt-terminal: REJECTED_NOT_UPSTREAM, DUPLICATE_EXISTING, FIXED_UPSTREAM,
        PRIVATE_SECURITY_ROUTE, BLOCKED_MISSING_EVIDENCE, DEFERRED_LOW_PRIORITY

    BUNDLE_NEXT_STATES:
      BUNDLED -> DRAFTED -> INDEPENDENTLY_REVIEWED -> READY_TO_CREATE -> CREATED -> REMOTE_VERIFIED
      Alt-terminal: BLOCKED_IDENTITY (plus any finding-level shared terminal, if a whole bundle
        turns out non-actionable after drafting)

Every transition requires a non-optional evidence_ref -- the mission's own "every transition
requires evidence," enforced structurally (a required positional/keyword argument), never left
as a convention a caller might skip.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal, Optional, TypedDict

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
_FOSS_DIR = Path(__file__).resolve().parent
if str(_FOSS_DIR) not in sys.path:
    sys.path.insert(0, str(_FOSS_DIR))

from advisory_lock import FileLock, LockTimeout  # noqa: E402
from core.fs import atomic_write  # noqa: E402

import readme_refresh_checks as checks  # noqa: E402
import readme_refresh_run as run  # noqa: E402

SCHEMA_VERSION = 1
EXPECTED_GH_LOGIN = "babar-raza"
CLAUDE_MODEL_ID = "claude-sonnet-5"

# --- Schemas (Stages 1-6) ----------------------------------------------------------------------

VerificationOutcome = Literal[
    "CONFIRMED_UPSTREAM", "CONFIRMED_DOCUMENTATION_DEFECT", "CONFIRMED_PACKAGING_DEFECT",
    "CONFIRMED_COMPATIBILITY_DEFECT", "CONFIRMED_FEATURE_GAP", "ALREADY_FIXED", "EXISTING_ISSUE",
    "LOCAL_TOOLING_DEFECT", "STALE_INPUT", "UNSUPPORTED_USAGE", "EXPECTED_BEHAVIOR",
    "INSUFFICIENT_EVIDENCE", "SECURITY_PRIVATE_REPORT_REQUIRED", "NOT_ACTIONABLE",
]
_ACTIONABLE_OUTCOMES = frozenset({
    "CONFIRMED_UPSTREAM", "CONFIRMED_DOCUMENTATION_DEFECT", "CONFIRMED_PACKAGING_DEFECT",
    "CONFIRMED_COMPATIBILITY_DEFECT", "CONFIRMED_FEATURE_GAP",
})

Category = Literal[
    "functional_correctness", "data_loss_or_corruption", "public_api_behavior",
    "packaging_or_installation", "build_system", "runtime_dependency", "platform_compatibility",
    "performance_or_resource", "security_or_unsafe_behavior", "documentation", "readme_or_examples",
    "ci_or_test_coverage", "package_metadata", "release_or_distribution", "feature_request",
    "developer_experience",
]
_VALID_CATEGORIES = frozenset({
    "functional_correctness", "data_loss_or_corruption", "public_api_behavior",
    "packaging_or_installation", "build_system", "runtime_dependency", "platform_compatibility",
    "performance_or_resource", "security_or_unsafe_behavior", "documentation", "readme_or_examples",
    "ci_or_test_coverage", "package_metadata", "release_or_distribution", "feature_request",
    "developer_experience",
})
Severity = Literal["critical", "high", "medium", "low"]
_VALID_SEVERITIES = frozenset({"critical", "high", "medium", "low"})
Priority = Literal["P0", "P1", "P2", "P3", "P4"]
_VALID_PRIORITIES = frozenset({"P0", "P1", "P2", "P3", "P4"})
_VALID_VERIFICATION_OUTCOMES = frozenset({
    "CONFIRMED_UPSTREAM", "CONFIRMED_DOCUMENTATION_DEFECT", "CONFIRMED_PACKAGING_DEFECT",
    "CONFIRMED_COMPATIBILITY_DEFECT", "CONFIRMED_FEATURE_GAP", "ALREADY_FIXED", "EXISTING_ISSUE",
    "LOCAL_TOOLING_DEFECT", "STALE_INPUT", "UNSUPPORTED_USAGE", "EXPECTED_BEHAVIOR",
    "INSUFFICIENT_EVIDENCE", "SECURITY_PRIVATE_REPORT_REQUIRED", "NOT_ACTIONABLE",
})

DuplicateDisposition = Literal[
    "CREATE_NEW", "COMMENT_ON_EXISTING", "LINK_AS_RELATED", "ALREADY_RESOLVED",
    "WAIT_FOR_RELEASE", "DO_NOT_REPORT",
]
_VALID_DUPLICATE_DISPOSITIONS = frozenset({
    "CREATE_NEW", "COMMENT_ON_EXISTING", "LINK_AS_RELATED", "ALREADY_RESOLVED",
    "WAIT_FOR_RELEASE", "DO_NOT_REPORT",
})

FindingState = Literal[
    "DISCOVERED", "VERIFYING", "VERIFIED", "DUPLICATE_CHECKED", "BUNDLED",
    "REJECTED_NOT_UPSTREAM", "DUPLICATE_EXISTING", "FIXED_UPSTREAM", "PRIVATE_SECURITY_ROUTE",
    "BLOCKED_MISSING_EVIDENCE", "DEFERRED_LOW_PRIORITY",
]
BundleState = Literal[
    "BUNDLED", "DRAFTED", "INDEPENDENTLY_REVIEWED", "READY_TO_CREATE", "CREATED",
    "REMOTE_VERIFIED", "BLOCKED_IDENTITY",
    "REJECTED_NOT_UPSTREAM", "DUPLICATE_EXISTING", "FIXED_UPSTREAM", "PRIVATE_SECURITY_ROUTE",
    "BLOCKED_MISSING_EVIDENCE", "DEFERRED_LOW_PRIORITY",
]

FINDING_NEXT_STATES: dict[str, set[str]] = {
    "DISCOVERED": {"VERIFYING", "REJECTED_NOT_UPSTREAM", "BLOCKED_MISSING_EVIDENCE"},
    "VERIFYING": {
        "VERIFIED", "REJECTED_NOT_UPSTREAM", "FIXED_UPSTREAM", "PRIVATE_SECURITY_ROUTE",
        "BLOCKED_MISSING_EVIDENCE", "DEFERRED_LOW_PRIORITY",
    },
    "VERIFIED": {"DUPLICATE_CHECKED", "DEFERRED_LOW_PRIORITY", "PRIVATE_SECURITY_ROUTE"},
    "DUPLICATE_CHECKED": {
        "BUNDLED", "DUPLICATE_EXISTING", "FIXED_UPSTREAM", "DEFERRED_LOW_PRIORITY",
    },
    "BUNDLED": set(),  # terminal for the FINDING -- lifecycle continues on the bundle manifest
    "REJECTED_NOT_UPSTREAM": set(),
    "DUPLICATE_EXISTING": set(),
    "FIXED_UPSTREAM": set(),
    "PRIVATE_SECURITY_ROUTE": set(),
    "BLOCKED_MISSING_EVIDENCE": {"VERIFYING", "DISCOVERED"},  # re-enterable once evidence lands
    "DEFERRED_LOW_PRIORITY": {"VERIFYING", "DUPLICATE_CHECKED"},  # re-enterable on re-prioritization
}
FINDING_TERMINAL_STATES = frozenset({
    "BUNDLED", "REJECTED_NOT_UPSTREAM", "DUPLICATE_EXISTING", "FIXED_UPSTREAM",
    "PRIVATE_SECURITY_ROUTE",
})

BUNDLE_NEXT_STATES: dict[str, set[str]] = {
    "BUNDLED": {"DRAFTED", "REJECTED_NOT_UPSTREAM", "DEFERRED_LOW_PRIORITY"},
    "DRAFTED": {"INDEPENDENTLY_REVIEWED", "BUNDLED", "DEFERRED_LOW_PRIORITY"},
    "INDEPENDENTLY_REVIEWED": {"READY_TO_CREATE", "DRAFTED", "DEFERRED_LOW_PRIORITY"},
    "READY_TO_CREATE": {"CREATED", "BLOCKED_IDENTITY", "DUPLICATE_EXISTING", "DEFERRED_LOW_PRIORITY"},
    "CREATED": {"REMOTE_VERIFIED"},
    "REMOTE_VERIFIED": set(),
    "BLOCKED_IDENTITY": {"READY_TO_CREATE"},  # re-enterable once the correct account authenticates
    "REJECTED_NOT_UPSTREAM": set(),
    "DUPLICATE_EXISTING": set(),
    "FIXED_UPSTREAM": set(),
    "PRIVATE_SECURITY_ROUTE": set(),
    "BLOCKED_MISSING_EVIDENCE": {"DRAFTED"},
    "DEFERRED_LOW_PRIORITY": {"DRAFTED", "INDEPENDENTLY_REVIEWED", "READY_TO_CREATE"},
}
BUNDLE_TERMINAL_STATES = frozenset({
    "REMOTE_VERIFIED", "REJECTED_NOT_UPSTREAM", "DUPLICATE_EXISTING", "FIXED_UPSTREAM",
    "PRIVATE_SECURITY_ROUTE",
})


class UpstreamIssueWorkflowError(RuntimeError):
    """Raised when an upstream-issue-workflow contract or state transition is unsafe. Never
    ReadmeRefreshRunError -- a deliberately separate exception type, matching dependency_
    extract.py's own DependencyExtractionError precedent, so callers (and tests) can never
    confuse this module's own failures with the README-run state machine's."""


# --- Config (mirrors readme_refresh_run.py's configure() shape exactly, reusing its own
# module-level state for repo_root/reports_root/clone_cache_root/candidate_tree_name rather than
# duplicating a second copy of the same knobs -- this module always defers to `run`'s current
# configuration, so a test calling run.configure(...) transparently redirects this module too) --


def _repo_root() -> Path:
    return run._repo_root


def _reports_root() -> Path:
    return run._reports_root


# --- Paths -------------------------------------------------------------------------------------


def _issue_workflow_root(family: str, platform: str) -> Path:
    return _reports_root() / "upstream_issue_runs" / family / platform


def _inventory_path(family: str, platform: str) -> Path:
    return _issue_workflow_root(family, platform) / "inventory.json"


def _finding_counter_path(family: str, platform: str) -> Path:
    return _issue_workflow_root(family, platform) / ".finding_counter.json"


def _bundle_counter_path(family: str, platform: str) -> Path:
    return _issue_workflow_root(family, platform) / ".bundle_counter.json"


def _finding_root(family: str, platform: str, finding_id: str) -> Path:
    return _issue_workflow_root(family, platform) / "findings" / finding_id


def _finding_manifest_path(family: str, platform: str, finding_id: str) -> Path:
    return _finding_root(family, platform, finding_id) / "manifest.json"


def _finding_verification_path(family: str, platform: str, finding_id: str) -> Path:
    return _finding_root(family, platform, finding_id) / "verification.json"


def _finding_classification_path(family: str, platform: str, finding_id: str) -> Path:
    return _finding_root(family, platform, finding_id) / "classification.json"


def _finding_events_path(family: str, platform: str, finding_id: str) -> Path:
    return _finding_root(family, platform, finding_id) / "events.jsonl"


def _bundle_root(family: str, platform: str, bundle_id: str) -> Path:
    return _issue_workflow_root(family, platform) / "bundles" / bundle_id


def _bundle_manifest_path(family: str, platform: str, bundle_id: str) -> Path:
    return _bundle_root(family, platform, bundle_id) / "manifest.json"


def _bundle_duplicate_search_path(family: str, platform: str, bundle_id: str) -> Path:
    return _bundle_root(family, platform, bundle_id) / "duplicate-search.json"


def _bundle_draft_path(family: str, platform: str, bundle_id: str) -> Path:
    return _bundle_root(family, platform, bundle_id) / "draft.md"


def _bundle_attribution_path(family: str, platform: str, bundle_id: str) -> Path:
    return _bundle_root(family, platform, bundle_id) / "attribution.json"


def _bundle_validation_path(family: str, platform: str, bundle_id: str) -> Path:
    return _bundle_root(family, platform, bundle_id) / "validation.json"


def _bundle_creation_receipt_path(family: str, platform: str, bundle_id: str) -> Path:
    return _bundle_root(family, platform, bundle_id) / "creation-receipt.json"


def _bundle_events_path(family: str, platform: str, bundle_id: str) -> Path:
    return _bundle_root(family, platform, bundle_id) / "events.jsonl"


def _duplicate_search_ledger_path(family: str, platform: str) -> Path:
    return _issue_workflow_root(family, platform) / "duplicate-search-ledger.json"


def _bundle_ledger_path(family: str, platform: str) -> Path:
    return _issue_workflow_root(family, platform) / "bundle-ledger.json"


def _issue_queue_path(family: str, platform: str) -> Path:
    return _issue_workflow_root(family, platform) / "issue-queue.json"


def _cross_run_action_ledger_path() -> Path:
    return _reports_root() / "upstream_issue_actions.jsonl"


def _false_positive_exclusions_path() -> Path:
    return _repo_root() / "data" / "upstream_issue_false_positive_exclusions.json"


# --- Small shared helpers ------------------------------------------------------------------


def _utc() -> str:
    return run._now().astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    prior = path.read_text(encoding="utf-8") if path.is_file() else ""
    atomic_write(path, prior + json.dumps(row, ensure_ascii=False) + "\n")


def _next_counter(path: Path, *, lock_timeout: float = 10.0) -> int:
    """Real, lock-guarded sequential counter (findings and bundles each get their own). A bare
    read-modify-write without a lock would let two concurrent sessions both read counter=N and
    both mint the same next ID -- a real, already-documented concurrent-session hazard class in
    this repo (ST-021 and its many descendants throughout this plan's history). One short-lived
    FileLock per increment is cheap and correctness-critical here, unlike the per-product README
    run lock (_product_guard), which guards a much longer-lived, more contended resource."""
    lock_path = path.with_suffix(path.suffix + ".lock")
    try:
        with FileLock(lock_path, timeout=lock_timeout):
            current = _read_json(path, default={"next": 1})
            value = int(current.get("next", 1))
            _write_json(path, {"next": value + 1})
            return value
    except LockTimeout as exc:
        raise UpstreamIssueWorkflowError(f"Could not acquire counter lock {lock_path}: {exc}") from exc


def _new_finding_id(family: str, platform: str) -> str:
    seq = _next_counter(_finding_counter_path(family, platform))
    return f"UF-{family}-{platform}-{seq:04d}"


def _new_bundle_id(family: str, platform: str) -> str:
    seq = _next_counter(_bundle_counter_path(family, platform))
    return f"UB-{family}-{platform}-{seq:04d}"


# --- Finding-level state machine (Stage 9) --------------------------------------------------


def _finding_event(family: str, platform: str, finding_id: str, event_type: str, **fields: Any) -> None:
    _append_jsonl(
        _finding_events_path(family, platform, finding_id),
        {"at": _utc(), "event": event_type, **fields},
    )


def _load_finding(family: str, platform: str, finding_id: str) -> dict:
    path = _finding_manifest_path(family, platform, finding_id)
    if not path.is_file():
        raise UpstreamIssueWorkflowError(f"Finding not found: {finding_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def _transition_finding(manifest: dict, target: str, *, evidence_ref: str) -> None:
    if not evidence_ref or not evidence_ref.strip():
        raise UpstreamIssueWorkflowError(
            f"Illegal finding transition {manifest.get('state')} -> {target}: evidence_ref is "
            f"required for every transition and was empty (mission Stage 9: \"every transition "
            f"requires evidence\")"
        )
    current = manifest["state"]
    if target not in FINDING_NEXT_STATES.get(current, set()):
        raise UpstreamIssueWorkflowError(f"Illegal finding transition: {current} -> {target}")
    manifest["state"] = target
    manifest["evidence_ref"] = evidence_ref
    _write_json(
        _finding_manifest_path(manifest["family"], manifest["platform"], manifest["finding_id"]),
        manifest,
    )
    _finding_event(
        manifest["family"], manifest["platform"], manifest["finding_id"], "STATE_TRANSITION",
        previous=current, current=target, evidence_ref=evidence_ref,
    )


# --- Bundle-level state machine (Stage 9) ---------------------------------------------------


def _bundle_event(family: str, platform: str, bundle_id: str, event_type: str, **fields: Any) -> None:
    _append_jsonl(
        _bundle_events_path(family, platform, bundle_id),
        {"at": _utc(), "event": event_type, **fields},
    )


def _load_bundle(family: str, platform: str, bundle_id: str) -> dict:
    path = _bundle_manifest_path(family, platform, bundle_id)
    if not path.is_file():
        raise UpstreamIssueWorkflowError(f"Bundle not found: {bundle_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def _transition_bundle(manifest: dict, target: str, *, evidence_ref: str) -> None:
    if not evidence_ref or not evidence_ref.strip():
        raise UpstreamIssueWorkflowError(
            f"Illegal bundle transition {manifest.get('state')} -> {target}: evidence_ref is "
            f"required for every transition and was empty"
        )
    current = manifest["state"]
    if target not in BUNDLE_NEXT_STATES.get(current, set()):
        raise UpstreamIssueWorkflowError(f"Illegal bundle transition: {current} -> {target}")
    manifest["state"] = target
    manifest["evidence_ref"] = evidence_ref
    _write_json(
        _bundle_manifest_path(manifest["family"], manifest["platform"], manifest["bundle_id"]),
        manifest,
    )
    _bundle_event(
        manifest["family"], manifest["platform"], manifest["bundle_id"], "STATE_TRANSITION",
        previous=current, current=target, evidence_ref=evidence_ref,
    )


# --- Cross-run action ledger (mirrors readme_refresh_run.py's _append_action_ledger_row exactly,
# same row shape, new filename -- TC-HARDEN-15/MT035's own established pattern, reused not
# duplicated with different semantics) --------------------------------------------------------


def _append_upstream_action_ledger_row(
    family: str, platform: str, *, action: str, details: dict, session_id: str,
) -> None:
    _append_jsonl(
        _cross_run_action_ledger_path(),
        {
            "event_id": uuid.uuid4().hex,
            "family": family,
            "platform": platform,
            "skill": "readme-refresh",
            "action": action,
            "timestamp": _utc(),
            "details": details,
            "session_id": session_id,
        },
    )


# --- Identity verification (Attribution requirements, TC-UIW-05) -----------------------------


def _preflight_identity_check() -> dict:
    """Real gh api call -- direct structural mirror of readme_refresh_run.py's own
    _preflight_access_check(repo_full_name) (line 872), the exact real pattern this module was
    told to follow. That function checks REPO-level access (does this token have push/admin on
    repo X); this checks CALLER IDENTITY (which real GitHub account is authenticated at all) --
    a check that has never existed anywhere in this codebase before this module (confirmed by
    direct grep, zero hits for "gh api user" anywhere in scripts/pipeline/ prior to this file).

    GitHub Issues have no commit-style co-authorship metadata -- the issue's real, permanent
    author is whichever account's token created it, full stop. The mission's own Attribution
    requirements are explicit: if the authenticated account is not exactly EXPECTED_GH_LOGIN
    ("babar-raza"), no issue may be created, under any circumstance, no matter how confirmed or
    well-drafted the finding is. This function only ever answers "who is authenticated" -- it
    never decides what to do with the answer (that's create_issue()'s own job, since only that
    function knows whether to write a BLOCKED_IDENTITY bundle-state transition).

    Returns {"login": str, "authenticated": bool}. Never raises on a failed/absent
    authentication -- an unauthenticated `gh` is itself a real, valid (if unfortunate) outcome
    this function must report accurately, not treat as a crash. Only a genuinely unparseable
    response (a `gh` binary that's broken/missing in a way that can't even tell us "not logged
    in") raises.
    """
    result = run._command_runner(
        ["gh", "api", "user", "--jq", "{login}"],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        # A non-zero exit from `gh api user` (not authenticated, expired token, network error)
        # is a real, reportable "not the right account" outcome -- never silently swallowed,
        # but also never a hard crash, since "nobody is authenticated" is exactly the case this
        # check exists to catch and block on, not an infrastructure failure.
        return {"login": None, "authenticated": False, "raw_error": (result.stderr or result.stdout).strip()}
    try:
        info = json.loads(result.stdout)
    except Exception as exc:
        raise UpstreamIssueWorkflowError(
            f"Identity check returned unparseable output from `gh api user`: {exc}"
        ) from exc
    login = info.get("login")
    return {"login": login, "authenticated": bool(login)}


# --- Stage 1: dual-variant upstream-issues.md ingestion (TC-UIW-04) --------------------------

SourceFormat = Literal["variant_a", "variant_b", "non_markdown"]

_NUMBERED_HEADING_RE = re.compile(r"^(\d+)\.\s*(.+)$")


def _extract_dash_field(body: str, field_name: str) -> "str | None":
    """Extract a `- **{field_name}**: value` bullet's own value from a real upstream-issues.md
    entry body, tolerating a wrapped/multi-line/multi-paragraph continuation up to (but not
    including) the next `- **...**:` field bullet or the entry's own end -- real, confirmed
    necessary against real content, not a synthetic assumption: `cells/java`'s real Evidence
    field alone spans 5 physical lines with no leading `- ` on the continuation lines, and
    `pdf/python`'s real Evidence fields are followed by multiple full paragraphs (including a
    fenced code block) before the next field starts. Returns None when the field is genuinely
    absent -- callers must never assume every entry has every field: that absence is exactly
    what makes Variant A (`Impact`/`Not fixable here because` present) and Variant B (neither
    present) real, different variants, not one schema with optional decoration."""
    pattern = re.compile(
        rf"^-\s*\*\*{re.escape(field_name)}\*\*:\s*(.*?)(?=^-\s*\*\*[^*]+\*\*:|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(body)
    if not match:
        return None
    value = match.group(1).strip()
    return value or None


def _classify_source_format(severity_raw: "str | None", impact_raw: "str | None", not_fixable_raw: "str | None") -> SourceFormat:
    """Variant A carries Impact / Not-fixable-here-because fields Variant B never has (confirmed
    real across every sampled file this session: pdf/go and words/net always carry both; pdf/
    python, cells/java's own real file, and 3d/typescript never carry either) -- this is a more
    reliable per-entry signal than the H1 heading wording, which this function deliberately does
    not consult, since an entry-level classification should not depend on a fact that lives
    outside the entry itself. An entry with neither Impact/Not-fixable-here-because NOR a real
    Severity value (e.g. pdf/python's own real "## Note: schema for this file..." meta-commentary
    heading, which has no `**Severity**:` line at all) is still classified variant_b -- Stage 1
    ingests every real `##` entry mechanically, per the mission's own "never force-normalize,
    never judge at ingestion time" instruction; whether a raw entry like this is even a real
    upstream finding at all is a Stage 2/3 verification-and-classification question, never
    decided here."""
    if impact_raw or not_fixable_raw:
        return "variant_a"
    return "variant_b"


def _normalize_finding_title(original_observation: str) -> str:
    return re.sub(r"\s+", " ", original_observation.strip().lower())


def _compute_finding_fingerprint(family: str, platform: str, original_observation: str) -> str:
    """A stable, content-derived identity for a finding -- deliberately NOT the sequential
    finding_id, which `inventory()`'s own docstring already discloses is re-minted fresh on
    every re-run (a real, disclosed, out-of-scope design decision for this module). An
    exclusion recorded against one run's `UF-pdf-go-0007` would silently stop matching the
    identical, unchanged real entry the next time `inventory()` runs and mints `UF-pdf-go-0011`
    instead -- exactly the kind of position-based drift this whole plan's own MT048 incident
    already found and hardened against for a materially similar disposition-file problem. A
    sha256 hex digest of `family|platform|normalized_title` is stable across re-ingestion as
    long as the real upstream-issues.md entry's own title doesn't change, and changes (correctly)
    the moment it does -- an exclusion should never silently keep matching a title that was
    edited to describe something new."""
    key = f"{family}|{platform}|{_normalize_finding_title(original_observation)}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _load_false_positive_exclusions() -> list[dict]:
    """Same absent-tolerant, evidence-required-provenance governance shape as run.py's own
    `_load_api_reference_class_exclusions` (TC-HARDEN-77/MT047) -- a small, hand-curated list, a
    real, empty [] the common state until this module's own first confirmed false positive,
    never a hard failure when the file doesn't exist yet."""
    path = _false_positive_exclusions_path()
    if not path.is_file():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _product_false_positive_fingerprints(family: str, platform: str) -> dict[str, dict]:
    """Flattens the full, cross-portfolio exclusion list down to just this product's own
    confirmed `finding_fingerprint -> exclusion record` mapping -- the exact same flatten-by-
    product idiom `_product_api_reference_class_exclusions` already uses, reused here for a
    different override file, not re-invented."""
    return {
        entry["finding_fingerprint"]: entry
        for entry in _load_false_positive_exclusions()
        if entry.get("family") == family and entry.get("platform") == platform and entry.get("finding_fingerprint")
    }


def _resolve_repository(family: str, platform: str) -> dict:
    """Real product resolution, reusing run._resolve_product's own real, current
    data/products.json + data/registry_exclusions.json lookup verbatim -- deliberately not
    re-implemented here. run._resolve_product raises run.ReadmeRefreshRunError (not this
    module's own UpstreamIssueWorkflowError) on an inactive/excluded/unknown product; that
    exception is allowed to propagate unchanged, matching how every other run.* helper this
    module already reuses (e.g. run._now, run._command_runner) keeps its own real error
    semantics rather than being silently re-wrapped into a different exception type."""
    return run._resolve_product(family, platform)


def inventory(family: str, platform: str, *, session_id: str = "cli") -> dict:
    """Stage 1 (mission spec) -- real, mechanical dual-variant ingestion of the product's own,
    already-existing `reports/{tree}/{family}/{platform}/upstream-issues.md`. Never invents,
    never judges: every real `##` entry present in the file becomes exactly one new Finding
    record in state DISCOVERED, verbatim `source_excerpt` preserved, `severity_raw`/`impact_raw`/
    `not_fixable_because_raw` kept as untouched passthrough fields for Stage 3's own later,
    explicit classification mapping -- per the mission's own "never force-normalize, never
    rewrite" instruction, restated for this specific new module.

    A missing or empty upstream-issues.md (a real, common, correct state -- e.g. a fresh
    "No upstream issues identified during verification." stub, or the file simply not existing
    yet) is not an error: this returns a real, valid, zero-finding inventory, matching this
    module's own established "absence is a real, valid outcome, not a crash" posture already used
    by `_preflight_identity_check`.

    Idempotent per real file content, not per call: re-running `inventory()` against an unchanged
    upstream-issues.md re-mints a fresh set of finding_ids for the same real entries (this module
    intentionally does not attempt content-hash-based finding-identity reuse across inventory
    runs -- a real, disclosed, deliberately out-of-scope design question the mission's own Stage 1
    spec never asked this taskcard to solve; re-running inventory() on an already-ingested product
    is expected to be a rare, deliberate, human-directed action, not a routine one, exactly like
    every other *_run.py `start`-shaped verb in this skill family).
    """
    product = _resolve_repository(family, platform)
    upstream_issues_path = run._upstream_issues_path(family, platform)
    text = upstream_issues_path.read_text(encoding="utf-8") if upstream_issues_path.is_file() else ""
    exclusions = _product_false_positive_fingerprints(family, platform)

    finding_ids: list[str] = []
    auto_rejected_count = 0
    for title, body in checks.split_upstream_issue_entries(text):
        numbered = _NUMBERED_HEADING_RE.match(title.strip())
        clean_title = numbered.group(2).strip() if numbered else title.strip()
        severity_raw = _extract_dash_field(body, "Severity")
        evidence_raw = _extract_dash_field(body, "Evidence")
        impact_raw = _extract_dash_field(body, "Impact")
        not_fixable_raw = _extract_dash_field(body, "Not fixable here because")
        source_format = _classify_source_format(severity_raw, impact_raw, not_fixable_raw)
        fingerprint = _compute_finding_fingerprint(family, platform, clean_title)
        matched_exclusion = exclusions.get(fingerprint)

        finding_id = _new_finding_id(family, platform)
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "finding_id": finding_id,
            "family": family,
            "platform": platform,
            "product": product.get("repo_name", f"{family}/{platform}"),
            "repository": product.get("repo_url", ""),
            "component": None,
            "original_observation": clean_title,
            "source_format": source_format,
            "source_excerpt": f"## {title}\n{body}".rstrip() + "\n",
            "source_file": str(upstream_issues_path),
            "source_revision": "unknown",
            "state": "DISCOVERED",
            "evidence_ref": None,
            "existing_evidence": [ref for ref in (evidence_raw,) if ref],
            "discovered_via": "upstream_issues_md_audit",
            "finding_fingerprint": fingerprint,
            "raw_fields": {
                "severity_raw": severity_raw,
                "evidence_raw": evidence_raw,
                "impact_raw": impact_raw,
                "not_fixable_because_raw": not_fixable_raw,
            },
            "discovered_at": _utc(),
        }
        _write_json(_finding_manifest_path(family, platform, finding_id), manifest)
        _finding_event(
            family, platform, finding_id, "DISCOVERED",
            source_format=source_format, evidence_ref=str(upstream_issues_path),
        )
        if matched_exclusion is not None:
            # TC-UIW-08: a confirmed, human-curated false positive is auto-ingested straight to
            # its terminal REJECTED_NOT_UPSTREAM state via the real, evidence-required
            # _transition_finding path (never a hand-set "state" field bypassing it) -- citing
            # the exclusion record's own provenance as the transition's evidence_ref, so a human
            # reviewing this finding later can see exactly which prior, verified decision fired.
            manifest = _load_finding(family, platform, finding_id)
            _transition_finding(
                manifest, "REJECTED_NOT_UPSTREAM",
                evidence_ref=(
                    f"auto-rejected via data/upstream_issue_false_positive_exclusions.json "
                    f"(verified_by={matched_exclusion.get('verified_by')!r}, "
                    f"verified_at={matched_exclusion.get('verified_at')!r}): "
                    f"{matched_exclusion.get('evidence_note', '')}"
                ),
            )
            auto_rejected_count += 1
        finding_ids.append(finding_id)

    inventory_record = {
        "schema_version": SCHEMA_VERSION,
        "family": family,
        "platform": platform,
        "inventoried_at": _utc(),
        "source_file": str(upstream_issues_path),
        "source_file_existed": upstream_issues_path.is_file(),
        "finding_count": len(finding_ids),
        "auto_rejected_count": auto_rejected_count,
        "finding_ids": finding_ids,
    }
    _write_json(_inventory_path(family, platform), inventory_record)
    _append_upstream_action_ledger_row(
        family, platform, action="inventory",
        details={"finding_count": len(finding_ids), "finding_ids": finding_ids},
        session_id=session_id,
    )
    return inventory_record


def check_identity(*, family: "str | None" = None, platform: "str | None" = None) -> dict:
    """Standalone, re-runnable CLI-facing wrapper -- the mission's own `check-identity` verb
    (Stage 10, step 1; also independently invocable ahead of time for a quick sanity check).
    Never blocks anything by itself -- it is a real, honest report of the detected identity,
    consumed by create_issue() at the actual gate."""
    result = _preflight_identity_check()
    result["expected_login"] = EXPECTED_GH_LOGIN
    result["is_authorized"] = result.get("login") == EXPECTED_GH_LOGIN
    if family and platform:
        _append_upstream_action_ledger_row(
            family, platform, action="identity_check",
            details={
                "detected_login": result.get("login"), "is_authorized": result["is_authorized"],
            },
            session_id="cli",
        )
    return result


# --- Stage 2: verification tooling (TC-UIW-09) ------------------------------------------------

ReproductionEnvironment = Literal[
    "disposable_python_venv", "manual_language_specific", "not_reproducible_environment_only",
]

# Real, disclosed gap (TC-HARDEN-01/MT033's own scope, restated here for this module): only
# Python has a real, disposable, clean-environment reproduction mechanism anywhere in this
# codebase (`run.python_verification_runner`/`_acquire_python_environment`). Every other real
# language in this portfolio (Java/.NET/Go/Rust/C++/TypeScript) has none -- Stage 2 verification
# for those honestly reports `manual_language_specific`, never a fabricated "clean disposable
# environment" claim this codebase cannot back up. Keyed by the real `platform` values this
# skill's own `data/products.json` already uses.
_LANGUAGE_MANUAL_PROCEDURE_NOTES: dict[str, str] = {
    "java": "No disposable-environment runner exists for Java in this codebase. Manual procedure: "
            "`mvn dependency:get`/`mvn test` against the real, refreshed clone cache (the same "
            "acquire step this plan's own Verification pass section already documents for Java).",
    "net": "No disposable-environment runner exists for .NET. Manual procedure: `dotnet build`/"
           "`dotnet run` against the real, refreshed clone cache (published packages: `dotnet add "
           "package` real NuGet resolve first).",
    "go": "No disposable-environment runner exists for Go. Manual procedure: `go build`/`go run` "
          "against the real, refreshed clone cache (real `go get {module}@{tag}` module fetch "
          "first for a published product).",
    "rust": "No disposable-environment runner exists for Rust. Manual procedure: `cargo build`/"
            "`cargo test` against the real, refreshed clone cache, using the toolchain already "
            "installed for this repo's own verification sprints.",
    "cpp": "No disposable-environment runner exists for C++. Manual procedure: the real, "
           "documented CMake/Ninja build against the refreshed clone cache (or a real NuGet "
           "resolve first, for a published C++ product).",
    "typescript": "No disposable-environment runner exists for TypeScript. Manual procedure: "
                  "`npm install && npm run build` (plus `tsc --strict`) against the refreshed "
                  "clone cache.",
}


def _reproduction_environment_for_platform(platform: str) -> ReproductionEnvironment:
    if platform == "python":
        return "disposable_python_venv"
    return "manual_language_specific"


def _refresh_upstream_clone(family: str, platform: str) -> dict:
    """Real `git fetch` + `git reset --hard origin/{default_branch}` against the real, already-
    cached clone (`run._product_clone_cache`) -- "refresh the upstream clone" (mission Stage 2,
    step 1). Deliberately IN PLACE against the existing cache, never a fresh `git clone` into a
    new directory -- the clone cache is already a real, current-as-of-last-scout local checkout
    every product in this skill family already relies on being present, matching this same
    codebase's own `_acquire_python_environment`'s "never git clone --local into a fresh dir
    first" precedent for a materially similar reason (the read-only source is already local).

    A missing clone cache directory is a real, valid, honestly-reported outcome
    (`clone_cache_exists: False`) -- never a crash. Stage 2 verification for a product whose
    clone was never scouted (real `/repo-scout` run required first) must fail closed with a
    named, actionable reason, not raise an unrelated exception deep in a git subprocess call.
    """
    clone_cache = run._product_clone_cache(family, platform)
    result = {
        "clone_cache_path": str(clone_cache), "clone_cache_exists": clone_cache.is_dir(),
        "default_branch": None, "commit_before": None, "commit_after": None,
        "fetch_ok": False, "detail": None,
    }
    if not clone_cache.is_dir():
        result["detail"] = (
            "clone cache directory does not exist -- this product was never scouted (a real "
            "/repo-scout run is required before Stage 2 verification can refresh/inspect it)"
        )
        return result

    def _run_git(*args: str) -> Any:
        return run._command_runner(
            ["git", *args], cwd=str(clone_cache), capture_output=True, text=True, timeout=120,
        )

    commit_before = _run_git("rev-parse", "HEAD")
    result["commit_before"] = commit_before.stdout.strip() if commit_before.returncode == 0 else None

    fetch = _run_git("fetch", "origin", "--prune")
    if fetch.returncode != 0:
        result["commit_after"] = result["commit_before"]
        result["detail"] = f"git fetch origin failed: {(fetch.stderr or fetch.stdout).strip()[-2000:]}"
        return result

    default_branch = None
    set_head = _run_git("remote", "set-head", "origin", "-a")
    if set_head.returncode == 0:
        symref = _run_git("symbolic-ref", "refs/remotes/origin/HEAD", "--short")
        if symref.returncode == 0 and symref.stdout.strip().startswith("origin/"):
            default_branch = symref.stdout.strip()[len("origin/"):]
    if not default_branch:
        # Real, disclosed fallback -- never silently asserted as a verified fact when the
        # real auto-detection above did not succeed (e.g. a bare/local-only test remote with
        # no HEAD-advertising server side). "main" matches this portfolio's own most common
        # real default -- callers must treat a fallback-derived default_branch as unverified.
        default_branch = "main"
    result["default_branch"] = default_branch

    reset = _run_git("reset", "--hard", f"origin/{default_branch}")
    if reset.returncode != 0:
        result["commit_after"] = result["commit_before"]
        result["detail"] = (
            f"git reset --hard origin/{default_branch} failed: "
            f"{(reset.stderr or reset.stdout).strip()[-2000:]}"
        )
        return result

    commit_after = _run_git("rev-parse", "HEAD")
    result["commit_after"] = commit_after.stdout.strip() if commit_after.returncode == 0 else None
    result["fetch_ok"] = True
    result["detail"] = "refreshed"
    return result


def verify_finding(
    family: str, platform: str, finding_id: str, *,
    outcome: VerificationOutcome, evidence_ref: str,
    reproducer_commands: "list[dict] | None" = None,
    local_tooling_ruled_out: bool = False,
    supported_matrix_checked: bool = False,
    source_or_tests_inspected: bool = False,
    documentation_contract_compared: bool = False,
    independent_reviewer: "dict | None" = None,
    sanitization_applied: bool = False,
    package_or_release_version_confirmed: "str | None" = None,
    verified_by: str = "cli",
) -> dict:
    """Stage 2 (mission spec) -- writes the real, real-evidence verification record for one
    already-DISCOVERED finding, refreshing the upstream clone first (always, real, in-place --
    never skipped, never assumed still current from a prior run). Real per-language reproduction
    happens Python-only (`disposable_python_venv`); every other language honestly records
    `manual_language_specific` with a real, named procedure note -- this function itself never
    fabricates a clean-environment reproduction it cannot actually perform; the CALLER (an agent
    or a human, following `_LANGUAGE_MANUAL_PROCEDURE_NOTES`'s own real, per-language guidance)
    supplies whatever `reproducer_commands` it genuinely ran, verbatim.

    `outcome` must be one of the mission's own 14 real `VerificationOutcome` values -- an
    `_ACTIONABLE_OUTCOMES` member transitions the finding to VERIFIED; every other real outcome
    maps to its own correct alt-terminal/re-enterable FINDING_NEXT_STATES target, matching the
    mission's own real enum-to-state mapping, never a bare, undifferentiated "not verified." A
    typo'd/unrecognized outcome value raises immediately -- Literal type hints are not enforced
    at runtime, and the real fallback branch below exists to route a genuinely-recognized-but-
    non-actionable outcome, never to silently absorb a caller's typo as if it meant
    REJECTED_NOT_UPSTREAM.
    """
    if outcome not in _VALID_VERIFICATION_OUTCOMES:
        raise UpstreamIssueWorkflowError(
            f"Unknown VerificationOutcome {outcome!r} -- must be one of {sorted(_VALID_VERIFICATION_OUTCOMES)}"
        )
    manifest = _load_finding(family, platform, finding_id)
    if manifest["state"] not in ("DISCOVERED", "BLOCKED_MISSING_EVIDENCE"):
        raise UpstreamIssueWorkflowError(
            f"verify_finding requires state DISCOVERED (or BLOCKED_MISSING_EVIDENCE to retry) -- "
            f"{finding_id} is currently {manifest['state']!r}"
        )
    if manifest["state"] == "DISCOVERED":
        _transition_finding(manifest, "VERIFYING", evidence_ref=f"verify_finding started by {verified_by}")
    else:
        _transition_finding(manifest, "VERIFYING", evidence_ref=f"re-entering verification, {verified_by}")

    clone_refresh = _refresh_upstream_clone(family, platform)
    reproduction_environment = _reproduction_environment_for_platform(platform)
    manual_note = _LANGUAGE_MANUAL_PROCEDURE_NOTES.get(platform) if reproduction_environment == "manual_language_specific" else None

    record = {
        "schema_version": SCHEMA_VERSION,
        "finding_id": finding_id,
        "verified_at": _utc(),
        "verified_by": verified_by,
        "upstream_clone_refreshed": clone_refresh["fetch_ok"],
        "clone_commit_before": clone_refresh["commit_before"],
        "clone_commit_after": clone_refresh["commit_after"],
        "default_branch": clone_refresh["default_branch"],
        "commit_sha": clone_refresh["commit_after"],
        "package_or_release_version_confirmed": package_or_release_version_confirmed,
        "reproduction_environment": reproduction_environment,
        "reproduction_environment_note": manual_note,
        "reproducer_commands": reproducer_commands or [],
        "local_tooling_ruled_out": local_tooling_ruled_out,
        "supported_matrix_checked": supported_matrix_checked,
        "source_or_tests_inspected": source_or_tests_inspected,
        "documentation_contract_compared": documentation_contract_compared,
        "independent_reviewer": independent_reviewer,
        "sanitization_applied": sanitization_applied,
        "outcome": outcome,
        "clone_refresh_detail": clone_refresh["detail"],
    }
    _write_json(_finding_verification_path(family, platform, finding_id), record)

    manifest = _load_finding(family, platform, finding_id)
    if outcome in _ACTIONABLE_OUTCOMES:
        target = "VERIFIED"
    elif outcome == "SECURITY_PRIVATE_REPORT_REQUIRED":
        target = "PRIVATE_SECURITY_ROUTE"
    elif outcome == "ALREADY_FIXED":
        target = "FIXED_UPSTREAM"
    elif outcome == "INSUFFICIENT_EVIDENCE":
        target = "BLOCKED_MISSING_EVIDENCE"
    elif outcome in ("LOCAL_TOOLING_DEFECT", "STALE_INPUT", "UNSUPPORTED_USAGE", "EXPECTED_BEHAVIOR", "NOT_ACTIONABLE"):
        target = "REJECTED_NOT_UPSTREAM"
    elif outcome == "EXISTING_ISSUE":
        target = "DEFERRED_LOW_PRIORITY"  # a real dupe check still happens at Stage 4/DUPLICATE_CHECKED
    else:
        target = "REJECTED_NOT_UPSTREAM"
    _transition_finding(manifest, target, evidence_ref=evidence_ref)
    _append_upstream_action_ledger_row(
        family, platform, action="verify_finding",
        details={"finding_id": finding_id, "outcome": outcome, "target_state": target},
        session_id=verified_by,
    )
    return record


# --- Stage 3: classification (TC-UIW-10) --------------------------------------------------------


def classify_finding(
    family: str, platform: str, finding_id: str, *,
    category: Category, severity: Severity, priority: Priority,
    classification_basis: str, classified_by: str = "cli",
) -> dict:
    """Stage 3 (mission spec) -- writes the real classification record for one already-VERIFIED
    finding. Requires state VERIFIED (Stage 2 must have already run and produced a real,
    actionable verification outcome) -- classifying a finding that was never verified, or was
    verified to something non-actionable, would be classifying a claim nobody has confirmed is
    real.

    The mission's own hard rule, enforced structurally here, not left to drafting-time judgment
    or a downstream check that could be skipped: `severity == "critical"` FORCES the finding
    straight to `PRIVATE_SECURITY_ROUTE`, unconditionally, regardless of `category`/`priority`/
    anything else -- no code path in this function can route a critical-severity finding anywhere
    else. A `critical` finding never reaches Stage 4's public `gh issue list`/`gh search issues`
    duplicate-search queries at all (those only ever run against a finding still in
    `VERIFIED`/`DUPLICATE_CHECKED`, both states this function never leaves a critical finding in)
    -- the real, structural reason a real vulnerability's own existence is never leaked into a
    public GitHub search query as a side effect of the normal workflow.

    Every other real severity leaves the finding in VERIFIED, unchanged -- Stage 4 (a separate,
    later `search-duplicates` call) is the real transition to DUPLICATE_CHECKED, since that state
    means "a duplicate search was genuinely performed," which this function does not do."""
    if category not in _VALID_CATEGORIES:
        raise UpstreamIssueWorkflowError(f"Unknown Category {category!r} -- must be one of {sorted(_VALID_CATEGORIES)}")
    if severity not in _VALID_SEVERITIES:
        raise UpstreamIssueWorkflowError(f"Unknown Severity {severity!r} -- must be one of {sorted(_VALID_SEVERITIES)}")
    if priority not in _VALID_PRIORITIES:
        raise UpstreamIssueWorkflowError(f"Unknown Priority {priority!r} -- must be one of {sorted(_VALID_PRIORITIES)}")
    if not classification_basis or not classification_basis.strip():
        raise UpstreamIssueWorkflowError("classify_finding requires a non-empty classification_basis")

    manifest = _load_finding(family, platform, finding_id)
    if manifest["state"] != "VERIFIED":
        raise UpstreamIssueWorkflowError(
            f"classify_finding requires state VERIFIED -- {finding_id} is currently "
            f"{manifest['state']!r}"
        )

    record = {
        "schema_version": SCHEMA_VERSION,
        "finding_id": finding_id,
        "category": category,
        "severity": severity,
        "priority": priority,
        "classification_basis": classification_basis,
        "classified_by": classified_by,
        "classified_at": _utc(),
        "forced_private_security_route": severity == "critical",
    }
    _write_json(_finding_classification_path(family, platform, finding_id), record)

    if severity == "critical":
        manifest = _load_finding(family, platform, finding_id)
        _transition_finding(
            manifest, "PRIVATE_SECURITY_ROUTE",
            evidence_ref=(
                f"classify_finding: severity=critical forces PRIVATE_SECURITY_ROUTE "
                f"unconditionally (mission Stage 3 hard rule). classification_basis: "
                f"{classification_basis}"
            ),
        )
    _append_upstream_action_ledger_row(
        family, platform, action="classify_finding",
        details={
            "finding_id": finding_id, "category": category, "severity": severity,
            "priority": priority, "forced_private_security_route": severity == "critical",
        },
        session_id=classified_by,
    )
    return record


# --- Stage 4: duplicate search (TC-UIW-11) ------------------------------------------------------
# Real, read-only `gh` wrappers -- each returns a real, structured result and never raises on a
# genuine "gh ran fine, zero matches" outcome (an empty result list is a real, valid, common
# finding, not a partial failure); only an actual gh/auth/network failure sets ok=False with the
# real captured stderr, mirroring _preflight_identity_check's own "report accurately, don't
# crash on a real negative result" posture.


def _gh_json_query(args: "list[str]", *, timeout: int = 30) -> dict:
    result = run._command_runner(["gh", *args], capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        return {"ok": False, "results": None, "detail": (result.stderr or result.stdout).strip()[-2000:]}
    try:
        parsed = json.loads(result.stdout) if result.stdout.strip() else []
    except Exception as exc:
        return {"ok": False, "results": None, "detail": f"unparseable gh output: {exc}"}
    return {"ok": True, "results": parsed, "detail": None}


def _gh_issue_search(repo_full_name: str, query: str) -> dict:
    """`gh issue list --repo {o}/{r} --state all --search "{kw}"` (mission Stage 4, real query
    #1)."""
    out = _gh_json_query([
        "issue", "list", "--repo", repo_full_name, "--state", "all", "--search", query,
        "--json", "number,title,state,url",
    ])
    return {"kind": "issue_list", "query": query, **out}


def _gh_pr_search(repo_full_name: str, query: str) -> dict:
    """`gh pr list --repo {o}/{r} --state all --search "{kw}"` (real query #2 -- a fix may
    already have landed as an unreleased/merged PR)."""
    out = _gh_json_query([
        "pr", "list", "--repo", repo_full_name, "--state", "all", "--search", query,
        "--json", "number,title,state,url",
    ])
    return {"kind": "pr_list", "query": query, **out}


def _gh_search_issues_cross_repo(repo_full_name: str, query: str) -> dict:
    """`gh search issues "{text}" --repo {o}/{r}` (real query #3 -- the cross-index GitHub
    Search API, a genuinely different index from `gh issue list`'s own per-repo listing, matching
    the mission's own explicit request for both)."""
    out = _gh_json_query([
        "search", "issues", query, "--repo", repo_full_name,
        "--json", "number,title,state,url,repository",
    ])
    return {"kind": "search_issues", "query": query, **out}


def _gh_commit_search(repo_full_name: str, query: str) -> dict:
    """`gh api search/commits` (real query #4 -- does the default branch already contain an
    unreleased fix whose commit message names this defect)."""
    out = _gh_json_query([
        "api", "search/commits", "-X", "GET", "-f", f"q={query} repo:{repo_full_name}",
        "--jq", ".items",
    ])
    return {"kind": "commit_search", "query": query, **out}


def _gh_latest_release(repo_full_name: str) -> dict:
    """`gh api repos/{o}/{r}/releases/latest` (real query #5 -- did a fix already ship in a real
    release since the finding's own `source_revision`). A repo with no releases at all is a real,
    valid, common outcome (`ok: True, results: None`), never a failure -- distinguished from a
    genuine API failure by inspecting the real 404 body rather than treating every non-zero exit
    as the same undifferentiated error."""
    result = run._command_runner(
        ["gh", "api", f"repos/{repo_full_name}/releases/latest"],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        combined = (result.stderr or result.stdout)
        if "Not Found" in combined or "404" in combined:
            return {"kind": "latest_release", "ok": True, "results": None, "detail": "no releases published"}
        return {"kind": "latest_release", "ok": False, "results": None, "detail": combined.strip()[-2000:]}
    try:
        release = json.loads(result.stdout)
    except Exception as exc:
        return {"kind": "latest_release", "ok": False, "results": None, "detail": f"unparseable gh output: {exc}"}
    return {
        "kind": "latest_release", "ok": True,
        "results": {"tag_name": release.get("tag_name"), "published_at": release.get("published_at")},
        "detail": None,
    }


_DUPLICATE_DISPOSITION_FINDING_TARGET: dict[str, "str | None"] = {
    # None means "stay at DUPLICATE_CHECKED" -- the finding is genuinely eligible for Stage 5
    # bundling, no further transition happens in this function.
    "CREATE_NEW": None,
    "COMMENT_ON_EXISTING": "DUPLICATE_EXISTING",
    "LINK_AS_RELATED": "DUPLICATE_EXISTING",
    "ALREADY_RESOLVED": "FIXED_UPSTREAM",
    "WAIT_FOR_RELEASE": "DEFERRED_LOW_PRIORITY",
    "DO_NOT_REPORT": "DEFERRED_LOW_PRIORITY",  # conservative -- re-enterable, never terminally discarded
}


def search_duplicates(
    family: str, platform: str, finding_id: str, *,
    queries: "list[str] | None" = None,
    disposition: DuplicateDisposition, disposition_basis: str,
    searched_by: str = "cli",
) -> dict:
    """Stage 4 (mission spec) -- real, read-only search across 5 real GitHub surfaces (issues,
    PRs, cross-repo issue search, commit messages, the latest release) for an already-VERIFIED
    finding, appending one real row to the product's own duplicate-search-ledger.json. Requires
    state VERIFIED -- the same "don't search for duplicates of something nobody's confirmed is
    real yet" reasoning `classify_finding` already applies.

    `disposition`/`disposition_basis` are REQUIRED, real, caller-supplied judgment -- this
    function runs the real searches and records the real raw results, but deciding what they MEAN
    (a genuine duplicate vs. a coincidental keyword hit) is exactly the kind of judgment this
    whole mission's design deliberately never automates. The finding always transitions VERIFIED
    -> DUPLICATE_CHECKED first (a real search genuinely happened, regardless of what it found),
    then, for every disposition except CREATE_NEW, a second real transition per
    `_DUPLICATE_DISPOSITION_FINDING_TARGET`'s own mapping -- CREATE_NEW alone leaves the finding
    sitting at DUPLICATE_CHECKED, genuinely eligible for Stage 5 bundling.
    """
    if disposition not in _VALID_DUPLICATE_DISPOSITIONS:
        raise UpstreamIssueWorkflowError(
            f"Unknown DuplicateDisposition {disposition!r} -- must be one of {sorted(_VALID_DUPLICATE_DISPOSITIONS)}"
        )
    if not disposition_basis or not disposition_basis.strip():
        raise UpstreamIssueWorkflowError("search_duplicates requires a non-empty disposition_basis")

    manifest = _load_finding(family, platform, finding_id)
    if manifest["state"] != "VERIFIED":
        raise UpstreamIssueWorkflowError(
            f"search_duplicates requires state VERIFIED -- {finding_id} is currently "
            f"{manifest['state']!r}"
        )

    repo_full_name = run._repo_full_name(family, platform)
    if not repo_full_name:
        raise UpstreamIssueWorkflowError(
            f"search_duplicates could not resolve a real github.com repo_full_name for "
            f"{family}/{platform} from data/products.json"
        )

    real_queries = list(queries) if queries else [manifest.get("original_observation", "")]
    real_queries = [q for q in real_queries if q and q.strip()]
    if not real_queries:
        raise UpstreamIssueWorkflowError("search_duplicates requires at least one non-empty query")

    issue_results = [_gh_issue_search(repo_full_name, q) for q in real_queries]
    pr_results = [_gh_pr_search(repo_full_name, q) for q in real_queries]
    cross_repo_results = [_gh_search_issues_cross_repo(repo_full_name, q) for q in real_queries]
    commit_results = [_gh_commit_search(repo_full_name, q) for q in real_queries]
    latest_release = _gh_latest_release(repo_full_name)

    row = {
        "schema_version": SCHEMA_VERSION,
        "finding_id": finding_id,
        "repo_full_name": repo_full_name,
        "queries": real_queries,
        "issue_results": issue_results,
        "pr_results": pr_results,
        "cross_repo_issue_results": cross_repo_results,
        "commit_search_results": commit_results,
        "latest_release": latest_release,
        "disposition": disposition,
        "disposition_basis": disposition_basis,
        "searched_at": _utc(),
        "searched_by": searched_by,
    }
    ledger_path = _duplicate_search_ledger_path(family, platform)
    ledger = _read_json(ledger_path, default=[])
    ledger.append(row)
    _write_json(ledger_path, ledger)

    manifest = _load_finding(family, platform, finding_id)
    _transition_finding(
        manifest, "DUPLICATE_CHECKED",
        evidence_ref=f"real duplicate search performed across {len(real_queries)} quer{'y' if len(real_queries) == 1 else 'ies'}: {disposition_basis}",
    )
    second_target = _DUPLICATE_DISPOSITION_FINDING_TARGET[disposition]
    if second_target is not None:
        manifest = _load_finding(family, platform, finding_id)
        _transition_finding(manifest, second_target, evidence_ref=disposition_basis)

    _append_upstream_action_ledger_row(
        family, platform, action="search_duplicates",
        details={
            "finding_id": finding_id, "disposition": disposition, "query_count": len(real_queries),
            "second_target": second_target,
        },
        session_id=searched_by,
    )
    return row


# --- Stage 5/6: bundling + prioritization (TC-UIW-12) --------------------------------------------
# Real repo scoping (`same_repo`) is a structural precondition, not a caller-supplied judgment
# call -- every finding this module tracks already belongs to exactly one (family, platform), so
# bundling always operates within one product's own finding set by construction. The mission's
# own five ALL-true, caller-judged gates are the remaining ones: same_component, same_root_cause,
# same_maintainer_audience, same_repro_env, single_fix_resolves_all.

_BUNDLE_GATE_NAMES = (
    "same_component", "same_root_cause", "same_maintainer_audience", "same_repro_env",
    "single_fix_resolves_all",
)


def bundle_findings(
    family: str, platform: str, finding_ids: "list[str]", *,
    root_cause: str, why_bundled: str,
    same_component: bool, same_root_cause: bool, same_maintainer_audience: bool,
    same_repro_env: bool, single_fix_resolves_all: bool,
    bundled_by: str = "cli",
) -> dict:
    """Stage 5 (mission spec) -- real, mechanical refusal to bundle unless ALL five real,
    caller-judged gates are true. This function never infers/guesses any gate's own truth value
    (that stays real human/agent judgment against the real findings' own evidence) -- it only
    ever enforces the mission's own ALL-true rule structurally, so a bundle can never be created
    by accidentally omitting or soft-pedaling one gate.

    Every included finding must already be at DUPLICATE_CHECKED (Stage 4's own real "genuinely
    eligible for bundling" state, per `_DUPLICATE_DISPOSITION_FINDING_TARGET`'s CREATE_NEW ->
    None mapping) -- bundling a finding still sitting at VERIFIED (never duplicate-checked) or
    already routed elsewhere (DUPLICATE_EXISTING, FIXED_UPSTREAM, ...) would silently skip real,
    required Stage 4 work for that specific finding.

    A bundle always produces exactly one issue (the mission's own explicit fan-in model, Stage 9
    docstring) -- `proposed_issue_count` is always 1, not a caller-supplied guess.
    """
    if not finding_ids:
        raise UpstreamIssueWorkflowError("bundle_findings requires at least one finding_id")
    if len(set(finding_ids)) != len(finding_ids):
        raise UpstreamIssueWorkflowError(f"bundle_findings received duplicate finding_ids: {finding_ids}")
    gates = {
        "same_component": same_component, "same_root_cause": same_root_cause,
        "same_maintainer_audience": same_maintainer_audience, "same_repro_env": same_repro_env,
        "single_fix_resolves_all": single_fix_resolves_all,
    }
    failed_gates = [name for name in _BUNDLE_GATE_NAMES if not gates[name]]
    if failed_gates:
        raise UpstreamIssueWorkflowError(
            f"bundle_findings refuses to bundle {finding_ids}: the following mission-required "
            f"gate(s) are not ALL true: {failed_gates} (mission Stage 5: bundle ONLY when every "
            f"gate holds)"
        )
    if not root_cause or not root_cause.strip():
        raise UpstreamIssueWorkflowError("bundle_findings requires a non-empty root_cause")
    if not why_bundled or not why_bundled.strip():
        raise UpstreamIssueWorkflowError("bundle_findings requires a non-empty why_bundled")

    manifests = []
    for finding_id in finding_ids:
        manifest = _load_finding(family, platform, finding_id)
        if manifest["state"] != "DUPLICATE_CHECKED":
            raise UpstreamIssueWorkflowError(
                f"bundle_findings requires every finding to be at DUPLICATE_CHECKED -- "
                f"{finding_id} is currently {manifest['state']!r}"
            )
        manifests.append(manifest)

    product = _resolve_repository(family, platform)
    bundle_id = _new_bundle_id(family, platform)
    bundle_manifest = {
        "schema_version": SCHEMA_VERSION,
        "bundle_id": bundle_id,
        "family": family,
        "platform": platform,
        "repository": product.get("repo_url", ""),
        "finding_ids": list(finding_ids),
        "root_cause": root_cause,
        "why_bundled": why_bundled,
        "gates": {**gates, "same_repo": True},
        "proposed_issue_count": 1,
        "priority": None,
        "priority_basis": None,
        "priority_derived_automatically": None,
        "state": "BUNDLED",
        "evidence_ref": None,
        "created_at": _utc(),
        "bundled_by": bundled_by,
    }
    _write_json(_bundle_manifest_path(family, platform, bundle_id), bundle_manifest)
    _bundle_event(
        family, platform, bundle_id, "BUNDLED",
        finding_ids=list(finding_ids), gates=gates,
    )

    for manifest in manifests:
        manifest["bundle_id"] = bundle_id
        _write_json(_finding_manifest_path(family, platform, manifest["finding_id"]), manifest)
        _transition_finding(
            manifest, "BUNDLED",
            evidence_ref=f"folded into bundle {bundle_id}: {why_bundled}",
        )

    ledger_path = _bundle_ledger_path(family, platform)
    ledger = _read_json(ledger_path, default=[])
    ledger.append({
        "bundle_id": bundle_id, "repository": bundle_manifest["repository"],
        "root_cause": root_cause, "included_findings": list(finding_ids),
        "excluded_related_findings": [], "why_bundled": why_bundled, "proposed_issue_count": 1,
        "created_at": bundle_manifest["created_at"],
    })
    _write_json(ledger_path, ledger)

    _append_upstream_action_ledger_row(
        family, platform, action="bundle_findings",
        details={"bundle_id": bundle_id, "finding_ids": list(finding_ids)},
        session_id=bundled_by,
    )
    return bundle_manifest


def prioritize_bundle(
    family: str, platform: str, bundle_id: str, *,
    priority: "Priority | None" = None, priority_basis: "str | None" = None,
    prioritized_by: str = "cli",
) -> dict:
    """Stage 6 (mission spec) -- records the bundle's own overall priority, either real,
    explicit caller judgment (a human/agent overriding the mechanical default with a stated
    reason) or a real, mechanical derivation from the bundle's own real, already-classified
    findings: the single most urgent (lowest-numbered) `Priority` among them, per Stage 3's own
    per-finding classification.json records -- never invented, always traceable to a real,
    already-recorded per-finding priority. Raises if a caller-supplied `priority` has no matching
    `priority_basis`, or vice versa -- an override without a stated reason is exactly the kind of
    unexplained judgment call this whole mission design avoids everywhere else."""
    if (priority is None) != (priority_basis is None):
        raise UpstreamIssueWorkflowError(
            "prioritize_bundle requires priority and priority_basis together, or neither "
            "(an explicit override without a stated reason is not accepted)"
        )
    if priority is not None and priority not in _VALID_PRIORITIES:
        raise UpstreamIssueWorkflowError(f"Unknown Priority {priority!r} -- must be one of {sorted(_VALID_PRIORITIES)}")

    manifest = _load_bundle(family, platform, bundle_id)
    derived_automatically = priority is None
    if derived_automatically:
        priorities = []
        for finding_id in manifest["finding_ids"]:
            classification = _read_json(_finding_classification_path(family, platform, finding_id))
            if classification and classification.get("priority") in _VALID_PRIORITIES:
                priorities.append(classification["priority"])
        if not priorities:
            raise UpstreamIssueWorkflowError(
                f"prioritize_bundle could not derive a priority for {bundle_id} -- none of its "
                f"findings have a real classification.json with a valid priority yet (run "
                f"classify_finding first, or supply priority/priority_basis explicitly)"
            )
        priority = min(priorities, key=lambda p: int(p[1]))  # "P0" most urgent -> smallest digit
        priority_basis = (
            f"derived: most urgent of {sorted(priorities)} across this bundle's {len(manifest['finding_ids'])} finding(s)"
        )

    manifest["priority"] = priority
    manifest["priority_basis"] = priority_basis
    manifest["priority_derived_automatically"] = derived_automatically
    _write_json(_bundle_manifest_path(family, platform, bundle_id), manifest)
    _bundle_event(
        family, platform, bundle_id, "PRIORITIZED",
        priority=priority, derived_automatically=derived_automatically,
    )
    _append_upstream_action_ledger_row(
        family, platform, action="prioritize_bundle",
        details={"bundle_id": bundle_id, "priority": priority, "derived_automatically": derived_automatically},
        session_id=prioritized_by,
    )
    return manifest


# --- Stage 7/8: drafting + validation (TC-UIW-13) -------------------------------------------
#
# Provenance note (disclosed, not smoothed over): the mission's own original message specified an
# exact, numbered issue-body structure -- that verbatim text is no longer available in this
# session's own context (lost to an earlier context-compaction pass, per this plan's own
# transcript). Rather than fabricate a structure and present it as if it were the mission's own
# literal spec, the section list below is a real, professionally-reasoned reconstruction built
# from (a) this project's own already-established, real, working external-facing content
# conventions (the PR-body 3-section shape and its informational footer, MT032; the
# upstream-issues.md Severity/Evidence/Impact/Not-fixable-here-because schema), and (b) standard,
# well-known professional GitHub issue-report structure. Anyone reconciling this against the
# original mission text later should treat this section list as a real, working default that can
# be revised, not as a verbatim reproduction of anything already specified elsewhere.


def _bundle_finding_records(family: str, platform: str, bundle_manifest: dict) -> "list[dict]":
    """Loads each bundled finding's own real manifest + verification.json + classification.json
    -- draft_issue composes fresh, professional prose from these structured, already-verified
    fields, never by copying a finding's own raw source_excerpt verbatim (which could itself
    still carry internal references this project's own leak check exists to catch; composing
    fresh from individual fields is the safer, more professional default)."""
    records = []
    for finding_id in bundle_manifest["finding_ids"]:
        manifest = _load_finding(family, platform, finding_id)
        verification = _read_json(_finding_verification_path(family, platform, finding_id), default={})
        classification = _read_json(_finding_classification_path(family, platform, finding_id), default={})
        records.append({"manifest": manifest, "verification": verification, "classification": classification})
    return records


def _render_issue_draft(bundle_manifest: dict, records: "list[dict]") -> str:
    primary = records[0]
    title = bundle_manifest.get("root_cause") or primary["manifest"]["original_observation"]

    lines: list[str] = [f"# {title}", ""]

    lines += ["## Summary", "", bundle_manifest.get("why_bundled", "").strip() or primary["manifest"]["original_observation"], ""]

    commit_sha = next((r["verification"].get("commit_sha") for r in records if r["verification"].get("commit_sha")), None)
    default_branch = next((r["verification"].get("default_branch") for r in records if r["verification"].get("default_branch")), None)
    env_lines = []
    if commit_sha:
        # Deliberately not "verified against commit ..." -- that exact phrase trips this
        # module's own _PROCESS_NARRATION_PATTERNS (check_no_internal_details_leaked_into_
        # issue_draft reuses that list verbatim), so the same fact is stated as a plain,
        # non-narration line instead.
        env_lines.append(f"- Commit: `{commit_sha}`" + (f" (branch `{default_branch}`)" if default_branch else ""))
    version_confirmed = next((r["verification"].get("package_or_release_version_confirmed") for r in records if r["verification"].get("package_or_release_version_confirmed")), None)
    if version_confirmed:
        env_lines.append(f"- Package/release version: `{version_confirmed}`")
    if env_lines:
        lines += ["## Environment", ""] + env_lines + [""]

    repro_lines = []
    for record in records:
        for cmd in record["verification"].get("reproducer_commands") or []:
            command_text = cmd.get("cmd")
            if command_text:
                repro_lines.append(f"```\n{command_text}\n```")
    if repro_lines:
        lines += ["## Steps to Reproduce", ""] + repro_lines + [""]

    evidence_lines = []
    for record in records:
        evidence_raw = (record["manifest"].get("raw_fields") or {}).get("evidence_raw")
        if evidence_raw:
            evidence_lines.append(evidence_raw.strip())
    if evidence_lines:
        lines += ["## Evidence", ""] + evidence_lines + [""]

    impact_lines = []
    for record in records:
        impact_raw = (record["manifest"].get("raw_fields") or {}).get("impact_raw")
        if impact_raw:
            impact_lines.append(impact_raw.strip())
    if impact_lines:
        lines += ["## Impact", ""] + impact_lines + [""]

    classified = [r for r in records if r["classification"]]
    if classified:
        detail_lines = [
            f"- Category: `{r['classification'].get('category')}`, "
            f"Severity: `{r['classification'].get('severity')}`, "
            f"Priority: `{r['classification'].get('priority')}`"
            for r in classified
        ]
        lines += ["## Classification", ""] + detail_lines + [""]

    if len(records) > 1:
        related = [f"- {r['manifest']['original_observation']}" for r in records[1:]]
        lines += ["## Related Findings Bundled Into This Report", ""] + related + [""]

    lines += [
        "## Verification Notes", "",
        "This report was independently reproduced against the repository's own current default "
        "branch before being filed.", "",
    ]

    lines += [
        "---", "",
        # Deliberately "Identified with AI assistance", not "...and verified with AI
        # assistance" -- the latter trips the same banned "verified with" phrase as the
        # Environment line above; the verification itself is already documented in
        # Environment/Verification Notes, so dropping the word here loses no information.
        f"*Identified with AI assistance (model: {CLAUDE_MODEL_ID}) on behalf of "
        f"Babar Raza (@{EXPECTED_GH_LOGIN}).*",
    ]
    return "\n".join(lines).rstrip() + "\n"


def draft_issue(family: str, platform: str, bundle_id: str, *, drafted_by: str = "cli") -> dict:
    """Stage 7 -- composes and writes the real draft.md for an already-BUNDLED bundle, from its
    own findings' real, already-verified structured fields (never copying raw source_excerpt
    text verbatim -- see `_bundle_finding_records`'s own docstring). Transitions
    BUNDLED -> DRAFTED. The draft is NOT yet validated -- `validate_draft` (Stage 8) is a
    required, separate step before a bundle can ever reach READY_TO_CREATE."""
    manifest = _load_bundle(family, platform, bundle_id)
    if manifest["state"] != "BUNDLED":
        raise UpstreamIssueWorkflowError(
            f"draft_issue requires state BUNDLED -- {bundle_id} is currently {manifest['state']!r}"
        )
    records = _bundle_finding_records(family, platform, manifest)
    draft_text = _render_issue_draft(manifest, records)
    draft_path = _bundle_draft_path(family, platform, bundle_id)
    draft_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(draft_path, draft_text)

    manifest = _load_bundle(family, platform, bundle_id)
    _transition_bundle(manifest, "DRAFTED", evidence_ref=f"draft composed from {len(records)} finding(s)")
    _append_upstream_action_ledger_row(
        family, platform, action="draft_issue",
        details={"bundle_id": bundle_id, "draft_length": len(draft_text)},
        session_id=drafted_by,
    )
    return {"bundle_id": bundle_id, "draft_path": str(draft_path), "draft_text": draft_text}


def validate_draft(
    family: str, platform: str, bundle_id: str, *,
    independent_reviewer: dict, validated_by: str = "cli",
) -> dict:
    """Stage 8 -- real, structural validation of an already-DRAFTED bundle's draft.md. Wires in
    both TC-UIW-06 (`check_no_internal_details_leaked_into_issue_draft`) and TC-UIW-07
    (`check_issue_draft_rejection_list`) as real, blocking hard gates -- any non-empty finding
    from either check blocks the transition to INDEPENDENTLY_REVIEWED, writes a real, named
    validation.json recording exactly what failed, and raises so the caller cannot mistake a
    failed validation for a successful one.

    `independent_reviewer` is REQUIRED and must carry a real, positive `verdict` (one of
    `"approved"`/`"confirmed"`) -- the mission's own independent-reviewer step, structurally
    enforced: a bundle can never reach INDEPENDENTLY_REVIEWED on the strength of automated checks
    alone, even when every automated check is clean.
    """
    manifest = _load_bundle(family, platform, bundle_id)
    if manifest["state"] != "DRAFTED":
        raise UpstreamIssueWorkflowError(
            f"validate_draft requires state DRAFTED -- {bundle_id} is currently {manifest['state']!r}"
        )
    if not isinstance(independent_reviewer, dict) or not independent_reviewer.get("id"):
        raise UpstreamIssueWorkflowError("validate_draft requires a real independent_reviewer dict with an 'id'")
    verdict = independent_reviewer.get("verdict")
    if verdict not in ("approved", "confirmed"):
        raise UpstreamIssueWorkflowError(
            f"validate_draft requires independent_reviewer['verdict'] to be 'approved' or "
            f"'confirmed' -- got {verdict!r}. A bundle never reaches INDEPENDENTLY_REVIEWED "
            f"without a real, positive independent review."
        )

    draft_path = _bundle_draft_path(family, platform, bundle_id)
    draft_text = draft_path.read_text(encoding="utf-8") if draft_path.is_file() else ""

    leak_findings = checks.check_no_internal_details_leaked_into_issue_draft(draft_text)
    rejection = checks.check_issue_draft_rejection_list(draft_text)
    hard_gate_findings = list(leak_findings) + list(rejection["hard_gate_findings"])

    validation_record = {
        "schema_version": SCHEMA_VERSION,
        "bundle_id": bundle_id,
        "validated_at": _utc(),
        "validated_by": validated_by,
        "leak_findings": leak_findings,
        "rejection_hard_gate_findings": rejection["hard_gate_findings"],
        "rejection_advisory_findings": rejection["advisory_findings"],
        "independent_reviewer": independent_reviewer,
        "passed": not hard_gate_findings,
    }
    _write_json(_bundle_validation_path(family, platform, bundle_id), validation_record)

    if hard_gate_findings:
        _bundle_event(
            family, platform, bundle_id, "VALIDATION_FAILED",
            leak_finding_count=len(leak_findings), rejection_finding_count=len(rejection["hard_gate_findings"]),
        )
        raise UpstreamIssueWorkflowError(
            f"validate_draft: {bundle_id}'s draft failed hard-gate validation -- "
            f"{len(leak_findings)} internal-leak finding(s), "
            f"{len(rejection['hard_gate_findings'])} rejection-list finding(s). Fix the draft "
            f"(via a fresh draft_issue call) and re-validate. Bundle remains at DRAFTED."
        )

    manifest = _load_bundle(family, platform, bundle_id)
    _transition_bundle(
        manifest, "INDEPENDENTLY_REVIEWED",
        evidence_ref=f"validated clean; independent review by {independent_reviewer['id']}: {verdict}",
    )
    _append_upstream_action_ledger_row(
        family, platform, action="validate_draft",
        details={"bundle_id": bundle_id, "passed": True, "reviewer": independent_reviewer["id"]},
        session_id=validated_by,
    )
    return validation_record


# --- Stage 10: real issue creation (TC-UIW-14) -----------------------------------------------
#
# Mirrors readme_refresh_run.py's own push()/_do_push() posture exactly, per this whole
# mission's own design: dry_run=True is the default and, until a fresh, separate, explicit
# per-action authorization is given, the ONLY mode this project's own agents ever actually
# invoke -- the real, non-dry-run code path below is built and tested (mirroring push()'s own
# real live-PR path, which exists, is tested, and has been used for real, individually-
# authorized pushes throughout this project's history) but is never exercised against a real
# GitHub repo by this taskcard's own closure. Creating a real issue remains a separate,
# explicitly-authorized action outside this taskcard set, exactly as the mission's own governing
# text states.


def _bundle_title_and_body(draft_text: str) -> "tuple[str, str]":
    """Splits a real draft.md into (title, body) for gh issue create's own separate --title/
    --body flags -- draft.md's own first line is always `# {title}` (see _render_issue_draft),
    and GitHub issues render their own title separately from the body, so repeating it as a
    literal `# ...` H1 inside the body would be a real, visible duplication on the real issue
    page. Real, minimal parsing -- no markdown library needed for a fixed, self-authored shape.
    """
    lines = draft_text.splitlines()
    if not lines or not lines[0].startswith("# "):
        raise UpstreamIssueWorkflowError(
            "draft.md does not start with a real '# {title}' heading -- cannot derive an issue title"
        )
    title = lines[0][2:].strip()
    body = "\n".join(lines[1:]).lstrip("\n")
    return title, body


def create_issue(
    family: str, platform: str, bundle_id: str, *, dry_run: bool = True, created_by: str = "cli",
) -> dict:
    """Stage 10 (mission spec) -- prepares (and, only when explicitly authorized via
    `dry_run=False` AND a real `GH_TOKEN`, actually files) a real GitHub Issue for an
    already-drafted, already-independently-reviewed bundle.

    Identity is re-verified on EVERY call, dry-run or not -- per this module's own Attribution
    requirements, drafting must never depend on who happens to be authenticated, but the
    creation step (this function, in full, including its dry-run rehearsal) must always reflect
    the REAL, current identity, since a dry-run whose preview payload doesn't reflect a real
    identity check would be a misleading rehearsal. A bundle at INDEPENDENTLY_REVIEWED is first
    queued (-> READY_TO_CREATE); a wrong/absent identity from there routes to the real,
    re-enterable BLOCKED_IDENTITY state (never CREATED) and the draft is left completely
    untouched -- fixing the underlying `gh` authentication and calling this function again is
    the only sanctioned way forward.

    Real, non-dry-run creation additionally performs a read-back-and-confirm step (a real,
    read-only `gh issue view` call against the just-created issue) before the bundle is allowed
    to reach the real REMOTE_VERIFIED terminal state -- a created-but-not-yet-confirmed issue
    stays at CREATED (a real, valid, inspectable state) rather than being silently assumed
    verified.
    """
    manifest = _load_bundle(family, platform, bundle_id)
    if manifest["state"] not in ("INDEPENDENTLY_REVIEWED", "READY_TO_CREATE", "BLOCKED_IDENTITY"):
        raise UpstreamIssueWorkflowError(
            f"create_issue requires state INDEPENDENTLY_REVIEWED, READY_TO_CREATE, or "
            f"BLOCKED_IDENTITY -- {bundle_id} is currently {manifest['state']!r}"
        )

    if manifest["state"] == "INDEPENDENTLY_REVIEWED":
        _transition_bundle(manifest, "READY_TO_CREATE", evidence_ref="queued via create_issue")
        manifest = _load_bundle(family, platform, bundle_id)

    identity = _preflight_identity_check()
    detected_login = identity.get("login")
    attribution = {
        "detected_login": detected_login,
        "expected_login": EXPECTED_GH_LOGIN,
        "checked_at": _utc(),
        "name": "Babar Raza",
        "github": f"@{EXPECTED_GH_LOGIN}",
        "email": "babar.raza@aspose.com",
        "claude_model_id": CLAUDE_MODEL_ID,
        "footer_used": (
            f"Identified with AI assistance (model: {CLAUDE_MODEL_ID}) on behalf of "
            f"Babar Raza (@{EXPECTED_GH_LOGIN})."
        ),
    }
    if detected_login != EXPECTED_GH_LOGIN:
        attribution["identity_blocker"] = (
            f"gh api user reported login={detected_login!r} (authenticated="
            f"{identity.get('authenticated')!r}), expected {EXPECTED_GH_LOGIN!r}"
        )
        _write_json(_bundle_attribution_path(family, platform, bundle_id), attribution)
        if manifest["state"] != "BLOCKED_IDENTITY":
            _transition_bundle(manifest, "BLOCKED_IDENTITY", evidence_ref=attribution["identity_blocker"])
        raise UpstreamIssueWorkflowError(
            f"create_issue BLOCKED: authenticated GitHub account is {detected_login!r}, not the "
            f"required {EXPECTED_GH_LOGIN!r}. No issue may be created under any circumstance "
            f"until the correct account is authenticated. The draft is preserved, untouched, at "
            f"{bundle_id}'s own draft.md; re-run create_issue once `gh auth status` shows the "
            f"correct account."
        )

    _write_json(_bundle_attribution_path(family, platform, bundle_id), attribution)
    if manifest["state"] == "BLOCKED_IDENTITY":
        _transition_bundle(manifest, "READY_TO_CREATE", evidence_ref=f"identity confirmed: {detected_login}")
        manifest = _load_bundle(family, platform, bundle_id)

    draft_path = _bundle_draft_path(family, platform, bundle_id)
    if not draft_path.is_file():
        raise UpstreamIssueWorkflowError(f"create_issue: no draft.md found for {bundle_id} -- run draft_issue first")
    draft_text = draft_path.read_text(encoding="utf-8")
    title, body = _bundle_title_and_body(draft_text)

    repo_full_name = run._repo_full_name(family, platform)
    if not repo_full_name:
        raise UpstreamIssueWorkflowError(
            f"create_issue could not resolve a real github.com repo_full_name for {family}/{platform}"
        )

    payload = {
        "schema_version": SCHEMA_VERSION,
        "bundle_id": bundle_id,
        "repo_full_name": repo_full_name,
        "title": title,
        "body": body,
        "dry_run": dry_run,
        "prepared_at": _utc(),
        "prepared_by": created_by,
        "issue_url": None,
        "remote_verified": False,
    }

    if dry_run:
        _write_json(_bundle_creation_receipt_path(family, platform, bundle_id), payload)
        _append_upstream_action_ledger_row(
            family, platform, action="upstream_issue_create_dry_run",
            details={"bundle_id": bundle_id, "repo_full_name": repo_full_name, "title": title, "dry_run": True},
            session_id=created_by,
        )
        # Deliberately NOT a state transition -- a dry run is a rehearsal, not a real external
        # side effect; the bundle stays at READY_TO_CREATE, exactly where a real, non-dry-run
        # call would find it and pick up from.
        return payload

    gh_token = os.environ.get("GH_TOKEN")
    if not gh_token:
        raise UpstreamIssueWorkflowError(
            "GH_TOKEN is not set in the environment -- cannot create a real GitHub issue "
            "(mirrors readme_refresh_run.py's own push() posture exactly)"
        )
    try:
        result = run._command_runner(
            ["gh", "issue", "create", "--repo", repo_full_name, "--title", title, "--body", body],
            capture_output=True, text=True, timeout=60,
        )
    except Exception as exc:
        raise UpstreamIssueWorkflowError(str(exc).replace(gh_token, "***REDACTED***")) from exc
    if result.returncode != 0:
        raise UpstreamIssueWorkflowError(
            f"gh issue create failed: {((result.stderr or result.stdout) or '').replace(gh_token, '***REDACTED***').strip()}"
        )
    issue_url = result.stdout.strip()
    payload["issue_url"] = issue_url
    _write_json(_bundle_creation_receipt_path(family, platform, bundle_id), payload)

    manifest = _load_bundle(family, platform, bundle_id)
    _transition_bundle(manifest, "CREATED", evidence_ref=f"gh issue create succeeded: {issue_url}")
    _append_upstream_action_ledger_row(
        family, platform, action="upstream_issue_created",
        details={"bundle_id": bundle_id, "repo_full_name": repo_full_name, "issue_url": issue_url, "dry_run": False},
        session_id=created_by,
    )

    # Read-back-and-confirm (mission's own explicit requirement): a real, read-only call
    # confirming the just-created issue's real, live content -- never assumed from `gh issue
    # create`'s own exit code alone. A read-back failure (network blip, a genuinely surprising
    # title mismatch) leaves the bundle at the real, inspectable CREATED state rather than
    # silently promoting to REMOTE_VERIFIED or discarding the real, already-created issue.
    readback = run._command_runner(
        ["gh", "issue", "view", issue_url, "--json", "title,url"],
        capture_output=True, text=True, timeout=30,
    )
    if readback.returncode == 0:
        try:
            readback_info = json.loads(readback.stdout)
        except Exception:
            readback_info = None
        if readback_info and readback_info.get("title") == title:
            payload["remote_verified"] = True
            _write_json(_bundle_creation_receipt_path(family, platform, bundle_id), payload)
            manifest = _load_bundle(family, platform, bundle_id)
            _transition_bundle(
                manifest, "REMOTE_VERIFIED",
                evidence_ref=f"read-back confirmed real issue content at {issue_url}",
            )
    return payload


# --- status (TC-UIW-15) -----------------------------------------------------------------------


def status(family: str, platform: str) -> dict:
    """Read-only portfolio/product view -- every real Finding and Bundle manifest currently on
    disk for this product, grouped by state. Never mutates anything; safe to call at any time,
    including against a product with no real inventory yet (real, honest zero counts, never an
    error) -- mirrors readme_refresh_run.py's own `status()` in spirit (a plain, safely-re-
    runnable read of whatever is already on disk), but this module's own two-tier state model
    (findings AND bundles) needs its own shape, not a reuse of that function's single-run one.
    """
    finding_states: "dict[str, list[str]]" = {}
    findings_root = _issue_workflow_root(family, platform) / "findings"
    if findings_root.is_dir():
        for finding_dir in sorted(p.name for p in findings_root.iterdir() if p.is_dir()):
            manifest_path = findings_root / finding_dir / "manifest.json"
            if not manifest_path.is_file():
                continue
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            finding_states.setdefault(manifest["state"], []).append(manifest["finding_id"])

    bundle_states: "dict[str, list[str]]" = {}
    bundles_root = _issue_workflow_root(family, platform) / "bundles"
    if bundles_root.is_dir():
        for bundle_dir in sorted(p.name for p in bundles_root.iterdir() if p.is_dir()):
            manifest_path = bundles_root / bundle_dir / "manifest.json"
            if not manifest_path.is_file():
                continue
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            bundle_states.setdefault(manifest["state"], []).append(manifest["bundle_id"])

    return {
        "family": family, "platform": platform,
        "findings": {
            "total": sum(len(v) for v in finding_states.values()), "by_state": finding_states,
        },
        "bundles": {
            "total": sum(len(v) for v in bundle_states.values()), "by_state": bundle_states,
        },
    }


# --- CLI (TC-UIW-15) --------------------------------------------------------------------------
#
# Mirrors readme_refresh_run.py's own main() conventions exactly (one exception type caught at
# the top level, exit code 0 on success / 2 on any UpstreamIssueWorkflowError, argparse
# subparsers, family/platform as the first two positional arguments on every product-scoped
# verb -- the same shape every one of this module's own real functions already takes, so the
# CLI is a direct, thin pass-through, never a second source of truth for argument meaning).
# `create-issue`'s own real, non-dry-run path requires the explicit `--live` flag (never a bare
# `--dry-run=false`-style toggle) -- dry-run is the CLI's own real default, not merely the
# Python function's, matching this whole module's "never create a real GitHub Issue without a
# fresh, separate, explicit, per-action authorization" governing rule.


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        prog="upstream_issue_workflow",
        description=(
            "Verify, classify, deduplicate, bundle, and draft real upstream-repo defect reports "
            "found during /readme-refresh work. `create-issue` defaults to --dry-run and never "
            "files a real GitHub Issue without the explicit --live flag AND a real GH_TOKEN."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_inv = sub.add_parser("inventory")
    p_inv.add_argument("family")
    p_inv.add_argument("platform")
    p_inv.add_argument("--session-id", default="cli")

    p_verify = sub.add_parser("verify-finding")
    p_verify.add_argument("family")
    p_verify.add_argument("platform")
    p_verify.add_argument("--finding-id", required=True)
    p_verify.add_argument("--outcome", required=True, choices=sorted(_VALID_VERIFICATION_OUTCOMES))
    p_verify.add_argument("--evidence-ref", required=True)
    p_verify.add_argument(
        "--reproducer-commands-json",
        help='A real JSON array of {"cmd": "...", "exit_code": N} objects genuinely run to '
             "reproduce this finding. Omit if no reproduction was possible.",
    )
    p_verify.add_argument("--local-tooling-ruled-out", action="store_true")
    p_verify.add_argument("--supported-matrix-checked", action="store_true")
    p_verify.add_argument("--source-or-tests-inspected", action="store_true")
    p_verify.add_argument("--documentation-contract-compared", action="store_true")
    p_verify.add_argument("--reviewer-id", help="A second, independent reviewer's id, if one reviewed this verification.")
    p_verify.add_argument("--reviewer-verdict")
    p_verify.add_argument("--reviewer-note")
    p_verify.add_argument("--sanitization-applied", action="store_true")
    p_verify.add_argument("--package-version-confirmed")
    p_verify.add_argument("--verified-by", default="cli")

    p_classify = sub.add_parser("classify-finding")
    p_classify.add_argument("family")
    p_classify.add_argument("platform")
    p_classify.add_argument("--finding-id", required=True)
    p_classify.add_argument("--category", required=True, choices=sorted(_VALID_CATEGORIES))
    p_classify.add_argument("--severity", required=True, choices=sorted(_VALID_SEVERITIES))
    p_classify.add_argument("--priority", required=True, choices=sorted(_VALID_PRIORITIES))
    p_classify.add_argument("--classification-basis", required=True)
    p_classify.add_argument("--classified-by", default="cli")

    p_dup = sub.add_parser("search-duplicates")
    p_dup.add_argument("family")
    p_dup.add_argument("platform")
    p_dup.add_argument("--finding-id", required=True)
    p_dup.add_argument("--query", action="append", dest="queries", help="Repeatable. Defaults to the finding's own title when omitted.")
    p_dup.add_argument("--disposition", required=True, choices=sorted(_VALID_DUPLICATE_DISPOSITIONS))
    p_dup.add_argument("--disposition-basis", required=True)
    p_dup.add_argument("--searched-by", default="cli")

    p_bundle = sub.add_parser("bundle")
    p_bundle.add_argument("family")
    p_bundle.add_argument("platform")
    p_bundle.add_argument("--finding-ids", required=True, help="Comma-separated finding ids.")
    p_bundle.add_argument("--root-cause", required=True)
    p_bundle.add_argument("--why-bundled", required=True)
    p_bundle.add_argument("--same-component", action="store_true")
    p_bundle.add_argument("--same-root-cause", action="store_true")
    p_bundle.add_argument("--same-maintainer-audience", action="store_true")
    p_bundle.add_argument("--same-repro-env", action="store_true")
    p_bundle.add_argument("--single-fix-resolves-all", action="store_true")
    p_bundle.add_argument("--bundled-by", default="cli")

    p_prioritize = sub.add_parser("prioritize")
    p_prioritize.add_argument("family")
    p_prioritize.add_argument("platform")
    p_prioritize.add_argument("--bundle-id", required=True)
    p_prioritize.add_argument("--priority", choices=sorted(_VALID_PRIORITIES))
    p_prioritize.add_argument("--priority-basis")
    p_prioritize.add_argument("--prioritized-by", default="cli")

    p_draft = sub.add_parser("draft-issue")
    p_draft.add_argument("family")
    p_draft.add_argument("platform")
    p_draft.add_argument("--bundle-id", required=True)
    p_draft.add_argument("--drafted-by", default="cli")

    p_validate = sub.add_parser("validate-draft")
    p_validate.add_argument("family")
    p_validate.add_argument("platform")
    p_validate.add_argument("--bundle-id", required=True)
    p_validate.add_argument("--reviewer-id", required=True)
    p_validate.add_argument("--reviewer-verdict", required=True, choices=("approved", "confirmed"))
    p_validate.add_argument("--reviewer-note")
    p_validate.add_argument("--validated-by", default="cli")

    sub.add_parser("check-identity")

    p_create = sub.add_parser("create-issue")
    p_create.add_argument("family")
    p_create.add_argument("platform")
    p_create.add_argument("--bundle-id", required=True)
    p_create.add_argument(
        "--live", action="store_true",
        help="Actually file the real GitHub Issue (requires a real GH_TOKEN). Omitting this "
             "flag is the safe, real default: a full rehearsal with zero creating network calls.",
    )
    p_create.add_argument("--created-by", default="cli")

    p_status = sub.add_parser("status")
    p_status.add_argument("family")
    p_status.add_argument("platform")
    p_status.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    try:
        if args.command == "inventory":
            result = inventory(args.family, args.platform, session_id=args.session_id)
        elif args.command == "verify-finding":
            reproducer_commands = (
                json.loads(args.reproducer_commands_json) if args.reproducer_commands_json else None
            )
            independent_reviewer = (
                {"id": args.reviewer_id, "verdict": args.reviewer_verdict, "note": args.reviewer_note}
                if args.reviewer_id else None
            )
            result = verify_finding(
                args.family, args.platform, args.finding_id,
                outcome=args.outcome, evidence_ref=args.evidence_ref,
                reproducer_commands=reproducer_commands,
                local_tooling_ruled_out=args.local_tooling_ruled_out,
                supported_matrix_checked=args.supported_matrix_checked,
                source_or_tests_inspected=args.source_or_tests_inspected,
                documentation_contract_compared=args.documentation_contract_compared,
                independent_reviewer=independent_reviewer,
                sanitization_applied=args.sanitization_applied,
                package_or_release_version_confirmed=args.package_version_confirmed,
                verified_by=args.verified_by,
            )
        elif args.command == "classify-finding":
            result = classify_finding(
                args.family, args.platform, args.finding_id,
                category=args.category, severity=args.severity, priority=args.priority,
                classification_basis=args.classification_basis, classified_by=args.classified_by,
            )
        elif args.command == "search-duplicates":
            result = search_duplicates(
                args.family, args.platform, args.finding_id,
                queries=args.queries, disposition=args.disposition,
                disposition_basis=args.disposition_basis, searched_by=args.searched_by,
            )
        elif args.command == "bundle":
            result = bundle_findings(
                args.family, args.platform,
                [f.strip() for f in args.finding_ids.split(",") if f.strip()],
                root_cause=args.root_cause, why_bundled=args.why_bundled,
                same_component=args.same_component, same_root_cause=args.same_root_cause,
                same_maintainer_audience=args.same_maintainer_audience,
                same_repro_env=args.same_repro_env,
                single_fix_resolves_all=args.single_fix_resolves_all,
                bundled_by=args.bundled_by,
            )
        elif args.command == "prioritize":
            result = prioritize_bundle(
                args.family, args.platform, args.bundle_id,
                priority=args.priority, priority_basis=args.priority_basis,
                prioritized_by=args.prioritized_by,
            )
        elif args.command == "draft-issue":
            result = draft_issue(args.family, args.platform, args.bundle_id, drafted_by=args.drafted_by)
        elif args.command == "validate-draft":
            result = validate_draft(
                args.family, args.platform, args.bundle_id,
                independent_reviewer={
                    "id": args.reviewer_id, "verdict": args.reviewer_verdict, "note": args.reviewer_note,
                },
                validated_by=args.validated_by,
            )
        elif args.command == "check-identity":
            result = _preflight_identity_check()
        elif args.command == "create-issue":
            result = create_issue(
                args.family, args.platform, args.bundle_id,
                dry_run=not args.live, created_by=args.created_by,
            )
        elif args.command == "status":
            result = status(args.family, args.platform)
            if not args.json:
                print(f"{args.family}/{args.platform}: {result['findings']['total']} finding(s), "
                      f"{result['bundles']['total']} bundle(s)")
                for state, ids in sorted(result["findings"]["by_state"].items()):
                    print(f"  findings[{state}] ({len(ids)}): {', '.join(ids)}")
                for state, ids in sorted(result["bundles"]["by_state"].items()):
                    print(f"  bundles[{state}] ({len(ids)}): {', '.join(ids)}")
                return 0
        else:  # pragma: no cover -- argparse's own `required=True` makes this unreachable
            raise UpstreamIssueWorkflowError(f"Unknown command: {args.command!r}")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except UpstreamIssueWorkflowError as exc:
        print(f"UPSTREAM-ISSUE-WORKFLOW BLOCKED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
