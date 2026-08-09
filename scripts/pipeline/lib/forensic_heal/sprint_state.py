"""CONTRACT: derived sprint-state aggregation and system-before-content gate for S-123
(forensic-heal-sprint), Wave 4 of MISSION MT025-2026-08-08-FORENSIC-BLIND-SPOT-HEAL-SKILLS.

Purpose: S-123 has no independent "run state" -- AGENTS.md section 17 forbids a parallel
tracker alongside taskcard schema 5f. This module computes a sprint's aggregate state ON
DEMAND from a mission's real taskcards (TaskcardStore.read_latest()), and enforces the one
genuinely new invariant this skill exists for: every SYSTEM_LAYERS taskcard (script, prompt,
validator, governance_doc, skill -- i.e. everything except "data") must reach IMPLEMENTED
before content-layer work may begin. Pure functions operating on plain dicts, so tests never
need a real TaskcardStore/file I/O -- forensic_heal_sprint_run.py is the thin I/O wrapper
that loads real cards and calls these.
"""
from __future__ import annotations

# Ordinal progress ordering (schema 5f's "advancing" statuses only). Exception states
# (REWORK_REQUIRED, BLOCKED_LOCAL, BLOCKED_EXTERNAL) are NOT part of this linear order -- a
# card in one of them forces the whole aggregate to that exception state directly,
# regardless of how far other cards have progressed. SUPERSEDED/OUT_OF_SCOPE cards are
# excluded from the aggregate entirely (no longer part of active progress).
_PROGRESS_ORDER: "tuple[str, ...]" = (
    "TODO", "READY", "IN_PROGRESS", "IMPLEMENTED", "FOCUSED_VERIFIED",
    "INTEGRATION_VERIFIED", "END_TO_END_VERIFIED", "PILOT_PROVEN",
    "INDEPENDENTLY_REVIEWED", "CLOSED",
)
_PROGRESS_RANK = {status: i for i, status in enumerate(_PROGRESS_ORDER)}
_EXCLUDED_FROM_AGGREGATE: "frozenset[str]" = frozenset({"SUPERSEDED", "OUT_OF_SCOPE"})
_EXCEPTION_STATUSES: "frozenset[str]" = frozenset({"REWORK_REQUIRED", "BLOCKED_LOCAL", "BLOCKED_EXTERNAL"})
# Reported in this order when more than one exception type is present in scope --
# BLOCKED_EXTERNAL first, since it is the least locally-resolvable and should dominate the
# operator's attention over a REWORK_REQUIRED card that just needs another local pass.
_EXCEPTION_PRIORITY: "tuple[str, ...]" = ("BLOCKED_EXTERNAL", "BLOCKED_LOCAL", "REWORK_REQUIRED")

# Taskcard `layer` values that must reach IMPLEMENTED before content-layer work begins.
# "data" (root_cause_model.LAYERS' remaining value) is deliberately excluded -- a data-layer
# root cause (e.g. a stale JSON config) does not gate content regeneration the way a
# script/prompt/validator/governance_doc bug does. A card with a missing/unrecognized layer
# is NOT treated as system-layer (fails open, not closed) -- every card S-122 emits always
# sets layer explicitly (taskcard_bridge.build_taskcard has no default), so this only matters
# for hand-authored taskcards outside this skill's own emission path.
SYSTEM_LAYERS: "frozenset[str]" = frozenset({"script", "prompt", "validator", "governance_doc", "skill"})
_IMPLEMENTED_RANK = _PROGRESS_RANK["IMPLEMENTED"]


def _select_cards(all_cards: dict, task_ids: "list[str] | None") -> dict:
    if task_ids is None:
        return dict(all_cards)
    missing = set(task_ids) - set(all_cards)
    if missing:
        raise ValueError(f"task_ids not found in taskcard store: {sorted(missing)}")
    return {tid: all_cards[tid] for tid in task_ids}


def compute_sprint_state(all_cards: dict, *, task_ids: "list[str] | None" = None) -> dict:
    """Aggregate sprint state over the given (or all) taskcards.

    Returns {"aggregate_status": str, "in_scope_task_ids": [...], "excluded_task_ids": [...],
             "exception_task_ids": {"BLOCKED_EXTERNAL": [...], ...}}.

    Raises ValueError if the in-scope set is empty (no cards to aggregate, or an explicit
    task_ids selection referencing an unknown task_id) -- an empty aggregate silently
    reporting some default status would be worse than refusing.
    """
    selected = _select_cards(all_cards, task_ids)
    in_scope = {tid: c for tid, c in selected.items() if c["status"] not in _EXCLUDED_FROM_AGGREGATE}
    excluded = [tid for tid, c in selected.items() if c["status"] in _EXCLUDED_FROM_AGGREGATE]
    if not in_scope:
        raise ValueError("no in-scope taskcards to aggregate (all excluded, or empty selection)")

    exceptions: "dict[str, list[str]]" = {}
    for tid, c in in_scope.items():
        if c["status"] in _EXCEPTION_STATUSES:
            exceptions.setdefault(c["status"], []).append(tid)

    if exceptions:
        aggregate = next(status for status in _EXCEPTION_PRIORITY if status in exceptions)
    else:
        min_rank = min(_PROGRESS_RANK[c["status"]] for c in in_scope.values())
        aggregate = _PROGRESS_ORDER[min_rank]

    return {
        "aggregate_status": aggregate,
        "in_scope_task_ids": sorted(in_scope),
        "excluded_task_ids": sorted(excluded),
        "exception_task_ids": exceptions,
    }


def check_system_before_content_gate(all_cards: dict, *, task_ids: "list[str] | None" = None) -> dict:
    """The one load-bearing new invariant S-123 enforces: every in-scope SYSTEM_LAYERS
    taskcard must be at IMPLEMENTED or later (and not in an exception status) before
    content-layer work may begin.

    Returns {"passed": bool, "blocking_cards": [{"task_id", "layer", "status"}]}.
    """
    selected = _select_cards(all_cards, task_ids)
    blocking = []
    for tid, c in selected.items():
        if c["status"] in _EXCLUDED_FROM_AGGREGATE:
            continue
        if c.get("layer") not in SYSTEM_LAYERS:
            continue
        status = c["status"]
        if status in _EXCEPTION_STATUSES or _PROGRESS_RANK.get(status, -1) < _IMPLEMENTED_RANK:
            blocking.append({"task_id": tid, "layer": c["layer"], "status": status})
    return {"passed": not blocking, "blocking_cards": blocking}
