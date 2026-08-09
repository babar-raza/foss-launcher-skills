"""CONTRACT: run-bound state machine for the /blind-spot-audit skill (S-122).

Wave 1 (skeleton) of MT025-2026-08-08-FORENSIC-BLIND-SPOT-HEAL-SKILLS. Architecture copied
from scripts/pipeline/commands/governance/root_docs_refresh_run.py (S-121's production
pattern: run-ID/session-ID binding, directory-per-run evidence, FileLock-guarded
single-owner locking, one exception type, configure() test seam) -- see the plan
(C:\\Users\\prora\\.claude\\plans\\typed-snuggling-peach.md) for the full design rationale.

Purpose: read-only, unaided (no-tooling) dual-pass review of cloned FOSS repos and
generated content, sealed before any system tooling runs, then a system-tooling pass, a
manual-vs-system blind-spot comparison matrix, root-cause analysis, solution-options fix
planning, and schema-5f taskcard emission. This skill never writes content/, scripts/,
knowledge/, or skills/ -- only its own evidence files and taskcard rows (via
taskcard_bridge.py, added in Wave 3).

HONEST SCOPE STATEMENT (Wave 2): `seal` now performs real unaided-first enforcement --
L1 (structural ordering, an INSIDE-window phase cannot be skipped and a POST-window phase
cannot be entered unless the manifest state is already SEALED), L2 (skill-invocation
ledger audit: no system-tooling skill may have started inside the unaided window -- see
scripts/pipeline/lib/forensic_heal/manual_first_audit.py), and L3 (artifact-mtime
forensics: no SYSTEM_ARTIFACT_ROOTS file/subtree may have appeared or been touched inside
the window). A non-CLEAN verdict moves the run to BLOCKED_UNAIDED_FIRST rather than
sealing; the only exits are `abandon` or retrying `seal --override-reason TEXT`, which
seals anyway but permanently records the violation in the manifest for later phases
(Wave 5's verdict computation caps the final verdict at WITH_LIMITATIONS whenever an
override is present -- not yet wired, since verdict computation itself is Wave 5).
L4 (narrowing the skill_context.py scope during the unaided window so system-tooling
outputs cannot structurally be written) is an OPERATOR CONVENTION documented in the skill
doc (Wave 3), not code this state machine enforces -- L2+L3 are the machine-independent
backstops for exactly the case where L4 wasn't followed.

HONEST SCOPE STATEMENT (Wave 3): the four analysis phases (blind-spots, root-cause,
fix-plan, taskcards-bind) now have real content requirements, validated by
scripts/pipeline/lib/forensic_heal/{blind_spot_matrix,root_cause_model,taskcard_bridge}.py
-- `advance --phase blind-spots|root-cause|fix-plan` requires `--evidence-file PATH` (a
JSON file the agent prepares with the phase's real findings/root-causes/fix-plan-items) and
REFUSES the transition if that content fails validation, rather than accepting a placeholder.
`taskcards-bind` is its own dedicated function (bind_taskcards()), not a generic `advance`
target: it reads the fix-plan evidence and actually writes taskcard rows via
scripts/pipeline/lib/taskcard_store.py -- the one and only sanctioned taskcard writer, never
a parallel scheme. `intake`, `scope`, `unaided-repo`, `unaided-content`, `agentic-
consumption`, and `system-review` remain placeholder phases (their real per-phase
validators -- capability-summary completeness, finding-record schema, and the
system-tooling ingestion adapters -- are future work, not scoped to this mission's waves).

State machine (PHASE_CONTRACTS is the single source of truth for ordering):

    CREATED -> INTAKE_PINNED -> SCOPED
             -> UNAIDED_REPO_REVIEWED -> UNAIDED_CONTENT_REVIEWED
             -> AGENTIC_CONSUMPTION_REVIEWED
             -> [seal] -> SEALED                                   <- hard gate, Wave 2
             -> SYSTEM_REVIEWED -> BLIND_SPOTS_MAPPED -> ROOT_CAUSED
             -> FIX_PLANNED -> TASKCARDS_BOUND (terminal)

`advance --phase X` walks PHASE_CONTRACTS strictly in order (no skipping, no re-entry) and
refuses to enter any POST-window phase while state != SEALED -- the L1 layer of
unaided-first enforcement. `seal` and `bind_taskcards` (CLI: `taskcards-bind`) are dedicated
verbs, not generic `advance` targets: seal is the one irreversible gate in the run (mirrors
S-121's `submit` precedent), and taskcards-bind is the one phase that writes outside its own
run directory (into reports/plan_state/{mission_id}/taskcards.jsonl). ABANDONED is reachable
from any non-terminal state. TASKCARDS_BOUND and ABANDONED are the only terminals.
"""
from __future__ import annotations

import argparse
import hashlib
import json
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
_GOVERNANCE_DIR = str(_PIPELINE_ROOT / "commands" / "governance")
if _GOVERNANCE_DIR not in sys.path:
    sys.path.insert(0, _GOVERNANCE_DIR)
_FORENSIC_HEAL_DIR = str(_LIB_DIR + "/forensic_heal")
if _FORENSIC_HEAL_DIR not in sys.path:
    sys.path.insert(0, _FORENSIC_HEAL_DIR)

import session_identity  # noqa: E402
from advisory_lock import FileLock, LockTimeout  # noqa: E402
from core.fs import atomic_write  # noqa: E402
from taskcard_store import TaskcardStore  # noqa: E402
import manual_first_audit  # noqa: E402
import blind_spot_matrix  # noqa: E402
import root_cause_model  # noqa: E402
import taskcard_bridge  # noqa: E402

SCHEMA_VERSION = 1

# Ordered by lifecycle: PRE phases run before the unaided window opens, INSIDE phases ARE
# the unaided window (no system tooling permitted -- see manual_first_audit.py, Wave 2),
# POST phases run only after `seal`. This table is the single source of truth NEXT_STATES
# and the CLI's --phase choices are both derived from.
PHASE_CONTRACTS: "tuple[dict[str, str], ...]" = (
    {"phase": "intake", "state": "INTAKE_PINNED", "window": "PRE"},
    {"phase": "scope", "state": "SCOPED", "window": "PRE"},
    {"phase": "unaided-repo", "state": "UNAIDED_REPO_REVIEWED", "window": "INSIDE"},
    {"phase": "unaided-content", "state": "UNAIDED_CONTENT_REVIEWED", "window": "INSIDE"},
    {"phase": "agentic-consumption", "state": "AGENTIC_CONSUMPTION_REVIEWED", "window": "INSIDE"},
    {"phase": "system-review", "state": "SYSTEM_REVIEWED", "window": "POST"},
    {"phase": "blind-spots", "state": "BLIND_SPOTS_MAPPED", "window": "POST"},
    {"phase": "root-cause", "state": "ROOT_CAUSED", "window": "POST"},
    {"phase": "fix-plan", "state": "FIX_PLANNED", "window": "POST"},
    {"phase": "taskcards-bind", "state": "TASKCARDS_BOUND", "window": "POST"},
)
_PHASE_BY_NAME: "dict[str, dict[str, str]]" = {p["phase"]: p for p in PHASE_CONTRACTS}
_PHASE_ORDER: "tuple[str, ...]" = tuple(p["phase"] for p in PHASE_CONTRACTS)
_STATE_BY_PHASE: "dict[str, str]" = {p["phase"]: p["state"] for p in PHASE_CONTRACTS}

_SEALED_STATE = "SEALED"
_BLOCKED_UNAIDED_FIRST_STATE = "BLOCKED_UNAIDED_FIRST"
_LAST_INSIDE_STATE = "AGENTIC_CONSUMPTION_REVIEWED"
_TERMINAL_PHASE = "taskcards-bind"
TERMINAL_STATES = frozenset({_STATE_BY_PHASE[_TERMINAL_PHASE], "ABANDONED"})

# All legal states, in creation order, for manifest validation. BLOCKED_UNAIDED_FIRST is
# reachable only from AGENTIC_CONSUMPTION_REVIEWED (a failed seal()) and exits only via
# abandon() or a retried seal() (with or without --override-reason).
ALL_STATES: "tuple[str, ...]" = ("CREATED",) + tuple(p["state"] for p in PHASE_CONTRACTS[:5]) + (
    _BLOCKED_UNAIDED_FIRST_STATE, _SEALED_STATE,
) + tuple(p["state"] for p in PHASE_CONTRACTS[5:]) + ("ABANDONED",)


def _next_phase(current_phase: "str | None") -> "str | None":
    """Return the phase name immediately after current_phase in PHASE_CONTRACTS order, or
    the first phase if current_phase is None (run just CREATED)."""
    if current_phase is None:
        return _PHASE_ORDER[0]
    idx = _PHASE_ORDER.index(current_phase)
    if idx + 1 >= len(_PHASE_ORDER):
        return None
    return _PHASE_ORDER[idx + 1]


_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
_repo_root = _DEFAULT_REPO_ROOT
_reports_root = _DEFAULT_REPO_ROOT / "reports"
_command_runner: Callable[..., "subprocess.CompletedProcess[str]"] = subprocess.run
_now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)


class BlindSpotAuditRunError(RuntimeError):
    """Raised when a run contract or state transition is unsafe."""


def configure(
    *,
    repo_root: "Path | str | None" = None,
    reports_root: "Path | str | None" = None,
    command_runner: "Callable[..., subprocess.CompletedProcess[str]] | None" = None,
    now: "Callable[[], datetime] | None" = None,
) -> None:
    """Override external boundaries for tests; call without arguments to reset."""
    global _repo_root, _reports_root, _command_runner, _now
    _repo_root = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    _reports_root = Path(reports_root) if reports_root is not None else _repo_root / "reports"
    _command_runner = command_runner or subprocess.run
    _now = now or (lambda: datetime.now(timezone.utc))


def _utc() -> str:
    return _now().astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _session_id(explicit: "str | None" = None) -> str:
    value = session_identity.resolve_sanitized(explicit)
    if not value:
        raise BlindSpotAuditRunError(
            "A stable session identity is required: pass --session-id or set "
            "AGENT_SESSION_ID/CODEX_THREAD_ID/CLAUDE_CODE_SESSION_ID"
        )
    return value


# --- Paths -----------------------------------------------------------------------------


def _run_root(run_id: str) -> Path:
    return _reports_root / "blind_spot_audit" / run_id


def _manifest_path(run_id: str) -> Path:
    return _run_root(run_id) / "manifest.json"


def _active_path() -> Path:
    return _reports_root / "blind_spot_audit" / "ACTIVE.json"


def _lock_path() -> Path:
    return _reports_root / "locks" / "blind_spot_audit.lock"


@contextmanager
def _guard() -> Iterator[None]:
    try:
        with FileLock(_lock_path(), timeout=10.0):
            yield
    except LockTimeout as exc:
        raise BlindSpotAuditRunError(str(exc)) from exc


def _git(*args: str, check: bool = True) -> str:
    result = _command_runner(
        ["git", *args], cwd=str(_repo_root), capture_output=True, text=True, timeout=60,
    )
    if check and result.returncode != 0:
        raise BlindSpotAuditRunError(
            f"git {' '.join(args)} failed ({result.returncode}): {(result.stderr or result.stdout).strip()}"
        )
    return result.stdout.strip()


# --- Manifest ----------------------------------------------------------------------------

_REQUIRED_MANIFEST_KEYS = {
    "schema_version", "run_id", "mission_id", "state", "session_owner", "created_at",
    "updated_at", "products",
}


def _validate_manifest(data: dict) -> list[str]:
    errors = []
    for key in _REQUIRED_MANIFEST_KEYS:
        if key not in data:
            errors.append(f"missing required key: {key}")
    if "state" in data and data["state"] not in ALL_STATES:
        errors.append(f"unknown state: {data.get('state')!r}")
    if "products" in data and not isinstance(data["products"], list):
        errors.append("'products' must be a list")
    return errors


def _write_json(path: Path, data: dict) -> None:
    atomic_write(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def _load_manifest(run_id: str) -> dict:
    path = _manifest_path(run_id)
    if not path.is_file():
        raise BlindSpotAuditRunError(f"Run not found: {run_id}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise BlindSpotAuditRunError(f"Run manifest is unreadable: {exc}") from exc
    errors = _validate_manifest(data)
    if errors:
        raise BlindSpotAuditRunError(f"Run manifest is invalid: {errors}")
    return data


def _save_manifest(data: dict) -> None:
    data["updated_at"] = _utc()
    errors = _validate_manifest(data)
    if errors:
        raise BlindSpotAuditRunError(f"Refusing to write invalid run manifest: {errors}")
    _write_json(_manifest_path(data["run_id"]), data)


def _event(run_id: str, event_type: str, **fields: Any) -> None:
    path = _run_root(run_id) / "events.jsonl"
    row = {"at": _utc(), "event": event_type, **fields}
    prior = path.read_text(encoding="utf-8") if path.is_file() else ""
    atomic_write(path, prior + json.dumps(row, ensure_ascii=False) + "\n")


def _evidence_path(run_id: str, phase: str) -> Path:
    return _run_root(run_id) / f"evidence-{phase}.json"


def _set_active(run_id: str) -> None:
    _write_json(_active_path(), {"run_id": run_id, "updated_at": _utc()})


def _clear_active(run_id: str) -> None:
    path = _active_path()
    if not path.is_file():
        return
    try:
        active = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    if active.get("run_id") == run_id:
        path.unlink(missing_ok=True)


def _transition(manifest: dict, target: str, *, phase: "str | None" = None) -> None:
    manifest["state"] = target
    if phase:
        manifest.setdefault("phase_history", []).append({"phase": phase, "state": target, "completed_at": _utc()})
    _save_manifest(manifest)
    _event(manifest["run_id"], "STATE_TRANSITION", current=target, phase=phase)


def _transition_abandoned(manifest: dict, *, reason: str) -> None:
    current = manifest["state"]
    if current in TERMINAL_STATES:
        raise BlindSpotAuditRunError(f"Run {manifest['run_id']} is already terminal ({current})")
    manifest["state"] = "ABANDONED"
    manifest["abandon_reason"] = reason.strip()
    _save_manifest(manifest)
    _event(manifest["run_id"], "STATE_TRANSITION", current="ABANDONED", previous=current)


# --- open: CREATED -> INTAKE_PINNED (first phase) --------------------------------------


def open_run(
    *, products: list[str], mission_id: str, run_id: "str | None" = None,
    session_id: "str | None" = None,
) -> dict:
    """Start a new run: single-owner lock via ACTIVE.json (refuses if another non-terminal
    run is active), pins the current git HEAD, writes the manifest at CREATED, then
    immediately advances to the first PHASE_CONTRACTS phase (intake -> INTAKE_PINNED).

    mission_id is required (not inferred) -- it is where bind_taskcards() later writes via
    TaskcardStore, and this run has no business emitting taskcards into a mission it wasn't
    told about."""
    if not products:
        raise BlindSpotAuditRunError("open requires at least one --products entry")
    if not mission_id or not mission_id.strip():
        raise BlindSpotAuditRunError("open requires a non-empty --mission-id")
    owner = _session_id(session_id)
    rid = run_id or f"bsa-{_now().strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:12]}"

    with _guard():
        active_path = _active_path()
        if active_path.is_file():
            try:
                active = json.loads(active_path.read_text(encoding="utf-8"))
                prior = _load_manifest(active["run_id"])
            except Exception as exc:
                raise BlindSpotAuditRunError(f"Existing active-run pointer is invalid: {exc}") from exc
            if prior.get("state") not in TERMINAL_STATES:
                raise BlindSpotAuditRunError(
                    f"blind-spot-audit already has active run {active['run_id']} "
                    f"in state {prior.get('state')} (session {prior.get('session_owner')})"
                )
            _clear_active(active["run_id"])

        run_root = _run_root(rid)
        if run_root.exists():
            raise BlindSpotAuditRunError(f"Run ID already exists: {rid}")
        run_root.mkdir(parents=True)

        try:
            head_sha = _git("rev-parse", "HEAD")
        except BlindSpotAuditRunError:
            head_sha = None

        now = _utc()
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "run_id": rid,
            "mission_id": mission_id.strip(),
            "state": "CREATED",
            "session_owner": owner,
            "created_at": now,
            "updated_at": now,
            "products": list(products),
            "pinned_inputs": {"git_head_sha": head_sha},
            "phase_history": [],
        }
        _save_manifest(manifest)
        _event(rid, "RUN_CREATED", session_owner=owner, products=products)
        _set_active(rid)

        # Immediately advance into the first phase (intake) -- CREATED itself is not a
        # phase a caller advances into; it is the pre-phase-zero state.
        first_phase = _PHASE_ORDER[0]
        _write_json(_evidence_path(rid, first_phase), {"phase": first_phase, "recorded_at": now})
        _transition(manifest, _STATE_BY_PHASE[first_phase], phase=first_phase)
        return manifest


# --- advance: walks PHASE_CONTRACTS strictly in order ------------------------------------

# Phases whose real content is agent-supplied via --evidence-file (a JSON file) and
# validated by a forensic_heal library module before the transition is allowed -- see
# _validate_and_shape_phase_content(). Every other phase still uses the placeholder
# {"phase": ..., "recorded_at": ...} shape (see module docstring's Honest Scope Statement).
_EVIDENCE_FILE_PHASES: "frozenset[str]" = frozenset({"blind-spots", "root-cause", "fix-plan"})

_FIX_PLAN_SCORING_AXES: "frozenset[str]" = frozenset({
    "correctness", "scope", "maintainability", "risk", "repeatability", "verification_cost",
})


def _load_phase_evidence(run_id: str, phase: str) -> dict:
    path = _evidence_path(run_id, phase)
    if not path.is_file():
        raise BlindSpotAuditRunError(f"Missing evidence for phase {phase!r} in run {run_id}: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_and_shape_phase_content(run_id: str, phase: str, payload: dict, *, now: str) -> dict:
    if phase == "blind-spots":
        unaided = payload.get("unaided_findings", [])
        system = payload.get("system_findings", [])
        result = blind_spot_matrix.build_comparison_matrix(unaided, system)
        if result["orphan_finding_ids"]:
            raise BlindSpotAuditRunError(
                f"blind-spots phase refused: {len(result['orphan_finding_ids'])} finding(s) "
                f"unaccounted for in the comparison matrix: {result['orphan_finding_ids']}"
            )
        result["recorded_at"] = now
        return result

    if phase == "root-cause":
        built = [root_cause_model.build_root_cause(**rc) for rc in payload.get("root_causes", [])]
        blind_spots_evidence = _load_phase_evidence(run_id, "blind-spots")
        all_finding_ids: "set[str]" = set()
        for row in blind_spots_evidence.get("rows", []):
            all_finding_ids.update(row.get("unaided_finding_ids", []))
            all_finding_ids.update(row.get("system_finding_ids", []))
        warnings = root_cause_model.validate_root_cause_set(built, all_finding_ids=all_finding_ids)
        return {"root_causes": built, "warnings": warnings, "recorded_at": now}

    if phase == "fix-plan":
        items = payload.get("fix_plan_items", [])
        errors: "list[str]" = []
        for i, item in enumerate(items):
            options = item.get("options", [])
            if len(options) < 2:
                errors.append(f"fix_plan_items[{i}] ({item.get('root_cause_id')!r}): requires >=2 options, has {len(options)}")
                continue
            for j, opt in enumerate(options):
                missing = _FIX_PLAN_SCORING_AXES - set(opt.keys())
                if missing:
                    errors.append(f"fix_plan_items[{i}].options[{j}]: missing scoring axes {sorted(missing)}")
            selected = [opt for opt in options if opt.get("selected")]
            if len(selected) != 1:
                errors.append(f"fix_plan_items[{i}]: exactly one option must have selected=true, found {len(selected)}")
        if errors:
            raise BlindSpotAuditRunError(f"fix-plan phase refused ({len(errors)} error(s)): {errors}")
        return {"fix_plan_items": items, "recorded_at": now}

    raise AssertionError(f"unreachable phase in _validate_and_shape_phase_content: {phase!r}")


def advance(
    run_id: str, *, phase: str, session_id: "str | None" = None, evidence_file: "str | None" = None,
) -> dict:
    """Move the run from its current phase to the next phase in PHASE_CONTRACTS order.

    `phase` must be exactly the phase immediately following the run's current phase --
    skipping ahead or re-entering a completed phase is refused. Entering a POST-window
    phase is refused unless the manifest state is already SEALED (L1). `phase="seal"` and
    `phase="taskcards-bind"` are always refused here: both are dedicated verbs (seal(),
    bind_taskcards()), not generic advance targets.

    For phase in {blind-spots, root-cause, fix-plan}: `evidence_file` (a JSON file path) is
    REQUIRED and its content is validated by the matching forensic_heal library module
    before the transition is allowed -- a malformed or under-specified evidence file
    refuses the transition entirely, it is never partially accepted.

    Entering the FIRST INSIDE-window phase opens the unaided window: records
    unaided_window_opened_at and takes the L3 baseline census (evidence-unaided-open-
    census.json) that seal() later diffs against. PRE-window phases (intake, scope) may
    legitimately use tooling (S-92/S-93/S-94 for baseline/scope work) and are deliberately
    outside the window -- opening the census here, not at open_run(), is what keeps that
    legitimate PRE-phase activity from tripping L2/L3.
    """
    if phase == "seal":
        raise BlindSpotAuditRunError("seal is a dedicated verb -- call `seal`, not `advance --phase seal`")
    if phase == "taskcards-bind":
        raise BlindSpotAuditRunError(
            "taskcards-bind is a dedicated verb -- call `bind_taskcards`, not `advance --phase taskcards-bind`"
        )
    if phase not in _PHASE_BY_NAME:
        raise BlindSpotAuditRunError(f"Unknown phase {phase!r}; choices: {', '.join(_PHASE_ORDER)}")

    manifest = _load_manifest(run_id)
    _session_id(session_id)  # validate a session identity is present
    if manifest["state"] in TERMINAL_STATES:
        raise BlindSpotAuditRunError(f"Run {run_id} is already terminal ({manifest['state']})")

    current_phase = manifest["phase_history"][-1]["phase"] if manifest.get("phase_history") else None
    expected_next = _next_phase(current_phase)
    if phase != expected_next:
        raise BlindSpotAuditRunError(
            f"Illegal advance: run is at phase {current_phase!r}, next eligible phase is "
            f"{expected_next!r}, not {phase!r}"
        )

    contract = _PHASE_BY_NAME[phase]
    # "sealed_at" is set once by seal() and never removed -- checking THIS, not
    # `manifest["state"] == SEALED`, matters: state has already moved past SEALED for every
    # POST-window phase after the first (e.g. state=SYSTEM_REVIEWED when advancing into
    # blind-spots), so comparing state itself would only ever allow the FIRST POST phase.
    if contract["window"] == "POST" and "sealed_at" not in manifest:
        raise BlindSpotAuditRunError(
            f"Cannot advance to POST-window phase {phase!r}: run is not SEALED "
            f"(state={manifest['state']!r}). Call `seal` first."
        )

    now = _utc()
    if contract["window"] == "INSIDE" and "unaided_window_opened_at" not in manifest:
        manifest["unaided_window_opened_at"] = now
        before_census = manual_first_audit.census_artifacts(_repo_root)
        _write_json(_run_root(run_id) / "evidence-unaided-open-census.json", before_census)
        _event(run_id, "UNAIDED_WINDOW_OPENED", at=now)

    if phase in _EVIDENCE_FILE_PHASES:
        if not evidence_file:
            raise BlindSpotAuditRunError(f"phase {phase!r} requires --evidence-file")
        try:
            payload = json.loads(Path(evidence_file).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BlindSpotAuditRunError(f"Cannot read --evidence-file {evidence_file!r}: {exc}") from exc
        content = _validate_and_shape_phase_content(run_id, phase, payload, now=now)
        _write_json(_evidence_path(run_id, phase), content)
    else:
        _write_json(_evidence_path(run_id, phase), {"phase": phase, "recorded_at": now})

    _transition(manifest, contract["state"], phase=phase)
    if contract["state"] in TERMINAL_STATES:
        _clear_active(run_id)
    return manifest


# --- recheck: Wave 1 placeholder, no transition ------------------------------------------


def recheck(run_id: str) -> dict:
    """Re-run the current phase's checks in place (no state transition).

    Wave 1 placeholder: re-timestamps the current phase's evidence file. Real per-phase
    content validators (capability-summary completeness in Wave 2, finding-record schema
    and the blind-spot matrix itself in Wave 3) replace this body without changing the
    CLI contract.
    """
    manifest = _load_manifest(run_id)
    if manifest["state"] in TERMINAL_STATES:
        raise BlindSpotAuditRunError(f"Run {run_id} is already terminal ({manifest['state']})")
    if not manifest.get("phase_history"):
        raise BlindSpotAuditRunError(f"Run {run_id} has not entered any phase yet")
    current_phase = manifest["phase_history"][-1]["phase"]
    _write_json(_evidence_path(run_id, current_phase), {"phase": current_phase, "recorded_at": _utc(), "rechecked": True})
    _event(run_id, "RECHECK", phase=current_phase)
    return manifest


# --- seal: AGENTIC_CONSUMPTION_REVIEWED -> SEALED, or -> BLOCKED_UNAIDED_FIRST -----------

# Unaided artifacts sealed (hashed) once the gate passes -- the INSIDE-window evidence
# files plus the L3 baseline itself, so re-audit (Wave 5) can detect retroactive editing.
_SEALED_EVIDENCE_PHASES: "tuple[str, ...]" = ("unaided-repo", "unaided-content", "agentic-consumption")


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def seal(run_id: str, *, session_id: "str | None" = None, override_reason: "str | None" = None) -> dict:
    """The unaided-first hard gate: AGENTIC_CONSUMPTION_REVIEWED -> SEALED.

    Runs L2 (skill-invocation ledger audit) + L3 (artifact-mtime forensics) via
    manual_first_audit.evaluate_unaided_first() over the window
    [unaided_window_opened_at, now]. On UNAIDED_FIRST_CLEAN: SHA-256-hashes every sealed
    evidence file into evidence-manual-seal.json and transitions to SEALED. On VIOLATED or
    UNPROVABLE: transitions to BLOCKED_UNAIDED_FIRST and raises, listing every violation,
    UNLESS override_reason is given -- in which case the run still seals, but the manifest
    permanently records unaided_first_override (verdict computation in Wave 5 must cap the
    final verdict at WITH_LIMITATIONS whenever this is present; not yet wired here).
    Callable again from BLOCKED_UNAIDED_FIRST as a retry (the same violations will recur
    unless the underlying cause is fixed -- a diff-based census/ledger audit cannot
    "un-detect" something that already happened; only an override can proceed past it).
    """
    manifest = _load_manifest(run_id)
    _session_id(session_id)  # validate a session identity is present
    if manifest["state"] not in (_LAST_INSIDE_STATE, _BLOCKED_UNAIDED_FIRST_STATE):
        raise BlindSpotAuditRunError(
            f"seal requires state {_LAST_INSIDE_STATE!r} or {_BLOCKED_UNAIDED_FIRST_STATE!r}, "
            f"run {run_id} is at {manifest['state']!r}"
        )
    window_start = manifest.get("unaided_window_opened_at")
    if not window_start:
        raise BlindSpotAuditRunError(
            f"Run {run_id} has no unaided_window_opened_at -- the unaided window was never "
            f"entered (advance through unaided-repo first)"
        )
    before_census_path = _run_root(run_id) / "evidence-unaided-open-census.json"
    if not before_census_path.is_file():
        raise BlindSpotAuditRunError(f"Missing L3 baseline census for run {run_id}: {before_census_path}")
    before_census = json.loads(before_census_path.read_text(encoding="utf-8"))

    now = _utc()
    result = manual_first_audit.evaluate_unaided_first(
        _repo_root, window_start=window_start, window_end=now, before_census=before_census,
    )
    _write_json(_run_root(run_id) / "evidence-unaided-audit.json", {
        "window_start": window_start, "window_end": now,
        "verdict": result["verdict"], "violations": result["violations"],
        "ledger_readable": result["ledger_readable"],
    })
    _event(run_id, "UNAIDED_FIRST_AUDIT", verdict=result["verdict"], violation_count=len(result["violations"]))

    if result["verdict"] != "UNAIDED_FIRST_CLEAN" and not override_reason:
        manifest["state"] = _BLOCKED_UNAIDED_FIRST_STATE
        manifest["unaided_first_verdict"] = result["verdict"]
        _save_manifest(manifest)
        _event(run_id, "STATE_TRANSITION", current=_BLOCKED_UNAIDED_FIRST_STATE, previous=_LAST_INSIDE_STATE)
        detail = "; ".join(v["detail"] for v in result["violations"]) or "ledger unreadable"
        raise BlindSpotAuditRunError(
            f"seal refused: unaided-first verdict is {result['verdict']} ({detail}). "
            f"Retry with --override-reason to seal anyway (caps the final verdict at "
            f"WITH_LIMITATIONS), or `abandon` this run."
        )

    # CLEAN, or VIOLATED/UNPROVABLE with an explicit override: hash the sealed evidence.
    hashes: "dict[str, str]" = {"evidence-unaided-open-census.json": _hash_file(before_census_path)}
    for phase in _SEALED_EVIDENCE_PHASES:
        p = _evidence_path(run_id, phase)
        if p.is_file():
            hashes[p.name] = _hash_file(p)
    _write_json(_run_root(run_id) / "evidence-manual-seal.json", {
        "sealed_at": now, "file_hashes": hashes, "unaided_first_verdict": result["verdict"],
    })

    if result["verdict"] != "UNAIDED_FIRST_CLEAN":
        manifest["unaided_first_override"] = {
            "reason": override_reason.strip(), "verdict": result["verdict"], "overridden_at": now,
        }
    manifest["unaided_first_verdict"] = result["verdict"]
    manifest["sealed_at"] = now
    _transition(manifest, _SEALED_STATE)
    return manifest


# --- taskcards-bind: FIX_PLANNED -> TASKCARDS_BOUND (terminal) ---------------------------


def bind_taskcards(run_id: str, *, session_id: "str | None" = None) -> dict:
    """FIX_PLANNED -> TASKCARDS_BOUND (terminal). Reads the fix-plan phase's evidence,
    converts each item's SELECTED option into a schema-5f taskcard via taskcard_bridge, and
    appends every card via TaskcardStore(mission_id).append() -- the one sanctioned
    taskcard writer (reports/plan_state/{mission_id}/taskcards.jsonl), never a parallel
    scheme. A dedicated verb, not a generic advance target: this is the one phase that
    writes outside its own run directory."""
    manifest = _load_manifest(run_id)
    owner = _session_id(session_id)
    if manifest["state"] in TERMINAL_STATES:
        raise BlindSpotAuditRunError(f"Run {run_id} is already terminal ({manifest['state']})")

    current_phase = manifest["phase_history"][-1]["phase"] if manifest.get("phase_history") else None
    expected_next = _next_phase(current_phase)
    if expected_next != "taskcards-bind":
        raise BlindSpotAuditRunError(
            f"Illegal bind_taskcards: run is at phase {current_phase!r}, next eligible phase "
            f"is {expected_next!r}, not 'taskcards-bind'"
        )

    fix_plan_evidence = _load_phase_evidence(run_id, "fix-plan")
    taskcard_items: "list[dict]" = []
    for item in fix_plan_evidence.get("fix_plan_items", []):
        # Selection was already enforced at the fix-plan phase (exactly one selected=true);
        # this loop only needs the item's own fields, not which option was chosen.
        taskcard_items.append({
            "title": item["title"],
            "root_cause_id": item["root_cause_id"],
            "finding_ids": item["finding_ids"],
            "layer": item["layer"],
            "priority": item["priority"],
            "allowed_paths": item["allowed_paths"],
            "forbidden_paths": item.get("forbidden_paths", []),
            "verification_commands": item["verification_commands"],
            "rollback": item["rollback"],
            "affected_content_paths": item.get("affected_content_paths", []),
            "regeneration_required": item.get("regeneration_required", False),
        })

    now = _utc()
    cards = taskcard_bridge.build_taskcards_from_fix_plan(
        taskcard_items, mission_id=manifest["mission_id"], recorded_at=now,
        recorded_by=owner, task_id_prefix=f"TC-BSA-{run_id}",
    )
    # repo_root explicit, not defaulted: TaskcardStore's own default resolves to the REAL
    # repo root at import time, which would silently escape configure()'s test sandbox and
    # write into the real reports/plan_state/ during tests.
    store = TaskcardStore(manifest["mission_id"], repo_root=_repo_root)
    for card in cards:
        store.append(card)

    _write_json(_evidence_path(run_id, "taskcards-bind"), {
        "phase": "taskcards-bind", "recorded_at": now, "task_ids": [c["task_id"] for c in cards],
    })
    _transition(manifest, _STATE_BY_PHASE["taskcards-bind"], phase="taskcards-bind")
    _clear_active(run_id)
    return manifest


# --- close: assert terminal state reached -------------------------------------------------


def close(run_id: str) -> dict:
    """Assert the run has reached its terminal phase (taskcards-bind -> TASKCARDS_BOUND).
    ACTIVE.json is already cleared by advance() on reaching a terminal state; this is a
    read-only confirmation, matching mission_authority.py close's semantics."""
    manifest = _load_manifest(run_id)
    if manifest["state"] != _STATE_BY_PHASE[_TERMINAL_PHASE]:
        raise BlindSpotAuditRunError(
            f"Cannot close: run {run_id} is at {manifest['state']!r}, not "
            f"{_STATE_BY_PHASE[_TERMINAL_PHASE]!r}"
        )
    return manifest


# --- abandon: any non-terminal -> ABANDONED ------------------------------------------------


def abandon(run_id: str, *, reason: str) -> dict:
    manifest = _load_manifest(run_id)
    _transition_abandoned(manifest, reason=reason)
    _clear_active(run_id)
    return manifest


def status(run_id: str) -> dict:
    return _load_manifest(run_id)


# --- CLI -----------------------------------------------------------------------------------


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description="blind-spot-audit run-bound state machine (S-122)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_open = sub.add_parser("open", help="CREATED -> INTAKE_PINNED: start a new run")
    p_open.add_argument("--products", nargs="+", required=True, help="family/platform entries")
    p_open.add_argument("--mission-id", required=True)
    p_open.add_argument("--run-id", default=None)
    p_open.add_argument("--session-id", default=None)

    p_advance = sub.add_parser("advance", help="Move to the next phase in PHASE_CONTRACTS order")
    p_advance.add_argument("--run-id", required=True)
    p_advance.add_argument("--phase", required=True, choices=[p for p in _PHASE_ORDER])
    p_advance.add_argument("--session-id", default=None)
    p_advance.add_argument(
        "--evidence-file", default=None,
        help="JSON file with phase content; required for blind-spots/root-cause/fix-plan",
    )

    p_recheck = sub.add_parser("recheck", help="Re-run current phase's checks, no transition")
    p_recheck.add_argument("--run-id", required=True)

    p_seal = sub.add_parser("seal", help="Unaided-first hard gate: L1+L2+L3 enforcement")
    p_seal.add_argument("--run-id", required=True)
    p_seal.add_argument("--session-id", default=None)
    p_seal.add_argument("--override-reason", default=None)

    p_bind = sub.add_parser("bind-taskcards", help="FIX_PLANNED -> TASKCARDS_BOUND: emit schema-5f taskcards")
    p_bind.add_argument("--run-id", required=True)
    p_bind.add_argument("--session-id", default=None)

    p_close = sub.add_parser("close", help="Assert terminal state reached")
    p_close.add_argument("--run-id", required=True)

    p_abandon = sub.add_parser("abandon", help="Any non-terminal -> ABANDONED")
    p_abandon.add_argument("--run-id", required=True)
    p_abandon.add_argument("--reason", required=True)

    p_status = sub.add_parser("status", help="Print run manifest")
    p_status.add_argument("--run-id", required=True)

    args = parser.parse_args(argv)

    try:
        if args.command == "open":
            result = open_run(
                products=args.products, mission_id=args.mission_id, run_id=args.run_id,
                session_id=args.session_id,
            )
        elif args.command == "advance":
            result = advance(
                args.run_id, phase=args.phase, session_id=args.session_id,
                evidence_file=args.evidence_file,
            )
        elif args.command == "recheck":
            result = recheck(args.run_id)
        elif args.command == "seal":
            result = seal(args.run_id, session_id=args.session_id, override_reason=args.override_reason)
        elif args.command == "bind-taskcards":
            result = bind_taskcards(args.run_id, session_id=args.session_id)
        elif args.command == "close":
            result = close(args.run_id)
        elif args.command == "abandon":
            result = abandon(args.run_id, reason=args.reason)
        elif args.command == "status":
            result = status(args.run_id)
        else:
            parser.error(f"unknown command {args.command!r}")
            return 2
    except BlindSpotAuditRunError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
