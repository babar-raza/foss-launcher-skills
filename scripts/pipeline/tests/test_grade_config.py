"""Tests for externalized grade config (S2-3 fix)."""

import yaml
from pathlib import Path

from content_eval import EVALUATOR_LOGIC_VERSION
from content_eval.models import (
    CRITICAL_CATEGORIES,
    _CATEGORY_CEILINGS,
    EvalReport,
    Finding,
    compute_grade_with_criticality,
)


_CONFIG_PATH = Path(__file__).resolve().parents[1] / "content_eval" / "grade_config.yaml"


def test_grade_config_exists():
    """grade_config.yaml must exist."""
    assert _CONFIG_PATH.exists(), f"Missing {_CONFIG_PATH}"


def test_grade_config_version_matches():
    """grade_config.yaml version must match EVALUATOR_LOGIC_VERSION."""
    config = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8"))
    assert config["evaluator_logic_version"] == EVALUATOR_LOGIC_VERSION


def test_critical_categories_loaded():
    """CRITICAL_CATEGORIES must be loaded from config."""
    assert "FC" in CRITICAL_CATEGORIES
    assert "PC" in CRITICAL_CATEGORIES
    assert "TA" in CRITICAL_CATEGORIES


def test_ceiling_categories_loaded():
    """Category ceilings must be loaded from config."""
    assert "TA" in _CATEGORY_CEILINGS
    assert _CATEGORY_CEILINGS["TA"]["ceiling"] == "C"
    assert "FT" in _CATEGORY_CEILINGS
    assert "CP" in _CATEGORY_CEILINGS
    assert _CATEGORY_CEILINGS["CP"]["ceiling"] == "B"


def test_critical_fail_forces_f():
    """FAIL in a critical category must produce grade F."""
    findings = [Finding("FAIL", "FC", "a.md", 1, "forbidden claim")]
    assert compute_grade_with_criticality(findings) == "F"


def test_ceiling_applied_from_config():
    """Category ceiling from config must cap the grade."""
    # Single TA WARN should cap at C (even though base grade would be A)
    findings = [Finding("WARN", "TA", "a.md", 1, "type accuracy warning")]
    assert compute_grade_with_criticality(findings) == "C"


def test_cp_fail_caps_at_b():
    """CP FAIL should cap at B per config."""
    findings = [Finding("FAIL", "CP", "a.md", 1, "code purity fail")]
    # 1 FAIL -> base C, CP ceiling B -> stays C (C is worse than B)
    assert compute_grade_with_criticality(findings) == "C"


def test_no_findings_gives_a():
    """Zero findings must produce grade A."""
    assert compute_grade_with_criticality([]) == "A"


def test_cb_ceiling_loaded():
    """CB (code_block_api) ceiling must be loaded from config."""
    assert "CB" in _CATEGORY_CEILINGS
    assert _CATEGORY_CEILINGS["CB"]["ceiling"] == "C"
    assert _CATEGORY_CEILINGS["CB"]["levels"] == ["FAIL"]


def test_dl_ceiling_loaded():
    """DL (dead_internal_link) ceiling must be loaded from config."""
    assert "DL" in _CATEGORY_CEILINGS
    assert _CATEGORY_CEILINGS["DL"]["ceiling"] == "C"
    assert _CATEGORY_CEILINGS["DL"]["levels"] == ["FAIL"]


def test_cb_fail_caps_at_c():
    """CB FAIL should cap at C per config."""
    findings = [Finding("FAIL", "CB", "a.md", 1, "code block API miss")]
    # 1 FAIL -> base C, CB ceiling C -> stays C
    assert compute_grade_with_criticality(findings) == "C"


def test_cb_warn_does_not_cap():
    """CB WARN should NOT trigger ceiling (only FAIL level configured)."""
    findings = [Finding("WARN", "CB", "a.md", 1, "code block API warning")]
    # 0 FAIL, 1 WARN -> base A, CB ceiling not triggered (WARN not in levels)
    assert compute_grade_with_criticality(findings) == "A"


def test_dl_fail_caps_at_c():
    """DL FAIL should cap at C per config."""
    findings = [Finding("FAIL", "DL", "a.md", 1, "dead internal link")]
    assert compute_grade_with_criticality(findings) == "C"


# ---------------------------------------------------------------------------
# grade_reasons tests (T-14)
# ---------------------------------------------------------------------------


def test_grade_reasons_critical_override():
    """Critical FAIL should produce critical category override reason."""
    r = EvalReport(findings=[
        Finding("FAIL", "FC", "a.md", 1, "forbidden", evaluator="forbidden_claims"),
    ])
    reasons = r.grade_reasons()
    assert len(reasons) == 1
    assert "critical category override" in reasons[0]
    assert "FC" in reasons[0]


def test_grade_reasons_base_grade():
    """WARN-only findings should show base grade reason."""
    r = EvalReport(findings=[
        Finding("WARN", "AA", "a.md", 1, "api acc", evaluator="api_accuracy"),
    ])
    reasons = r.grade_reasons()
    assert any("1 WARN" in r for r in reasons)


def test_grade_reasons_ceiling_applied():
    """TA WARN should show ceiling applied reason."""
    r = EvalReport(findings=[
        Finding("WARN", "TA", "a.md", 1, "type acc", evaluator="type_accuracy"),
    ])
    reasons = r.grade_reasons()
    assert any("ceiling applied" in r for r in reasons)


def test_grade_reasons_no_findings():
    """No findings should explain grade A."""
    r = EvalReport(findings=[])
    reasons = r.grade_reasons()
    assert len(reasons) == 1
    assert "No findings" in reasons[0]
