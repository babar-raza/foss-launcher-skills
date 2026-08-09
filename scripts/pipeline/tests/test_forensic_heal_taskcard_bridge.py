from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib" / "forensic_heal"))

import taskcard_bridge as tcb  # noqa: E402


def _base_item(**overrides):
    item = dict(
        title="Fix empty-description-cells fallback in batch_reference.py",
        root_cause_id="RC-001",
        finding_ids=["FND-email-python-001"],
        layer="script",
        priority="P0",
        allowed_paths=["scripts/pipeline/commands/content/batch_reference.py"],
        verification_commands=["pytest scripts/pipeline/tests/test_batch_reference.py"],
        rollback="git checkout HEAD -- scripts/pipeline/commands/content/batch_reference.py",
    )
    item.update(overrides)
    return item


def test_build_taskcard_happy_path_is_schema_5f_valid():
    card = tcb.build_taskcard(
        "TC-MT025-99", "MT025-2026-08-08-FORENSIC-BLIND-SPOT-HEAL-SKILLS",
        recorded_at="2026-08-09T00:00:00Z", recorded_by="test-session",
        **_base_item(),
    )
    assert card["status"] == "TODO"
    assert card["evidence_refs"] == []
    assert card["task_id"] == "TC-MT025-99"
    assert card["priority"] == "P0"


def test_build_taskcard_rejects_invalid_priority():
    with pytest.raises(ValueError, match="invalid priority"):
        tcb.build_taskcard(
            "TC-1", "M", recorded_at="2026-08-09T00:00:00Z", recorded_by="s",
            **_base_item(priority="P9"),
        )


def test_build_taskcard_rejects_empty_allowed_paths():
    with pytest.raises(ValueError, match="allowed_paths"):
        tcb.build_taskcard(
            "TC-1", "M", recorded_at="2026-08-09T00:00:00Z", recorded_by="s",
            **_base_item(allowed_paths=[]),
        )


def test_build_taskcard_rejects_empty_verification_commands():
    with pytest.raises(ValueError, match="verification_commands"):
        tcb.build_taskcard(
            "TC-1", "M", recorded_at="2026-08-09T00:00:00Z", recorded_by="s",
            **_base_item(verification_commands=[]),
        )


def test_build_taskcard_rejects_blank_rollback():
    with pytest.raises(ValueError, match="rollback"):
        tcb.build_taskcard(
            "TC-1", "M", recorded_at="2026-08-09T00:00:00Z", recorded_by="s",
            **_base_item(rollback="   "),
        )


def test_build_taskcard_rejects_empty_finding_ids():
    with pytest.raises(ValueError, match="finding_ids"):
        tcb.build_taskcard(
            "TC-1", "M", recorded_at="2026-08-09T00:00:00Z", recorded_by="s",
            **_base_item(finding_ids=[]),
        )


def test_build_taskcards_from_fix_plan_assigns_sequential_ids():
    items = [_base_item(title="fix A"), _base_item(title="fix B", root_cause_id="RC-002")]
    cards = tcb.build_taskcards_from_fix_plan(
        items, mission_id="M", recorded_at="2026-08-09T00:00:00Z", recorded_by="s",
        task_id_prefix="TC-MT025",
    )
    assert [c["task_id"] for c in cards] == ["TC-MT025-01", "TC-MT025-02"]
    assert cards[1]["root_cause_id"] == "RC-002"
