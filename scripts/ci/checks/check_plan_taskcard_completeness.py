#!/usr/bin/env python3
"""check_plan_taskcard_completeness.py — plan step coverage vs. taskcards.jsonl.

CONTEXT (2026-08-06 first-principles assessment, "MT023 silent step-drop"):
check_taskcard_plan_parity.py (RPR-G-04) deliberately treats an untagged plan
step as SILENCE, never a contradiction -- correct for its purpose (avoiding a
brittle prose-status gate), but it means a step that was never given a
taskcard row at all is invisible to it BY DESIGN, not by bug. A real plan
(the media-optimize dual-format redesign, `~/.claude/plans/
magical-inventing-book.md`) had 9 numbered "Execution order" steps; only 6
taskcards (`TC-MEDIA-01`..`06`) were ever created for the same mission. Step
9 -- "resume the paused .supervisor MT023 convergence audit" -- was silently
dropped in that manual, unverified plan-to-taskcard translation, and nothing
in this repo's governance stack (plan-health-watchdog, plan-normalize, the
parity checker above) is designed to catch an OMISSION, only a
CONTRADICTION or multi-day STALENESS. See
docs/governance/planning-methodology.md for the design rationale.

This check closes that specific, narrow gap: it counts a plan's own
"Execution order" numbered steps and compares that count against the number
of distinct task_ids recorded for the mission's taskcards.jsonl. It CANNOT
determine which individual step lacks a card without per-step tags (most
existing plans, including the one that motivated this check, don't carry
them) -- so it is deliberately coarse: a count-based completeness signal,
not a precise mapping. That coarseness is enough to have caught the actual
incident (9 steps, 6 cards) and is honest about its own limit rather than
pretending to more precision than it has.

Scope: only plans that carry an explicit "## Execution order" (or "###...",
case-insensitive) heading are checked -- a plan without one has nothing this
check can evaluate, and that is a PASS (exit 0), not an error. This mirrors
check_taskcard_plan_parity.py's own restraint about not forcing every plan
into one rigid shape (docs/governance/planning-methodology.md "Non-goals").

Per-step opt-out: a step line may carry an inline
`<!-- NOT-TRACKED: reason -->` marker to exclude it from the required count
(e.g. a step that is prose-only guidance, not a discrete unit of work) --
the same opt-out-tag idiom used elsewhere in this repo's governance rather
than a rigid, unescapable gate.

ENFORCEMENT STATUS: agent-invoked (via /plan-health-watchdog, S-113), NOT a
CI gate -- for the same structural reason check_taskcard_plan_parity.py
isn't one: plan files live in ~/.claude/plans/, outside the repo, so CI
cannot reach the --plan-file it requires.

Exit codes:
  0 — no "Execution order" section found (nothing to check), or step count
      is fully covered by the mission's distinct taskcard count
  1 — step count exceeds distinct taskcard count (incomplete coverage)
  2 — a required input file is missing/unparseable
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_SECTION_HEADING = re.compile(r"^#{1,6}\s*execution order\s*$", re.IGNORECASE)
_ANY_HEADING = re.compile(r"^#{1,6}\s")
_NUMBERED_STEP = re.compile(r"^\s*\d+\.\s+(.*)$")
_NOT_TRACKED_TAG = re.compile(r"<!--\s*NOT-TRACKED\s*:\s*[^>]*-->", re.IGNORECASE)


def extract_execution_steps(plan_text: str) -> "list[str] | None":
    """Return the plan's numbered "Execution order" step lines, or None if
    no such section exists (nothing for this check to evaluate).

    Steps carrying an inline <!-- NOT-TRACKED: reason --> marker are
    excluded from the returned list -- they are explicitly exempted from
    completeness tracking, not silently missed.
    """
    lines = plan_text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if _SECTION_HEADING.match(line.strip()):
            start = i + 1
            break
    if start is None:
        return None

    steps: list[str] = []
    for line in lines[start:]:
        if _ANY_HEADING.match(line):
            break  # next section — execution order list has ended
        m = _NUMBERED_STEP.match(line)
        if not m:
            continue
        if _NOT_TRACKED_TAG.search(line):
            continue  # explicit opt-out
        steps.append(m.group(1).strip())
    return steps


def load_distinct_task_ids(path: Path) -> set[str]:
    """Distinct task_ids ever recorded for a mission (any status counts —
    this check measures whether a step was REGISTERED at all, not whether
    it finished; PAUSED, TODO, and CLOSED all equally prove registration)."""
    ids: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        tid = obj.get("task_id")
        if tid:
            ids.add(tid)
    return ids


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Plan 'Execution order' step count vs. taskcards.jsonl coverage."
    )
    parser.add_argument("--plan-file", required=True, help="Path to the plan markdown")
    parser.add_argument("--taskcards", required=True, help="Path to the mission's taskcards.jsonl")
    args = parser.parse_args(argv)

    plan_path, store_path = Path(args.plan_file), Path(args.taskcards)
    if not plan_path.is_file():
        print(f"ERROR: plan file not found: {plan_path}", file=sys.stderr)
        return 2
    if not store_path.is_file():
        print(f"ERROR: taskcards file not found: {store_path}", file=sys.stderr)
        return 2

    try:
        plan_text = plan_path.read_text(encoding="utf-8")
        steps = extract_execution_steps(plan_text)
        task_ids = load_distinct_task_ids(store_path)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"ERROR: could not parse inputs: {exc}", file=sys.stderr)
        return 2

    if steps is None:
        print("OK: no 'Execution order' section found; nothing to check.")
        return 0

    step_count, card_count = len(steps), len(task_ids)
    if step_count <= card_count:
        print(
            f"OK: {step_count} execution-order step(s) <= {card_count} distinct "
            f"taskcard(s); coverage looks complete."
        )
        return 0

    deficit = step_count - card_count
    print(
        f"PLAN/TASKCARD COMPLETENESS: {step_count} execution-order step(s) but only "
        f"{card_count} distinct taskcard(s) recorded for this mission — at least "
        f"{deficit} step(s) may have no durable record at all."
    )
    print("Execution-order steps found:")
    for i, step in enumerate(steps, start=1):
        print(f"  {i}. {step[:100]}")
    print(
        "Tag steps that are genuinely not discrete tracked work with "
        "<!-- NOT-TRACKED: reason -->, or create a taskcard for each real step, "
        "before treating this plan as ready to execute."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
