"""CONTRACT: I/O wrapper for the /forensic-heal-sprint skill (S-123), Waves 4-5 of
MISSION MT025-2026-08-08-FORENSIC-BLIND-SPOT-HEAL-SKILLS.

Purpose: consume a mission's already-bound schema-5f taskcards (typically emitted by S-122
blind-spot-audit's bind-taskcards) and drive them through system-heal -> content-regen ->
verify -> harden -> reverify -> pilot -> re-audit -> adversarial-review -> close, per the
plan (C:\\Users\\prora\\.claude\\plans\\typed-snuggling-peach.md).

Wave 4 shipped the two load-bearing primitives -- `status` (derived sprint-state
aggregation) and `gate` (the system-before-content invariant) -- plus `advance-taskcard`, a
thin CAS-protected wrapper over TaskcardStore.update_taskcard_status(). Wave 5 adds
`pilot-check` (scripts/pipeline/lib/forensic_heal/pilot_chain.py), `adversarial-review`
(scripts/pipeline/lib/forensic_heal/adversarial_probes.py, 12 probes + independence
enforcement), `compute-verdict` (scripts/pipeline/lib/forensic_heal/verdict.py, computed
never asserted), and `close` -- which requires a computed verdict and appends one row to
the TRACKED `docs/governance/forensic-heal-history.md` ledger (the only durable, cross-clone
record, since reports/, .local/, and plans/ are all git-ignored). This module has no
manifest, no run_id, and no ACTIVE.json: unlike S-122, it has no per-run irreversible
artifact of its own (its only mutations are taskcard rows, already CAS-protected by
taskcard_store.py, and the one append-only tracked ledger file) and it is not a parallel
tracker -- its whole state is TaskcardStore's, recomputed fresh on every call.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
_FORENSIC_HEAL_DIR = str(_PIPELINE_ROOT / "lib" / "forensic_heal")
if _FORENSIC_HEAL_DIR not in sys.path:
    sys.path.insert(0, _FORENSIC_HEAL_DIR)

import session_identity  # noqa: E402
from core.fs import atomic_write  # noqa: E402
from taskcard_store import TaskcardStore, TaskcardCASError, TaskcardNotFoundError  # noqa: E402
import sprint_state  # noqa: E402
import pilot_chain  # noqa: E402
import adversarial_probes  # noqa: E402
import verdict as verdict_module  # noqa: E402

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
_repo_root = _DEFAULT_REPO_ROOT
_now: "Callable[[], datetime]" = lambda: datetime.now(timezone.utc)


def configure(
    *, repo_root: "Path | str | None" = None, now: "Callable[[], datetime] | None" = None,
) -> None:
    """Override the repo root (and, for tests, the clock) for tests; call without
    arguments to reset."""
    global _repo_root, _now
    _repo_root = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    _now = now or (lambda: datetime.now(timezone.utc))


def _utc() -> str:
    return _now().astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _history_ledger_path() -> Path:
    return _repo_root / "docs" / "governance" / "forensic-heal-history.md"


class ForensicHealSprintRunError(RuntimeError):
    """Raised when a taskcard operation or gate check cannot proceed safely."""


def _session_id(explicit: "str | None" = None) -> str:
    value = session_identity.resolve_sanitized(explicit)
    if not value:
        raise ForensicHealSprintRunError(
            "A stable session identity is required: pass --session-id or set "
            "AGENT_SESSION_ID/CODEX_THREAD_ID/CLAUDE_CODE_SESSION_ID"
        )
    return value


def _load_cards(mission_id: str) -> dict:
    store = TaskcardStore(mission_id, repo_root=_repo_root)
    cards = store.read_latest()
    if not cards:
        raise ForensicHealSprintRunError(f"No taskcards found for mission {mission_id!r} at {store.path}")
    return cards


def status(mission_id: str, *, task_ids: "list[str] | None" = None) -> dict:
    """Derived sprint-state aggregation over the mission's real taskcards."""
    cards = _load_cards(mission_id)
    try:
        return sprint_state.compute_sprint_state(cards, task_ids=task_ids)
    except ValueError as exc:
        raise ForensicHealSprintRunError(str(exc)) from exc


def gate(mission_id: str, *, task_ids: "list[str] | None" = None) -> dict:
    """The system-before-content gate. Does not raise on failure -- returns
    {"passed": False, ...} so a caller can inspect blocking_cards; use --fail-on-block on the
    CLI (or check result["passed"] yourself in Python) to turn a failure into an error."""
    cards = _load_cards(mission_id)
    return sprint_state.check_system_before_content_gate(cards, task_ids=task_ids)


def advance_taskcard(
    mission_id: str, task_id: str, *, expected_status: str, new_status: str,
    evidence_refs: "list[str]", session_id: "str | None" = None,
) -> dict:
    """CAS-protected advance of one taskcard. Refuses (does not silently overwrite) if
    the card's actual current status has already moved past expected_status -- the same
    guarantee TaskcardStore.update_taskcard_status() provides, surfaced here with a
    forensic-heal-sprint-specific error message."""
    owner = _session_id(session_id)
    store = TaskcardStore(mission_id, repo_root=_repo_root)
    try:
        return store.update_taskcard_status(
            task_id, expected_status=expected_status, new_status=new_status,
            recorded_by=owner, evidence_refs=evidence_refs,
        )
    except TaskcardCASError as exc:
        raise ForensicHealSprintRunError(
            f"CAS refusal advancing {task_id}: expected {expected_status!r}, actual status "
            f"is {exc.actual!r} (last recorded by {exc.recorded_by!r}) -- reload and retry, "
            f"never blind-overwrite"
        ) from exc
    except TaskcardNotFoundError as exc:
        raise ForensicHealSprintRunError(str(exc)) from exc


def pilot_check(chain: dict) -> dict:
    """Thin pass-through to pilot_chain.resolve_pilot_chain() -- kept as a module-level
    function so the CLI and any future orchestration call one stable name."""
    return pilot_chain.resolve_pilot_chain(chain)


def adversarial_review(
    evidence_bundle: dict, *, sealing_session_id: str, reviewer_session_id: "str | None" = None,
    prior_dispositions: "dict[str, str] | None" = None,
) -> dict:
    """Runs the 12 adversarial probes. reviewer_session_id defaults to the caller's own
    resolved session identity if not given explicitly -- but note that still requires it to
    differ from sealing_session_id; passing the SAME session for both is refused either way,
    by design (see adversarial_probes.run_adversarial_review)."""
    reviewer = _session_id(reviewer_session_id)
    try:
        return adversarial_probes.run_adversarial_review(
            evidence_bundle, sealing_session_id=sealing_session_id, reviewer_session_id=reviewer,
            prior_dispositions=prior_dispositions,
        )
    except adversarial_probes.AdversarialReviewError as exc:
        raise ForensicHealSprintRunError(str(exc)) from exc


def compute_verdict(
    mission_id: str, *, gate_passed: bool, pilot_chain_resolved: bool,
    adversarial_review_result: dict, unaided_first_override: "dict | None" = None,
    task_ids: "list[str] | None" = None,
) -> dict:
    """Computes the final verdict from this mission's REAL current sprint state plus the
    caller-supplied gate/pilot/adversarial results -- never an asserted field."""
    sprint = status(mission_id, task_ids=task_ids)
    return verdict_module.compute_verdict(
        sprint_state=sprint, gate_passed=gate_passed, pilot_chain_resolved=pilot_chain_resolved,
        adversarial_review=adversarial_review_result, unaided_first_override=unaided_first_override,
    )


_HISTORY_HEADER = (
    "# Forensic Heal Sprint History\n\n"
    "> Tracked, cross-clone-durable summary of every closed S-123 forensic-heal-sprint run. "
    "The only durable record of these runs -- `reports/`, `.local/`, and `plans/` are all "
    "git-ignored, so a fresh clone would otherwise have no trail at all. One row per closed "
    "sprint, appended by `forensic_heal_sprint_run.py close`, never hand-edited.\n\n"
    "| Mission ID | Closed At | Products | Taskcards Closed/Total | Unaided-First Verdict | "
    "System Recall | Final Verdict |\n"
    "|---|---|---|---|---|---|---|\n"
)


def _ensure_history_ledger() -> Path:
    path = _history_ledger_path()
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(path, _HISTORY_HEADER)
    return path


def append_history_row(
    mission_id: str, *, products: "list[str]", taskcards_closed: int, taskcards_total: int,
    unaided_first_verdict: str, system_recall: "float | None", final_verdict: str,
) -> str:
    """Append one row to the tracked docs/governance/forensic-heal-history.md ledger.
    Returns the row as written. Never rewrites prior rows -- append-only, matching every
    other evidence ledger this mission uses."""
    path = _ensure_history_ledger()
    recall_str = f"{system_recall:.0%}" if system_recall is not None else "n/a"
    row = (
        f"| {mission_id} | {_utc()} | {', '.join(products)} | {taskcards_closed}/{taskcards_total} | "
        f"{unaided_first_verdict} | {recall_str} | {final_verdict} |\n"
    )
    current = path.read_text(encoding="utf-8")
    atomic_write(path, current + row)
    return row


def close(
    mission_id: str, *, products: "list[str]", gate_passed: bool, pilot_chain_resolved: bool,
    adversarial_review_result: dict, unaided_first_verdict: str, system_recall: "float | None",
    unaided_first_override: "dict | None" = None, task_ids: "list[str] | None" = None,
) -> dict:
    """Compute the final verdict and, REGARDLESS of what it is (including
    SYSTEM_NOT_READY_REWORK_REQUIRED and BLOCKED_EXTERNAL -- a sprint that did not succeed
    is still a real, tracked outcome, not something to hide), append one row to the tracked
    history ledger. Returns {"verdict": {...}, "history_row": str}."""
    sprint = status(mission_id, task_ids=task_ids)
    result = verdict_module.compute_verdict(
        sprint_state=sprint, gate_passed=gate_passed, pilot_chain_resolved=pilot_chain_resolved,
        adversarial_review=adversarial_review_result, unaided_first_override=unaided_first_override,
    )
    cards = _load_cards(mission_id)
    selected = cards if task_ids is None else {tid: cards[tid] for tid in task_ids}
    closed_count = sum(1 for c in selected.values() if c["status"] == "CLOSED")
    row = append_history_row(
        mission_id, products=products, taskcards_closed=closed_count, taskcards_total=len(selected),
        unaided_first_verdict=unaided_first_verdict, system_recall=system_recall,
        final_verdict=result["final_verdict"],
    )
    return {"verdict": result, "history_row": row}


# --- CLI -----------------------------------------------------------------------------------


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description="forensic-heal-sprint taskcard operations (S-123)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_status = sub.add_parser("status", help="Derived sprint-state aggregation")
    p_status.add_argument("--mission-id", required=True)
    p_status.add_argument("--task-ids", nargs="*", default=None)

    p_gate = sub.add_parser("gate", help="System-before-content gate check")
    p_gate.add_argument("--mission-id", required=True)
    p_gate.add_argument("--task-ids", nargs="*", default=None)
    p_gate.add_argument("--fail-on-block", action="store_true", help="Exit 1 if the gate does not pass")

    p_advance = sub.add_parser("advance-taskcard", help="CAS-protected taskcard status advance")
    p_advance.add_argument("--mission-id", required=True)
    p_advance.add_argument("--task-id", required=True)
    p_advance.add_argument("--expected-status", required=True)
    p_advance.add_argument("--new-status", required=True)
    p_advance.add_argument("--evidence", nargs="+", required=True, dest="evidence_refs")
    p_advance.add_argument("--session-id", default=None)

    p_pilot = sub.add_parser("pilot-check", help="Resolve the 7-link pilot chain")
    p_pilot.add_argument("--chain-file", required=True, help="JSON file with the chain fields")

    p_adversarial = sub.add_parser("adversarial-review", help="Run the 12 adversarial probes")
    p_adversarial.add_argument("--evidence-file", required=True, help="JSON file: {probe_id: evidence}")
    p_adversarial.add_argument("--sealing-session-id", required=True)
    p_adversarial.add_argument("--reviewer-session-id", default=None)
    p_adversarial.add_argument("--prior-dispositions-file", default=None)

    p_verdict = sub.add_parser("compute-verdict", help="Compute the final dual verdict")
    p_verdict.add_argument("--mission-id", required=True)
    p_verdict.add_argument("--task-ids", nargs="*", default=None)
    p_verdict.add_argument("--gate-passed", required=True, choices=["true", "false"])
    p_verdict.add_argument("--pilot-resolved", required=True, choices=["true", "false"])
    p_verdict.add_argument("--adversarial-review-file", required=True)
    p_verdict.add_argument("--unaided-first-override-file", default=None)

    p_close = sub.add_parser("close", help="Compute the verdict and append the tracked history row")
    p_close.add_argument("--mission-id", required=True)
    p_close.add_argument("--task-ids", nargs="*", default=None)
    p_close.add_argument("--products", nargs="+", required=True)
    p_close.add_argument("--gate-passed", required=True, choices=["true", "false"])
    p_close.add_argument("--pilot-resolved", required=True, choices=["true", "false"])
    p_close.add_argument("--adversarial-review-file", required=True)
    p_close.add_argument("--unaided-first-verdict", required=True)
    p_close.add_argument("--system-recall", type=float, default=None)
    p_close.add_argument("--unaided-first-override-file", default=None)

    args = parser.parse_args(argv)

    try:
        if args.command == "status":
            result = status(args.mission_id, task_ids=args.task_ids)
        elif args.command == "gate":
            result = gate(args.mission_id, task_ids=args.task_ids)
            if args.fail_on_block and not result["passed"]:
                print(json.dumps(result, indent=2, ensure_ascii=False))
                return 1
        elif args.command == "advance-taskcard":
            result = advance_taskcard(
                args.mission_id, args.task_id, expected_status=args.expected_status,
                new_status=args.new_status, evidence_refs=args.evidence_refs,
                session_id=args.session_id,
            )
        elif args.command == "pilot-check":
            chain = json.loads(Path(args.chain_file).read_text(encoding="utf-8"))
            result = pilot_check(chain)
        elif args.command == "adversarial-review":
            evidence_bundle = json.loads(Path(args.evidence_file).read_text(encoding="utf-8"))
            prior = None
            if args.prior_dispositions_file:
                prior = json.loads(Path(args.prior_dispositions_file).read_text(encoding="utf-8"))
            result = adversarial_review(
                evidence_bundle, sealing_session_id=args.sealing_session_id,
                reviewer_session_id=args.reviewer_session_id, prior_dispositions=prior,
            )
        elif args.command == "compute-verdict":
            adversarial_result = json.loads(Path(args.adversarial_review_file).read_text(encoding="utf-8"))
            override = None
            if args.unaided_first_override_file:
                override = json.loads(Path(args.unaided_first_override_file).read_text(encoding="utf-8"))
            result = compute_verdict(
                args.mission_id, gate_passed=args.gate_passed == "true",
                pilot_chain_resolved=args.pilot_resolved == "true",
                adversarial_review_result=adversarial_result, unaided_first_override=override,
                task_ids=args.task_ids,
            )
        elif args.command == "close":
            adversarial_result = json.loads(Path(args.adversarial_review_file).read_text(encoding="utf-8"))
            override = None
            if args.unaided_first_override_file:
                override = json.loads(Path(args.unaided_first_override_file).read_text(encoding="utf-8"))
            result = close(
                args.mission_id, products=args.products, gate_passed=args.gate_passed == "true",
                pilot_chain_resolved=args.pilot_resolved == "true",
                adversarial_review_result=adversarial_result,
                unaided_first_verdict=args.unaided_first_verdict, system_recall=args.system_recall,
                unaided_first_override=override, task_ids=args.task_ids,
            )
        else:
            parser.error(f"unknown command {args.command!r}")
            return 2
    except ForensicHealSprintRunError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
