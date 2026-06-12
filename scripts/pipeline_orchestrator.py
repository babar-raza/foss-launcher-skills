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

State is persisted to: runs/.pipeline_state/<run_id>.json
"""
from __future__ import annotations

import argparse
import json
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

    except (FileNotFoundError, FileExistsError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
