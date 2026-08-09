"""CONTRACT: fix-plan -> schema-5f taskcard conversion for S-122 (blind-spot-audit), Wave 3
of MISSION MT025-2026-08-08-FORENSIC-BLIND-SPOT-HEAL-SKILLS.

Purpose: the emit half of the pasted mission spec's "convert every fix into a taskcard"
rule, targeting this repo's REAL taskcard mechanism (schema 5f / TaskcardStore /
reports/plan_state/{mission_id}/taskcards.jsonl) instead of inventing a parallel one -- see
plan typed-snuggling-peach.md's explicit rejection of the spec's own `09-taskcards/*.yaml`
scheme. This module only shapes and validates records; scripts/pipeline/lib/
taskcard_store.py remains the sole writer (append()/update_taskcard_status()).

The consume half -- S-123 driving these cards through IN_PROGRESS -> IMPLEMENTED ->
... -> CLOSED -- is Wave 4's job and is thin enough (direct
TaskcardStore.update_taskcard_status() calls from forensic_heal_sprint_run.py) that it does
not need its own bridge function; only the emit direction (fix-plan item -> valid schema-5f
row) has real shaping/validation work to do.
"""
from __future__ import annotations

import sys
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parents[1]
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from schema_validators import validate_taskcard_record  # noqa: E402

PRIORITIES: "frozenset[str]" = frozenset({"P0", "P1", "P2", "P3", "P4"})


def build_taskcard(
    task_id: str, mission_id: str, *, recorded_at: str, recorded_by: str, title: str,
    root_cause_id: str, finding_ids: "list[str]", layer: str, priority: str,
    allowed_paths: "list[str]", verification_commands: "list[str]", rollback: str,
    forbidden_paths: "list[str] | None" = None,
    affected_content_paths: "list[str] | None" = None,
    regeneration_required: bool = False,
) -> dict:
    """Build one schema-5f taskcard row at status TODO from a chosen fix-plan item.

    Raises ValueError (not a silent best-effort shape) when priority is invalid, or when
    allowed_paths/verification_commands/rollback are empty -- an un-scoped, unverifiable,
    or unrecoverable taskcard is exactly the "too vague" failure mode the plan's Taskcard
    Readiness Checklist exists to catch, and this is the machine-checkable slice of it.
    """
    if priority not in PRIORITIES:
        raise ValueError(f"{task_id}: invalid priority {priority!r}, must be one of {sorted(PRIORITIES)}")
    if not allowed_paths:
        raise ValueError(f"{task_id}: allowed_paths must be non-empty")
    if not verification_commands:
        raise ValueError(f"{task_id}: verification_commands must be non-empty")
    if not rollback or not rollback.strip():
        raise ValueError(f"{task_id}: rollback must be non-empty")
    if not finding_ids:
        raise ValueError(f"{task_id}: finding_ids must be non-empty (a taskcard traces to real findings)")

    record = {
        "task_id": task_id,
        "mission_id": mission_id,
        "status": "TODO",
        "recorded_at": recorded_at,
        "recorded_by": recorded_by,
        "evidence_refs": [],
        "title": title,
        "root_cause_id": root_cause_id,
        "finding_ids": list(finding_ids),
        "layer": layer,
        "priority": priority,
        "allowed_paths": list(allowed_paths),
        "forbidden_paths": list(forbidden_paths or []),
        "verification_commands": list(verification_commands),
        "rollback": rollback.strip(),
        "regeneration_required": bool(regeneration_required),
        "affected_content_paths": list(affected_content_paths or []),
    }
    errors = validate_taskcard_record(record)
    if errors:
        raise ValueError(f"{task_id}: invalid schema-5f record: {errors}")
    return record


def build_taskcards_from_fix_plan(
    fix_plan_items: "list[dict]", *, mission_id: str, recorded_at: str, recorded_by: str,
    task_id_prefix: str,
) -> "list[dict]":
    """Build one taskcard per fix-plan item, IDs `{task_id_prefix}-01`, `-02`, ... in
    input order. Each item dict must supply every build_taskcard() keyword except task_id/
    mission_id/recorded_at/recorded_by."""
    cards = []
    for i, item in enumerate(fix_plan_items, start=1):
        task_id = f"{task_id_prefix}-{i:02d}"
        cards.append(build_taskcard(
            task_id, mission_id, recorded_at=recorded_at, recorded_by=recorded_by, **item,
        ))
    return cards
