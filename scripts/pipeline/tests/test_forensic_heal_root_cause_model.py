from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib" / "forensic_heal"))

import root_cause_model as rcm  # noqa: E402


def test_build_root_cause_happy_path():
    rc = rcm.build_root_cause(
        "RC-001", layer="script", file_ref="scripts/pipeline/commands/content/batch_reference.py:412",
        finding_ids=["FND-email-python-001", "FND-pdf-net-001"],
        why_root_cause_not_symptom="Both findings show empty description cells traced to the same ERC fallback gap",
        fix_direction="Add a signature-based fallback when ERC has no description",
        risk_if_unfixed="Recurs on every future regen for any product hitting the same code path",
    )
    assert rc["root_cause_id"] == "RC-001"
    assert rc["layer"] == "script"
    assert rc["finding_ids"] == ["FND-email-python-001", "FND-pdf-net-001"]
    assert rc["evidence"] == []


def test_build_root_cause_rejects_invalid_layer():
    with pytest.raises(ValueError, match="invalid layer"):
        rcm.build_root_cause(
            "RC-002", layer="not_a_real_layer", file_ref="x.py", finding_ids=["FND-1"],
            why_root_cause_not_symptom="x", fix_direction="x", risk_if_unfixed="x",
        )


def test_build_root_cause_rejects_empty_finding_ids():
    with pytest.raises(ValueError, match="finding_ids"):
        rcm.build_root_cause(
            "RC-003", layer="script", file_ref="x.py", finding_ids=[],
            why_root_cause_not_symptom="x", fix_direction="x", risk_if_unfixed="x",
        )


def test_build_root_cause_rejects_blank_required_prose_field():
    with pytest.raises(ValueError, match="fix_direction"):
        rcm.build_root_cause(
            "RC-004", layer="script", file_ref="x.py", finding_ids=["FND-1"],
            why_root_cause_not_symptom="x", fix_direction="   ", risk_if_unfixed="x",
        )


def test_validate_root_cause_set_flags_unexplained_findings():
    rc = rcm.build_root_cause(
        "RC-001", layer="script", file_ref="x.py", finding_ids=["FND-1"],
        why_root_cause_not_symptom="x", fix_direction="x", risk_if_unfixed="x",
    )
    warnings = rcm.validate_root_cause_set([rc], all_finding_ids={"FND-1", "FND-2"})
    assert any("FND-2" in w for w in warnings)


def test_validate_root_cause_set_flags_unknown_finding_reference():
    rc = rcm.build_root_cause(
        "RC-001", layer="script", file_ref="x.py", finding_ids=["FND-999"],
        why_root_cause_not_symptom="x", fix_direction="x", risk_if_unfixed="x",
    )
    warnings = rcm.validate_root_cause_set([rc], all_finding_ids={"FND-1"})
    assert any("FND-999" in w for w in warnings)


def test_validate_root_cause_set_clean_when_every_finding_explained():
    rc = rcm.build_root_cause(
        "RC-001", layer="script", file_ref="x.py", finding_ids=["FND-1", "FND-2"],
        why_root_cause_not_symptom="x", fix_direction="x", risk_if_unfixed="x",
    )
    warnings = rcm.validate_root_cause_set([rc], all_finding_ids={"FND-1", "FND-2"})
    assert warnings == []
