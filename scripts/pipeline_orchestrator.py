"""pipeline_orchestrator.py -- Stateful pipeline run orchestrator.

Tracks multi-skill pipeline runs through explicit state transitions with
JSON persistence, HITL (Human-In-The-Loop) approval gate integration,
and structured audit logging via ops_log.

State machine:

    PENDING -> RUNNING -> GATE_WAITING -> COMPLETE
                       -> FAILED
               RETRYING (from FAILED, increments attempt counter,
                         then RETRYING -> RUNNING)

Approved gate: GATE_WAITING -> RUNNING (pipeline continues)
Rejected gate: GATE_WAITING -> FAILED

CLI usage (from repo root, using venv interpreter):
    $ .venv/bin/python scripts/pipeline_orchestrator.py start <run_id>
    $ .venv/bin/python scripts/pipeline_orchestrator.py status <run_id>
    $ .venv/bin/python scripts/pipeline_orchestrator.py gate-approve <run_id>
    $ .venv/bin/python scripts/pipeline_orchestrator.py gate-reject <run_id>
    $ .venv/bin/python scripts/pipeline_orchestrator.py complete <run_id>
    $ .venv/bin/python scripts/pipeline_orchestrator.py fail <run_id>
    $ .venv/bin/python scripts/pipeline_orchestrator.py retry <run_id>
    $ .venv/bin/python scripts/pipeline_orchestrator.py run-chain <run_id> \\
          --skills scripts/local_gate.py,scripts/path_guard.py

State is persisted to: runs/.pipeline_state/<run_id>.json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

# Allow imports from scripts/ when run directly
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config_loader import resolve_reports_root  # noqa: E402  # type: ignore[import]
from ops_log import log_entry  # noqa: E402  # type: ignore[import]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = REPO_ROOT / "runs" / ".pipeline_state"
MAX_RETRIES = 3
SKILL_TIMEOUT = 300  # seconds per skill subprocess


# ---------------------------------------------------------------------------
# State definition
# ---------------------------------------------------------------------------

class RunState(str, Enum):
    """Explicit pipeline run states."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    GATE_WAITING = "GATE_WAITING"
    RETRYING = "RETRYING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


# Valid state transitions: source -> allowed targets
_TRANSITIONS: dict[RunState, set[RunState]] = {
    RunState.PENDING:       {RunState.RUNNING},
    RunState.RUNNING:       {RunState.GATE_WAITING, RunState.COMPLETE, RunState.FAILED},
    RunState.GATE_WAITING:  {RunState.RUNNING, RunState.FAILED},
    RunState.RETRYING:      {RunState.RUNNING},
    RunState.FAILED:        {RunState.RETRYING},
    RunState.COMPLETE:      set(),  # terminal
}


# ---------------------------------------------------------------------------
# Core orchestrator class
# ---------------------------------------------------------------------------

class PipelineOrchestrator:
    """Manages state for a single pipeline run.

    Each run has a unique ``run_id``. State is persisted as JSON so the
    orchestrator survives process restarts (checkpoint/resume).

    Parameters
    ----------
    run_id:
        Unique identifier for this pipeline run. Must be filesystem-safe.
    state_dir:
        Override the directory where state JSON files are stored.
    """

    def __init__(self, run_id: str, *, state_dir: Optional[Path] = None) -> None:
        if not run_id or "/" in run_id or "\\" in run_id:
            raise ValueError(
                f"run_id must be a non-empty path-safe string, got {run_id!r}"
            )
        self.run_id = run_id
        self._state_dir = Path(state_dir) if state_dir is not None else STATE_DIR

    def _state_path(self) -> Path:
        return self._state_dir / f"{self.run_id}.json"

    def _load(self) -> dict:
        path = self._state_path()
        if not path.exists():
            raise FileNotFoundError(
                f"No state found for run_id={self.run_id!r} at {path}"
            )
        return json.loads(path.read_text(encoding="utf-8"))

    def _save(self, data: dict) -> Path:
        path = self._state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(path)
        return path

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _log_transition(self, to_state: RunState, reason: str = "") -> None:
        """Write an ops_log entry for this state transition (best-effort)."""
        try:
            if to_state == RunState.FAILED:
                status = "FAIL"
            elif to_state in (RunState.COMPLETE, RunState.RUNNING):
                status = "PASS"
            else:
                status = "WARN"
            log_entry(
                skill="pipeline-orchestrator",
                status=status,
                errors=[reason] if reason else [],
            )
        except Exception:  # pragma: no cover
            pass  # logging failures must never abort orchestration

    def _transition(self, target: RunState, *, reason: str = "") -> dict:
        """Load current state, validate transition, apply, persist, log."""
        data = self._load()
        from_str = data["state"]
        from_state = RunState(from_str)
        if target not in _TRANSITIONS[from_state]:
            allowed = sorted(s.value for s in _TRANSITIONS[from_state])
            raise ValueError(
                f"Invalid transition {from_str!r} -> {target.value!r}. "
                f"Allowed from {from_str!r}: {allowed}"
            )
        data["state"] = target.value
        data["updated_at"] = self._now()
        if target == RunState.RETRYING:
            data["attempt"] = data.get("attempt", 1) + 1
        event: dict = {"ts": self._now(), "from": from_str, "to": target.value}
        if reason:
            event["reason"] = reason
        data.setdefault("events", []).append(event)
        self._save(data)
        self._log_transition(target, reason)
        return data

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def start_run(self, *, metadata: Optional[dict] = None) -> dict:
        """Create a new run and advance it from PENDING to RUNNING.

        Raises FileExistsError if a state file already exists for this run_id.
        """
        path = self._state_path()
        if path.exists():
            raise FileExistsError(
                f"Run {self.run_id!r} already exists. "
                "Use a different run_id or delete the existing state file."
            )
        now = self._now()
        data: dict = {
            "run_id": self.run_id,
            "state": RunState.PENDING.value,
            "created_at": now,
            "updated_at": now,
            "attempt": 1,
            "metadata": metadata or {},
            "events": [{"ts": now, "from": None, "to": RunState.PENDING.value}],
            "skill_queue": [],
            "skill_index": 0,
            "skill_results": [],
            "gate_raised_at": None,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(path)
        return self._transition(RunState.RUNNING)

    def advance_to_gate(self) -> dict:
        """RUNNING -> GATE_WAITING: pipeline reached a HITL approval checkpoint."""
        return self._transition(RunState.GATE_WAITING)

    def approve_gate(self) -> dict:
        """GATE_WAITING -> RUNNING: operator approved; pipeline resumes."""
        return self._transition(RunState.RUNNING, reason="gate approved by operator")

    def reject_gate(self, *, reason: str = "gate rejected by operator") -> dict:
        """GATE_WAITING -> FAILED: operator rejected the gate."""
        return self._transition(RunState.FAILED, reason=reason)

    def complete(self) -> dict:
        """RUNNING -> COMPLETE: pipeline finished successfully."""
        return self._transition(RunState.COMPLETE)

    def fail(self, *, reason: str = "") -> dict:
        """RUNNING -> FAILED: pipeline encountered a terminal error."""
        return self._transition(RunState.FAILED, reason=reason or "pipeline failed")

    def retry(self) -> dict:
        """FAILED -> RETRYING -> RUNNING: operator initiates retry.

        Raises ValueError if the retry budget (MAX_RETRIES) is exhausted.
        """
        data = self._load()
        attempts = data.get("attempt", 1)
        if attempts >= MAX_RETRIES:
            raise ValueError(
                f"Retry budget exhausted for run {self.run_id!r}: "
                f"{attempts}/{MAX_RETRIES} attempts used. "
                "Inspect the failure and start a new run if needed."
            )
        self._transition(RunState.RETRYING)
        return self._transition(RunState.RUNNING)

    def get_status(self) -> dict:
        """Return the current run state dict (read-only)."""
        return self._load()

    def current_state(self) -> RunState:
        """Return the current RunState enum value."""
        return RunState(self._load()["state"])

    def is_terminal(self) -> bool:
        """Return True if the run is in a terminal state (COMPLETE or FAILED)."""
        return self.current_state() in (RunState.COMPLETE, RunState.FAILED)

    # ------------------------------------------------------------------ #
    # Skill execution                                                      #
    # ------------------------------------------------------------------ #

    def load_skills(self, skill_specs: list[dict]) -> dict:
        """Persist a skill queue into the run state.

        Each spec is a dict with keys:
            id (str): Skill identifier for logging (e.g. "S-23").
            script (str): Path to the Python script, relative to repo root.
            args (list[str], optional): Extra CLI args for the script.
            requires_gate (bool, optional): If True, pause for HITL approval
                before executing this skill.

        Raises FileNotFoundError if no state exists for this run.
        Raises ValueError if the run is in a terminal state.
        """
        data = self._load()
        if RunState(data["state"]) in (RunState.COMPLETE, RunState.FAILED):
            raise ValueError(
                f"Cannot load skills into terminal run {self.run_id!r} "
                f"(state={data['state']!r})."
            )
        normalised = []
        for spec in skill_specs:
            normalised.append({
                "id": str(spec.get("id", "")),
                "script": str(spec.get("script", "")),
                "args": list(spec.get("args", [])),
                "requires_gate": bool(spec.get("requires_gate", False)),
            })
        data["skill_queue"] = normalised
        data["skill_index"] = 0
        data["skill_results"] = []
        data["gate_raised_at"] = None
        data["updated_at"] = self._now()
        self._save(data)
        return data

    def execute_next_skill(self) -> dict:
        """Execute the next skill in the queue.

        - If the next skill has ``requires_gate=True`` and the gate has not yet
          been raised for it, transitions to GATE_WAITING and returns. The
          caller must call ``approve_gate()`` (then call this method again) or
          ``reject_gate()``.
        - Runs the skill script via subprocess. On success increments
          ``skill_index`` and logs a PASS entry. On failure transitions to
          FAILED and logs a FAIL entry.
        - If all skills have been executed successfully, transitions to
          COMPLETE.

        Returns the current state dict after the operation.
        Raises ValueError if the run is not in RUNNING state.
        """
        data = self._load()
        state = RunState(data["state"])
        if state != RunState.RUNNING:
            raise ValueError(
                f"execute_next_skill requires RUNNING state, got {state.value!r}. "
                "Call approve_gate() first if in GATE_WAITING."
            )

        queue = data.get("skill_queue", [])
        idx = data.get("skill_index", 0)

        if idx >= len(queue):
            return self.complete()

        spec = queue[idx]
        gate_raised_at = data.get("gate_raised_at")

        # Raise gate before this skill if required (and not already raised for it)
        if spec.get("requires_gate") and gate_raised_at != idx:
            data["gate_raised_at"] = idx
            data["updated_at"] = self._now()
            self._save(data)
            return self._transition(RunState.GATE_WAITING)

        # Run the skill
        script = spec.get("script", "")
        extra_args = spec.get("args", [])
        skill_id = spec.get("id", script)
        cmd = [sys.executable, script] + extra_args

        try:
            proc = subprocess.run(
                cmd,
                cwd=str(REPO_ROOT),
                timeout=SKILL_TIMEOUT,
                capture_output=True,
                text=True,
            )
        except subprocess.TimeoutExpired:
            reason = f"skill {skill_id!r} timed out after {SKILL_TIMEOUT}s"
            self._record_skill_result(data, idx, spec, -1, "", reason)
            self._save(data)  # persist result before transitioning
            try:
                log_entry(skill=skill_id, status="FAIL", errors=[reason])
            except Exception:  # pragma: no cover
                pass
            return self.fail(reason=reason)
        except Exception as exc:
            reason = f"skill {skill_id!r} failed to launch: {exc}"
            self._record_skill_result(data, idx, spec, -1, "", reason)
            self._save(data)  # persist result before transitioning
            try:
                log_entry(skill=skill_id, status="FAIL", errors=[reason])
            except Exception:  # pragma: no cover
                pass
            return self.fail(reason=reason)

        stderr_text = proc.stderr.strip() if proc.stderr else ""
        stdout_text = proc.stdout.strip() if proc.stdout else ""

        if proc.returncode != 0:
            reason = (
                f"skill {skill_id!r} exited {proc.returncode}"
                + (f": {stderr_text[:200]}" if stderr_text else "")
            )
            self._record_skill_result(data, idx, spec, proc.returncode, stdout_text, reason)
            self._save(data)  # persist result before transitioning
            try:
                log_entry(skill=skill_id, status="FAIL", errors=[reason])
            except Exception:  # pragma: no cover
                pass
            return self.fail(reason=reason)

        # Success — advance index and persist
        self._record_skill_result(data, idx, spec, 0, stdout_text, "")
        data["skill_index"] = idx + 1
        data["updated_at"] = self._now()
        self._save(data)
        try:
            log_entry(skill=skill_id, status="PASS")
        except Exception:  # pragma: no cover
            pass

        # If all skills complete, mark run done
        if data["skill_index"] >= len(queue):
            return self.complete()

        return self._load()

    def execute_all_skills(self) -> dict:
        """Drive the skill queue to completion or until a gate or failure.

        Calls ``execute_next_skill()`` in a loop until the run reaches a
        terminal state (COMPLETE or FAILED) or GATE_WAITING (requires operator
        action). Returns the final state dict.
        """
        while True:
            state = self.current_state()
            if state in (RunState.COMPLETE, RunState.FAILED, RunState.GATE_WAITING):
                break
            if state != RunState.RUNNING:
                break
            self.execute_next_skill()
        return self._load()

    @staticmethod
    def _record_skill_result(
        data: dict,
        idx: int,
        spec: dict,
        exit_code: int,
        stdout: str,
        error: str,
    ) -> None:
        """Append a skill result entry (mutates data in place, does not save)."""
        data.setdefault("skill_results", []).append({
            "index": idx,
            "id": spec.get("id", ""),
            "script": spec.get("script", ""),
            "exit_code": exit_code,
            "stdout": stdout[:500] if stdout else "",
            "error": error,
            "logged_at": datetime.now(timezone.utc).isoformat(),
        })


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pipeline_orchestrator",
        description="Manage stateful pipeline run lifecycle.",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    _cmds = [
        ("start",        "Start a new pipeline run.",    False),
        ("status",       "Show current state of a run.", False),
        ("gate-approve", "Approve the HITL gate.",       False),
        ("gate-reject",  "Reject the HITL gate.",        True),
        ("complete",     "Mark run as COMPLETE.",         False),
        ("fail",         "Mark run as FAILED.",           True),
        ("retry",        "Retry a FAILED run.",           False),
    ]
    for name, help_text, has_reason in _cmds:
        p = sub.add_parser(name, help=help_text)
        p.add_argument("run_id", help="Unique run identifier.")
        if has_reason:
            p.add_argument("--reason", default="", help="Optional reason text.")

    # run-chain: start + load skills + execute all
    p_chain = sub.add_parser(
        "run-chain",
        help="Start a run, load a skill chain, and execute to completion.",
    )
    p_chain.add_argument("run_id", help="Unique run identifier.")
    p_chain.add_argument(
        "--skills",
        required=True,
        help=(
            "Comma-separated script paths relative to repo root, "
            "e.g. scripts/local_gate.py,scripts/path_guard.py"
        ),
    )
    p_chain.add_argument(
        "--gate-before",
        default="",
        help=(
            "Comma-separated script paths that should pause for gate approval "
            "before execution, e.g. scripts/pre_write.py"
        ),
    )

    return parser


def main(argv: "list[str] | None" = None) -> int:
    """CLI entry point. Returns exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        orch = PipelineOrchestrator(args.run_id)

        if args.command == "start":
            data = orch.start_run()
            print(f"Run {args.run_id!r} started. State: {data['state']}")

        elif args.command == "status":
            print(json.dumps(orch.get_status(), indent=2))

        elif args.command == "gate-approve":
            data = orch.approve_gate()
            print(f"Gate approved. State: {data['state']}")

        elif args.command == "gate-reject":
            reason = getattr(args, "reason", "") or "gate rejected by operator"
            data = orch.reject_gate(reason=reason)
            print(f"Gate rejected. State: {data['state']}")

        elif args.command == "complete":
            orch.complete()
            print(f"Run {args.run_id!r} marked COMPLETE.")

        elif args.command == "fail":
            reason = getattr(args, "reason", "")
            orch.fail(reason=reason)
            print(f"Run {args.run_id!r} marked FAILED.")

        elif args.command == "retry":
            data = orch.retry()
            print(f"Retry started. State: {data['state']}, Attempt: {data['attempt']}")

        elif args.command == "run-chain":
            gate_before = set(
                s.strip() for s in args.gate_before.split(",") if s.strip()
            )
            skill_specs = []
            for script in args.skills.split(","):
                script = script.strip()
                if not script:
                    continue
                skill_specs.append({
                    "id": Path(script).stem,
                    "script": script,
                    "args": [],
                    "requires_gate": script in gate_before,
                })
            data = orch.start_run()
            orch.load_skills(skill_specs)
            data = orch.execute_all_skills()
            print(f"Run {args.run_id!r} finished. State: {data['state']}")
            if data.get("skill_results"):
                for r in data["skill_results"]:
                    status = "OK" if r["exit_code"] == 0 else "FAIL"
                    print(f"  [{status}] {r['id']} (exit {r['exit_code']})")
            if data["state"] == RunState.GATE_WAITING.value:
                idx = data.get("skill_index", 0)
                queue = data.get("skill_queue", [])
                pending = queue[idx]["id"] if idx < len(queue) else "?"
                print(
                    f"  Paused at gate before skill {pending!r}. "
                    "Run gate-approve to continue."
                )
                return 2  # special exit code: gate waiting

    except (FileNotFoundError, FileExistsError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
