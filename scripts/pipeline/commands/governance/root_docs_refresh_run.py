"""CONTRACT: run-bound state machine for the /root-docs-refresh skill (S-121).

Right-sized against readme_refresh_run.py's architecture (S-120's production pattern --
run-ID/session-ID binding, directory-per-run evidence, FileLock-guarded single-owner
locking, one exception type) adapted to a much narrower effect boundary: this skill edits
seven files already inside this repo's own working tree and lands them via the existing
/commit (S-76) skill -- there is no external GitHub push, no per-product concurrency (there
is exactly one target: this repo's own root docs), and no cross-repo preflight. Copying
readme-refresh's per-product locking or disposable-clone push machinery here would be
over-engineering; see plan (moonlit-strolling-sunset.md) Design section for the explicit
rationale on what was kept vs dropped.

State machine:

    CREATED -> FACTS_PINNED -> AWAITING_REVIEW -> APPROVED -> COMMITTED
    BLOCKED re-enterable from FACTS_PINNED / AWAITING_REVIEW / APPROVED.
    ABANDONED terminal from any non-terminal state. COMMITTED and ABANDONED are the only
    terminals. AWAITING_REVIEW -> FACTS_PINNED and APPROVED -> FACTS_PINNED both exist for
    the "drift or new hard-gate finding forces re-plan" path (approve() re-verifies the
    pinned git HEAD hasn't moved since plan() before letting a run proceed -- exactly the
    concurrent-session hazard this repo has hit before). `recheck` does NOT transition state;
    it re-runs the deterministic checks (root_docs_checks.py) in place after remediation and
    updates checks/result.json. `submit` is the hard gate: FACTS_PINNED -> AWAITING_REVIEW
    only when the latest check results show zero HARD_GATE findings.

HONEST SCOPE STATEMENT: `plan`/`recheck`/`submit`/`approve` are fully real -- they read
data/products.json, docs/registries/skills.md, content_eval/__init__.py, grade_config.yaml,
and call the real functions in root_docs_checks.py; nothing here is a stub. `commit_prepare`
creates real override tokens via override_manager.py. It deliberately does NOT itself invoke
git or the /commit skill -- /commit (S-76) is an agent-executed skill with its own multi-step
contract, not a single deterministic subprocess call, so pretending to invoke it here would
be dishonest. `finalize` records the resulting commit SHA and consumes the tokens after the
agent has actually run /commit -- the same split CLAUDE.md's git_plumb_commit.py guidance
already uses (retroactive finalization tied to the real resulting SHA, not a promise made
before the fact).
"""
from __future__ import annotations

import argparse
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
_GOVERNANCE_DIR = Path(__file__).resolve().parent
if str(_GOVERNANCE_DIR) not in sys.path:
    sys.path.insert(0, str(_GOVERNANCE_DIR))

import session_identity  # noqa: E402
from advisory_lock import FileLock, LockTimeout  # noqa: E402
from core.fs import atomic_write  # noqa: E402

import root_docs_checks as checks  # noqa: E402
import override_manager  # noqa: E402

SCHEMA_VERSION = 1

# The seven files this skill refreshes. TASK_BACKLOG.md is gitignored/untracked (per the
# plan's diagnosis) and is intentionally excluded from the checks pipeline -- it's a plain
# filesystem delete with no governance gate, handled by the agent directly, not this state
# machine.
TARGET_FILES: tuple[str, ...] = (
    "OPERATOR_GUIDE.md",
    "RUNBOOK.md",
    "CODEX.md",
    "GRADE_CONTRACT.md",
    "LAYMAN_SYSTEM_STATUS_REVIEW.md",
    "TASK_BACKLOG_20260521.md",
)

TERMINAL_STATES = frozenset({"COMMITTED", "ABANDONED"})
NEXT_STATES: dict[str, set[str]] = {
    "CREATED": {"FACTS_PINNED", "BLOCKED", "ABANDONED"},
    "FACTS_PINNED": {"AWAITING_REVIEW", "BLOCKED", "ABANDONED"},
    "AWAITING_REVIEW": {"APPROVED", "FACTS_PINNED", "ABANDONED"},
    "APPROVED": {"COMMITTED", "FACTS_PINNED", "ABANDONED"},
    "BLOCKED": {"FACTS_PINNED", "AWAITING_REVIEW", "APPROVED", "ABANDONED"},
    "COMMITTED": set(),
    "ABANDONED": set(),
}

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
_repo_root = _DEFAULT_REPO_ROOT
_reports_root = _DEFAULT_REPO_ROOT / "reports"
_command_runner: Callable[..., "subprocess.CompletedProcess[str]"] = subprocess.run
_now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)


class RootDocsRefreshRunError(RuntimeError):
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
    override_manager.configure(repo_root=_repo_root)


def _utc() -> str:
    return _now().astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _session_id(explicit: "str | None" = None) -> str:
    value = session_identity.resolve_sanitized(explicit)
    if not value:
        raise RootDocsRefreshRunError(
            "A stable session identity is required: pass --session-id or set "
            "AGENT_SESSION_ID/CODEX_THREAD_ID/CLAUDE_CODE_SESSION_ID"
        )
    return value


# --- Paths -------------------------------------------------------------------------------


def _run_root(run_id: str) -> Path:
    return _reports_root / "root_docs_refresh" / run_id


def _manifest_path(run_id: str) -> Path:
    return _run_root(run_id) / "manifest.json"


def _active_path() -> Path:
    return _reports_root / "root_docs_refresh" / "ACTIVE.json"


def _lock_path() -> Path:
    return _reports_root / "locks" / "root_docs_refresh.lock"


@contextmanager
def _guard() -> Iterator[None]:
    try:
        with FileLock(_lock_path(), timeout=10.0):
            yield
    except LockTimeout as exc:
        raise RootDocsRefreshRunError(str(exc)) from exc


def _git(*args: str, check: bool = True) -> str:
    result = _command_runner(
        ["git", *args], cwd=str(_repo_root), capture_output=True, text=True, timeout=60,
    )
    if check and result.returncode != 0:
        raise RootDocsRefreshRunError(
            f"git {' '.join(args)} failed ({result.returncode}): {(result.stderr or result.stdout).strip()}"
        )
    return result.stdout.strip()


# --- Manifest ------------------------------------------------------------------------------

_REQUIRED_MANIFEST_KEYS = {
    "schema_version", "run_id", "state", "session_owner", "created_at", "updated_at",
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


def _load_manifest(run_id: str) -> dict:
    path = _manifest_path(run_id)
    if not path.is_file():
        raise RootDocsRefreshRunError(f"Run not found: {run_id}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RootDocsRefreshRunError(f"Run manifest is unreadable: {exc}") from exc
    errors = _validate_manifest(data)
    if errors:
        raise RootDocsRefreshRunError(f"Run manifest is invalid: {errors}")
    return data


def _save_manifest(data: dict) -> None:
    data["updated_at"] = _utc()
    errors = _validate_manifest(data)
    if errors:
        raise RootDocsRefreshRunError(f"Refusing to write invalid run manifest: {errors}")
    _write_json(_manifest_path(data["run_id"]), data)


def _event(run_id: str, event_type: str, **fields: Any) -> None:
    path = _run_root(run_id) / "events.jsonl"
    row = {"at": _utc(), "event": event_type, **fields}
    prior = path.read_text(encoding="utf-8") if path.is_file() else ""
    atomic_write(path, prior + json.dumps(row, ensure_ascii=False) + "\n")


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


def _transition(manifest: dict, target: str, *, checkpoint: "str | None" = None) -> None:
    current = manifest["state"]
    if target not in NEXT_STATES.get(current, set()):
        raise RootDocsRefreshRunError(f"Illegal root-docs-refresh-run transition: {current} -> {target}")
    manifest["state"] = target
    if checkpoint:
        manifest.setdefault("stage_checkpoints", {})[checkpoint] = {"state": target, "completed_at": _utc()}
    _save_manifest(manifest)
    _event(manifest["run_id"], "STATE_TRANSITION", previous=current, current=target, checkpoint=checkpoint)


def _transition_abandoned(manifest: dict, *, reason: str) -> None:
    current = manifest["state"]
    if "ABANDONED" not in NEXT_STATES.get(current, set()):
        raise RootDocsRefreshRunError(f"Illegal root-docs-refresh-run transition: {current} -> ABANDONED")
    manifest["state"] = "ABANDONED"
    manifest["failure_reason"] = reason.strip()
    _save_manifest(manifest)
    _event(manifest["run_id"], "STATE_TRANSITION", previous=current, current="ABANDONED")


def _block(manifest: dict, reason: str) -> None:
    current = manifest["state"]
    manifest["resume_state"] = current
    manifest["failure_reason"] = reason.strip()
    _transition(manifest, "BLOCKED")


# --- Checks orchestration --------------------------------------------------------------------


def _load_text(rel_path: str) -> "str | None":
    path = _repo_root / rel_path
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def _run_checks_for_file(rel_path: str) -> dict:
    """Run every applicable root_docs_checks function against one file's current on-disk
    content. Returns {"file": rel_path, "exists": bool, "hard_gate": [...], "heuristic": [...]}."""
    text = _load_text(rel_path)
    if text is None:
        return {"file": rel_path, "exists": False, "hard_gate": [], "heuristic": []}

    findings: list[dict] = []
    findings += checks.check_dead_path_references(text, _repo_root)

    registry_text = _load_text("docs/registries/skills.md")
    if registry_text:
        findings += checks.check_skill_id_references(text, registry_text)

    if rel_path == "GRADE_CONTRACT.md":
        init_text = _load_text("scripts/pipeline/content_eval/__init__.py")
        config_text = _load_text("scripts/pipeline/content_eval/grade_config.yaml")
        if init_text and config_text:
            findings += checks.check_grade_contract_sync(text, init_text, config_text)

    findings += checks.check_volatile_count_hardcoding(text)

    dead_snapshot = checks.check_dead_snapshot_file(_repo_root / rel_path, _repo_root)
    if dead_snapshot:
        findings.append(dead_snapshot)

    return {
        "file": rel_path,
        "exists": True,
        "hard_gate": [f for f in findings if f["tier"] == checks.HARD_GATE],
        "heuristic": [f for f in findings if f["tier"] == checks.HEURISTIC],
    }


def _run_all_checks() -> dict:
    results = [_run_checks_for_file(f) for f in TARGET_FILES]
    total_hard_gate = sum(len(r["hard_gate"]) for r in results)
    total_heuristic = sum(len(r["heuristic"]) for r in results)
    return {
        "checked_at": _utc(),
        "files": results,
        "total_hard_gate": total_hard_gate,
        "total_heuristic": total_heuristic,
    }


def _write_check_results(run_id: str, results: dict) -> None:
    _write_json(_run_root(run_id) / "checks" / "result.json", results)


# --- start: CREATED -> FACTS_PINNED (alias: plan) -------------------------------------------


def plan(*, run_id: "str | None" = None, session_id: "str | None" = None) -> dict:
    """CREATED -> FACTS_PINNED: pin the current git HEAD and every live fact the seven
    files' checks depend on, run the initial check pass, write factpack.json + checks/
    result.json. Returns the validated manifest."""
    owner = _session_id(session_id)
    rid = run_id or f"rdr-{_now().strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:12]}"

    with _guard():
        active_path = _active_path()
        if active_path.is_file():
            try:
                active = json.loads(active_path.read_text(encoding="utf-8"))
                prior = _load_manifest(active["run_id"])
            except Exception as exc:
                raise RootDocsRefreshRunError(f"Existing active-run pointer is invalid: {exc}") from exc
            if prior.get("state") not in TERMINAL_STATES:
                raise RootDocsRefreshRunError(
                    f"root-docs-refresh already has active run {active['run_id']} "
                    f"in state {prior.get('state')} (session {prior.get('session_owner')}) "
                    f"-- another session may be mid-edit on these files"
                )
            _clear_active(active["run_id"])

        run_root = _run_root(rid)
        if run_root.exists():
            raise RootDocsRefreshRunError(f"Run ID already exists: {rid}")
        run_root.mkdir(parents=True)

        try:
            head_sha = _git("rev-parse", "HEAD")
        except RootDocsRefreshRunError:
            head_sha = None

        now = _utc()
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "run_id": rid,
            "state": "CREATED",
            "session_owner": owner,
            "created_at": now,
            "updated_at": now,
            "pinned_inputs": {"git_head_sha": head_sha},
            "stage_checkpoints": {},
        }
        _save_manifest(manifest)
        _event(rid, "RUN_CREATED", session_owner=owner)

        products_text = _load_text("data/products.json")
        active_product_count = None
        if products_text:
            try:
                products = json.loads(products_text)
                active_product_count = sum(1 for p in products if p.get("active"))
            except (json.JSONDecodeError, TypeError):
                active_product_count = None

        results = _run_all_checks()
        factpack = {
            "generated_at": now,
            "git_head_sha": head_sha,
            "active_product_count": active_product_count,
            "check_results": results,
        }
        _write_json(_run_root(rid) / "factpack.json", factpack)
        _write_check_results(rid, results)

        _transition(manifest, "FACTS_PINNED", checkpoint="facts_pinned")
        _set_active(rid)
        return manifest


# --- recheck: no transition, re-runs checks in place ----------------------------------------


def recheck(run_id: str) -> dict:
    """Re-run every check against the seven files' CURRENT on-disk content (after
    remediation edits) and update checks/result.json. Does not transition state -- call this
    after each remediation pass instead of re-planning from scratch."""
    manifest = _load_manifest(run_id)
    if manifest["state"] in TERMINAL_STATES:
        raise RootDocsRefreshRunError(f"Run {run_id} is already terminal ({manifest['state']})")
    results = _run_all_checks()
    _write_check_results(run_id, results)
    _event(run_id, "RECHECK", total_hard_gate=results["total_hard_gate"], total_heuristic=results["total_heuristic"])
    return results


def _latest_check_results(run_id: str) -> dict:
    path = _run_root(run_id) / "checks" / "result.json"
    if not path.is_file():
        raise RootDocsRefreshRunError(f"No check results found for run {run_id} -- run plan/recheck first")
    return json.loads(path.read_text(encoding="utf-8"))


# --- submit: FACTS_PINNED -> AWAITING_REVIEW (hard gate) ------------------------------------


def submit(run_id: str) -> dict:
    """FACTS_PINNED -> AWAITING_REVIEW. Hard gate: raises, listing every blocking finding,
    unless the latest check results show zero HARD_GATE findings across all seven files."""
    manifest = _load_manifest(run_id)
    results = _latest_check_results(run_id)
    if results["total_hard_gate"] > 0:
        blocking = [
            f"{r['file']}: {f['message']}"
            for r in results["files"] for f in r["hard_gate"]
        ]
        raise RootDocsRefreshRunError(
            f"Cannot submit -- {results['total_hard_gate']} HARD_GATE finding(s) remain:\n  "
            + "\n  ".join(blocking)
        )
    _transition(manifest, "AWAITING_REVIEW", checkpoint="submitted")
    return manifest


# --- approve: AWAITING_REVIEW -> APPROVED ----------------------------------------------------


def approve(run_id: str, *, note: str, session_id: "str | None" = None) -> dict:
    """AWAITING_REVIEW -> APPROVED. The skill must never call this on its own initiative --
    only on an explicit, fresh instruction from the user in that turn. Re-verifies the pinned
    git HEAD hasn't moved since plan(); if it has, forces the run back to FACTS_PINNED for
    re-plan rather than approving against a possibly-stale factpack -- this is the direct
    defense against the concurrent-session hazard (another session commits to main between
    this run's plan() and approve())."""
    if not note or not note.strip():
        raise RootDocsRefreshRunError("approve requires a non-empty --note")
    manifest = _load_manifest(run_id)
    _session_id(session_id)  # validate a session identity is present; ownership not enforced globally

    try:
        current_head = _git("rev-parse", "HEAD")
    except RootDocsRefreshRunError:
        current_head = None
    pinned_head = manifest.get("pinned_inputs", {}).get("git_head_sha")
    if pinned_head is not None and current_head != pinned_head:
        _transition(manifest, "FACTS_PINNED", checkpoint="drift_detected")
        raise RootDocsRefreshRunError(
            f"git HEAD moved since plan() (pinned {pinned_head}, now {current_head}) -- "
            f"run forced back to FACTS_PINNED; re-run plan/recheck/submit before approving"
        )

    results = _latest_check_results(run_id)
    if results["total_hard_gate"] > 0:
        raise RootDocsRefreshRunError(
            f"Cannot approve -- {results['total_hard_gate']} HARD_GATE finding(s) present "
            f"in the latest check results; this should not be reachable from AWAITING_REVIEW "
            f"and indicates a file changed after submit() without a recheck()"
        )

    manifest["approval"] = {"note": note.strip(), "approved_at": _utc()}
    _transition(manifest, "APPROVED", checkpoint="approved")
    return manifest


# --- commit_prepare: stays APPROVED, creates override tokens --------------------------------


def commit_prepare(run_id: str, *, changed_files: list[str], reason: str) -> dict:
    """Create one override token per changed file (override_manager.py) so the agent's
    subsequent /commit (S-76) invocation is pre-authorized against path_guard's default-deny
    for root-level writes. Does not transition state and does not touch git -- /commit is an
    agent-executed skill, not something this script can honestly invoke itself."""
    manifest = _load_manifest(run_id)
    if manifest["state"] != "APPROVED":
        raise RootDocsRefreshRunError(f"commit_prepare requires state APPROVED, run is {manifest['state']}")

    token_ids: list[str] = []
    for rel_path in changed_files:
        result = override_manager.cmd_create(argparse.Namespace(
            paths=[rel_path],
            reason=reason,
            plan="moonlit-strolling-sunset.md",
            scope=f"root-docs-refresh run {run_id}",
            operation="edit",
            retroactive=False,
        ))
        if result != 0:
            raise RootDocsRefreshRunError(f"Failed to create override token for {rel_path}")
    # override_manager.cmd_create prints rather than returns the token id; re-derive it by
    # scanning pending/ for the most recently created tokens matching our paths.
    for rel_path in changed_files:
        token = override_manager.find_valid_token_for_path(rel_path)
        if token:
            token_ids.append(token["override_id"])

    manifest["commit_prepare"] = {
        "changed_files": changed_files,
        "override_token_ids": sorted(set(token_ids)),
        "prepared_at": _utc(),
    }
    _save_manifest(manifest)
    _event(run_id, "COMMIT_PREPARED", changed_files=changed_files, token_ids=token_ids)
    return manifest


# --- finalize: APPROVED -> COMMITTED ---------------------------------------------------------


def finalize(run_id: str, *, commit_sha: str) -> dict:
    """APPROVED -> COMMITTED. Call after the agent has actually run /commit (S-76) and the
    changes are pushed. Consumes every override token created by commit_prepare and records
    the resulting commit SHA -- the same retroactive-finalization pattern CLAUDE.md's
    git_plumb_commit.py guidance already uses."""
    manifest = _load_manifest(run_id)
    prepared = manifest.get("commit_prepare", {})
    for token_id in prepared.get("override_token_ids", []):
        try:
            override_manager.cmd_consume(argparse.Namespace(token_id=token_id, commit_sha=commit_sha))
        except Exception:
            pass  # already consumed or missing -- finalize must not fail on a cleanup step
    manifest["commit_sha"] = commit_sha
    _transition(manifest, "COMMITTED", checkpoint="committed")
    _clear_active(run_id)
    return manifest


# --- abandon: any non-terminal -> ABANDONED ---------------------------------------------------


def abandon(run_id: str, *, reason: str) -> dict:
    manifest = _load_manifest(run_id)
    _transition_abandoned(manifest, reason=reason)
    _clear_active(run_id)
    return manifest


def status(run_id: str) -> dict:
    return _load_manifest(run_id)


# --- CLI ---------------------------------------------------------------------------------------


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description="root-docs-refresh run-bound state machine (S-121)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_plan = sub.add_parser("plan", help="CREATED -> FACTS_PINNED: pin facts, run initial checks")
    p_plan.add_argument("--run-id", default=None)
    p_plan.add_argument("--session-id", default=None)

    p_recheck = sub.add_parser("recheck", help="Re-run checks in place, no transition")
    p_recheck.add_argument("--run-id", required=True)

    p_submit = sub.add_parser("submit", help="FACTS_PINNED -> AWAITING_REVIEW (hard gate)")
    p_submit.add_argument("--run-id", required=True)

    p_approve = sub.add_parser("approve", help="AWAITING_REVIEW -> APPROVED")
    p_approve.add_argument("--run-id", required=True)
    p_approve.add_argument("--note", required=True)
    p_approve.add_argument("--session-id", default=None)

    p_prepare = sub.add_parser("commit-prepare", help="Create override tokens for changed files")
    p_prepare.add_argument("--run-id", required=True)
    p_prepare.add_argument("--files", nargs="+", required=True)
    p_prepare.add_argument("--reason", required=True)

    p_finalize = sub.add_parser("finalize", help="APPROVED -> COMMITTED")
    p_finalize.add_argument("--run-id", required=True)
    p_finalize.add_argument("--commit-sha", required=True)

    p_abandon = sub.add_parser("abandon", help="Any non-terminal -> ABANDONED")
    p_abandon.add_argument("--run-id", required=True)
    p_abandon.add_argument("--reason", required=True)

    p_status = sub.add_parser("status", help="Print run manifest")
    p_status.add_argument("--run-id", required=True)

    args = parser.parse_args(argv)

    try:
        if args.command == "plan":
            result = plan(run_id=args.run_id, session_id=args.session_id)
        elif args.command == "recheck":
            result = recheck(args.run_id)
        elif args.command == "submit":
            result = submit(args.run_id)
        elif args.command == "approve":
            result = approve(args.run_id, note=args.note, session_id=args.session_id)
        elif args.command == "commit-prepare":
            result = commit_prepare(args.run_id, changed_files=args.files, reason=args.reason)
        elif args.command == "finalize":
            result = finalize(args.run_id, commit_sha=args.commit_sha)
        elif args.command == "abandon":
            result = abandon(args.run_id, reason=args.reason)
        elif args.command == "status":
            result = status(args.run_id)
        else:
            parser.error(f"unknown command {args.command!r}")
            return 2
    except RootDocsRefreshRunError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
