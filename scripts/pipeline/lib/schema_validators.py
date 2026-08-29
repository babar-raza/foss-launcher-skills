"""schema_validators.py -- validation for taskcard_store.py's records.

Ported from aspose.org's schema_validators.py (2026-08-29 sync,
TASK_BACKLOG.md SYNC-1) as a NARROW SLICE, not a full port: source's
version validates several other schemas (fact graphs, etc.) specific to
its own knowledge pipeline that have no equivalent here. Only
validate_taskcard_record and its direct dependencies are ported -- the
taskcard status vocabulary and evidence-requirement rule are generic
project-tracking concepts, not tied to any content/product model.

CONTRACT: scripts/pipeline/lib/schema_validators.py
  purpose: validate one taskcards.jsonl row before taskcard_store.py
    writes it -- a malformed or under-evidenced row is refused before it
    ever reaches disk, not just flagged after the fact.
"""
from __future__ import annotations


def _check_required(data: dict, keys: list, context: str) -> list:
    errors = []
    for key in keys:
        if key not in data:
            errors.append(f"{context}: missing required key '{key}'")
    return errors


def _check_type(data: dict, key: str, expected_type: type, context: str) -> list:
    if key in data and not isinstance(data[key], expected_type):
        return [f"{context}: '{key}' expected {expected_type.__name__}, got {type(data[key]).__name__}"]
    return []


_TASKCARD_STATUSES = {
    "TODO", "READY", "IN_PROGRESS", "IMPLEMENTED", "FOCUSED_VERIFIED",
    "INTEGRATION_VERIFIED", "END_TO_END_VERIFIED", "PILOT_PROVEN",
    "INDEPENDENTLY_REVIEWED", "CLOSED", "REWORK_REQUIRED",
    "BLOCKED_LOCAL", "BLOCKED_EXTERNAL", "SUPERSEDED", "OUT_OF_SCOPE",
    "PAUSED",
}
# Statuses at or before which no evidence is yet required (nothing verified).
_TASKCARD_PRE_EVIDENCE_STATUSES = {"TODO", "READY", "IN_PROGRESS", "IMPLEMENTED"}
# Statuses representing a deliberate non-progress state rather than a
# verified/terminal outcome -- same evidence exemption as BLOCKED_*/SUPERSEDED.
_TASKCARD_NON_PROGRESS_STATUSES = (
    "SUPERSEDED", "OUT_OF_SCOPE", "BLOCKED_LOCAL", "BLOCKED_EXTERNAL",
    "REWORK_REQUIRED", "PAUSED",
)


def validate_taskcard_record(data: dict) -> list:
    """Validate one taskcards.jsonl row.

    The core rule: any status past IMPLEMENTED must cite at least one
    evidence_ref (a file path, commit SHA, or test name) -- the exact
    check that prevents a task claiming progress in prose while its
    structured record shows nothing verified.

    PAUSED records that a step was deliberately set aside mid-session
    rather than silently dropped -- non-terminal but distinct from
    BLOCKED_*: blocked means "can't proceed", paused means "chose not to
    proceed yet". Requires a pause_reason, the same way verified statuses
    require evidence_refs.
    """
    errors = []
    errors.extend(_check_required(
        data,
        ["task_id", "mission_id", "status", "recorded_at", "evidence_refs", "recorded_by"],
        "taskcard_record",
    ))
    errors.extend(_check_type(data, "evidence_refs", list, "taskcard_record"))
    if "status" in data and data["status"] not in _TASKCARD_STATUSES:
        errors.append(f"taskcard_record: invalid status '{data['status']}'")
    status = data.get("status")
    if status == "PAUSED":
        reason = data.get("pause_reason")
        if not isinstance(reason, str) or not reason.strip():
            errors.append(
                "taskcard_record: status=PAUSED requires a non-empty pause_reason "
                "(a paused card with no stated reason is indistinguishable from a "
                "silently dropped one)"
            )
    if (
        status in _TASKCARD_STATUSES
        and status not in _TASKCARD_PRE_EVIDENCE_STATUSES
        and status not in _TASKCARD_NON_PROGRESS_STATUSES
    ):
        refs = data.get("evidence_refs")
        if not isinstance(refs, list) or not refs:
            errors.append(
                f"taskcard_record: status={status} requires a non-empty evidence_refs "
                f"(a status past IMPLEMENTED that cites no evidence is the prose-drift "
                f"failure mode this schema exists to prevent)"
            )
    return errors
