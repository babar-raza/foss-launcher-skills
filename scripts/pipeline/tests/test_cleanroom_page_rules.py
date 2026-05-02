"""
TC-S96-009: Tests for cleanroom_page_rules.yaml configuration.
Verifies that the YAML is parseable, structurally correct, and contains
required profiles for all 5 subdomains.
"""

import pathlib
import pytest

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

CONFIG_PATH = (
    pathlib.Path(__file__).parent.parent / "config" / "cleanroom_page_rules.yaml"
)

pytestmark = pytest.mark.skipif(not HAS_YAML, reason="PyYAML not installed")

REQUIRED_PROFILES = ["reference_page", "products_page", "blog_post", "docs_page", "kb_page", "section_index"]
REQUIRED_SUBDOMAIN_DEFAULTS = ["reference", "blog", "docs", "kb", "products"]


@pytest.fixture(scope="module")
def rules():
    assert CONFIG_PATH.exists(), f"Config not found: {CONFIG_PATH}"
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def test_config_loads(rules):
    assert rules is not None
    assert isinstance(rules, dict)


def test_has_profiles_key(rules):
    assert "profiles" in rules
    assert isinstance(rules["profiles"], dict)


def test_all_required_profiles_present(rules):
    for name in REQUIRED_PROFILES:
        assert name in rules["profiles"], f"Missing profile: {name}"


def test_all_subdomain_defaults_present(rules):
    defaults = rules.get("subdomain_defaults", {})
    for sub in REQUIRED_SUBDOMAIN_DEFAULTS:
        assert sub in defaults, f"Missing subdomain default: {sub}"


def test_reference_page_evidence_required(rules):
    profile = rules["profiles"]["reference_page"]
    assert profile["evidence_required"] is True
    assert profile["claims_required"] is True
    assert profile["apis_required"] is True


def test_products_page_evidence_not_required(rules):
    """Products pages must NOT require evidence — they have no evidence blocks."""
    profile = rules["profiles"]["products_page"]
    assert profile["evidence_required"] is False
    assert profile["claims_required"] is False
    assert profile["apis_required"] is False
    assert profile["evidence_block_forbidden"] is True


def test_blog_post_author_enforcement(rules):
    """Blog must enforce author=Aspose and directory path pattern."""
    profile = rules["profiles"]["blog_post"]
    assert profile["author_must_be_aspose"] is True
    assert profile["path_must_be_directory"] is True


def test_kb_page_grade_required(rules):
    profile = rules["profiles"]["kb_page"]
    assert profile["grade_required"] is True
    assert "grade" in profile["required_frontmatter"]


def test_reference_page_churn_tolerance_none(rules):
    """Reference pages should have zero churn tolerance."""
    profile = rules["profiles"]["reference_page"]
    assert profile["churn_tolerance"] == "none"


def test_section_index_no_evidence(rules):
    profile = rules["profiles"]["section_index"]
    assert profile["evidence_required"] is False
    assert profile["claims_required"] is False


def test_grade_order_defined(rules):
    order = rules.get("grade_order", [])
    assert order == ["A", "B", "C", "D", "F"]


def test_all_profiles_have_required_fields(rules):
    required_keys = [
        "match", "required_frontmatter", "protected_frontmatter",
        "evidence_required", "claims_required", "grade_required",
        "churn_tolerance", "link_check", "shortcode_check"
    ]
    for name, profile in rules["profiles"].items():
        for key in required_keys:
            assert key in profile, f"Profile '{name}' missing key: {key}"


def test_products_page_match_subdomain(rules):
    profile = rules["profiles"]["products_page"]
    assert profile["match"]["subdomain"] == "products"


def test_blog_subdomain_match(rules):
    profile = rules["profiles"]["blog_post"]
    assert profile["match"]["subdomain"] == "blog"
    # Blog match should not require a specific layout — any blog page matches
    assert "layout" not in profile["match"] or profile["match"].get("layout") is None


def test_churn_signals_defined(rules):
    signals = rules.get("churn_signals", [])
    assert "timestamp_only" in signals
    assert "yaml_reorder" in signals
    assert "whitespace_only" in signals
