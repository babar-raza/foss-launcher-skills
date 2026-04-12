"""Tests for externalized grade config (S2-3 fix)."""

import yaml
from pathlib import Path

from content_eval import EVALUATOR_LOGIC_VERSION
from content_eval.models import (
    CRITICAL_CATEGORIES,
    _CATEGORY_CEILINGS,
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
