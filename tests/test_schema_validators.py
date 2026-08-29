"""Tests for scripts/pipeline/lib/schema_validators.py (ported 2026-08-29,
taskcard-only slice)."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline" / "lib"))

from schema_validators import validate_taskcard_record  # noqa: E402

_VALID_BASE = {
    "task_id": "T-1", "mission_id": "M-1", "status": "TODO",
    "recorded_at": "2026-08-29T00:00:00Z", "recorded_by": "a", "evidence_refs": [],
}


def test_valid_record_has_no_errors():
    assert validate_taskcard_record(dict(_VALID_BASE)) == []


def test_missing_required_field_flagged():
    record = dict(_VALID_BASE)
    del record["recorded_by"]
    errors = validate_taskcard_record(record)
    assert any("recorded_by" in e for e in errors)


def test_invalid_status_flagged():
    record = dict(_VALID_BASE, status="NOT_A_REAL_STATUS")
    errors = validate_taskcard_record(record)
    assert any("invalid status" in e for e in errors)


def test_evidence_refs_wrong_type_flagged():
    record = dict(_VALID_BASE, evidence_refs="not-a-list")
    errors = validate_taskcard_record(record)
    assert any("evidence_refs" in e for e in errors)


def test_paused_requires_reason():
    record = dict(_VALID_BASE, status="PAUSED")
    errors = validate_taskcard_record(record)
    assert any("pause_reason" in e for e in errors)


def test_paused_with_reason_is_valid():
    record = dict(_VALID_BASE, status="PAUSED", pause_reason="waiting on input")
    assert validate_taskcard_record(record) == []


def test_closed_requires_evidence():
    record = dict(_VALID_BASE, status="CLOSED", evidence_refs=[])
    errors = validate_taskcard_record(record)
    assert any("evidence_refs" in e for e in errors)


def test_closed_with_evidence_is_valid():
    record = dict(_VALID_BASE, status="CLOSED", evidence_refs=["tests/test_x.py"])
    assert validate_taskcard_record(record) == []


def test_todo_does_not_require_evidence():
    record = dict(_VALID_BASE, status="TODO", evidence_refs=[])
    assert validate_taskcard_record(record) == []


def test_blocked_does_not_require_evidence():
    record = dict(_VALID_BASE, status="BLOCKED_EXTERNAL", evidence_refs=[])
    assert validate_taskcard_record(record) == []
