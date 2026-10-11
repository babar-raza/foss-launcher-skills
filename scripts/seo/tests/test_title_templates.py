"""SEO-TITLE-TEMPLATE-REGISTRY: title_templates.py resolver/conformance tests.

Covers Finding #22 (31 docs devguide pages + 28 KB FAQ pages sharing a
single literal generic title) via the registry at
scripts/pipeline/config/title_templates.yaml.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[2]
_PIPELINE = _SCRIPTS / "pipeline"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
if str(_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_PIPELINE))

import seo.pipeline.title_templates as tt  # noqa: E402


def test_registry_loads_and_has_all_four_page_types():
    registry = tt.load_registry()
    assert set(registry["page_types"].keys()) == {
        "docs_devguide_index", "kb_faq", "products_family_root", "reference_class",
    }


def test_registry_max_content_clause_words_is_6():
    registry = tt.load_registry()
    assert registry["max_content_clause_words"] == 6


def test_resolve_devguide_with_content_clause():
    title = tt.resolve_title(
        "docs_devguide_index", family="PDF", platform=".NET",
        content_clause="Forms, Annotations & JavaScript Extensions",
    )
    assert title == "Aspose.PDF FOSS for .NET — Forms, Annotations & JavaScript Extensions"


def test_resolve_devguide_without_content_clause_uses_fallback():
    title = tt.resolve_title("docs_devguide_index", family="PDF", platform="Java")
    assert title == "Aspose.PDF FOSS for Java — Developer Guide & Examples"


def test_resolve_devguide_fallback_meets_the_50_char_floor_for_short_combos():
    """Regression pin (found by an independent S-116 review before any
    content file was written): the ORIGINAL fallback resolved to 38-48
    chars for every real family/platform combo -- always below safety.py's
    _TITLE_MIN=50. The shortest realistic combo (a 2-char family + a
    2-char platform) is the tightest case; it must still clear the floor."""
    title = tt.resolve_title("docs_devguide_index", family="3D", platform="Go")
    assert len(title) >= 50


def test_resolve_kb_faq_ignores_any_content_clause_rigid():
    title = tt.resolve_title("kb_faq", family="Page", platform="Python", content_clause="should be ignored")
    assert title == "Aspose.Page FOSS for Python — Frequently Asked Questions"


def test_resolve_kb_faq_meets_the_50_char_floor_for_short_combos():
    """Same regression class as the devguide fallback -- kb_faq is rigid
    (skeleton == fallback_skeleton), so the ORIGINAL "...FAQ" skeleton
    (25-36 chars for every real combo) would have failed this floor for
    EVERY kb FAQ title, not just an edge case."""
    title = tt.resolve_title("kb_faq", family="3D", platform="Go")
    assert len(title) >= 50


def test_resolve_products_family_root():
    title = tt.resolve_title("products_family_root", family="PDF", category="PDF Document Processing Library")
    assert title == "Aspose.PDF FOSS | Open-Source PDF Document Processing Library"


def test_resolve_reference_class_is_bare_class_name():
    title = tt.resolve_title("reference_class", family="3d", class_name="A3DObject")
    assert title == "A3DObject"


def test_resolve_unknown_page_type_raises():
    with pytest.raises(tt.UnknownPageType):
        tt.resolve_title("not_a_real_page_type", family="X")


def test_resolve_missing_required_placeholder_raises():
    with pytest.raises(tt.MissingPlaceholder):
        tt.resolve_title("reference_class", family="3d")  # class_name missing


def test_check_conformance_true_for_fallback_title():
    assert tt.check_conformance(
        "Aspose.PDF FOSS for .NET — Developer Guide & Examples", "docs_devguide_index", family="PDF", platform=".NET",
    )


def test_check_conformance_true_for_skeleton_with_bounded_clause():
    assert tt.check_conformance(
        "Aspose.PDF FOSS for .NET — Forms, Annotations & JavaScript Extensions",
        "docs_devguide_index", family="PDF", platform=".NET",
    )


def test_check_conformance_false_for_the_known_duplicate_title():
    """The exact regression this task exists to eventually fix -- the
    literal generic title is NOT conformant (it isn't the family/platform-
    scoped fallback either, since it has no family/platform in it at all)."""
    assert not tt.check_conformance(
        "Developer Guide", "docs_devguide_index", family="PDF", platform=".NET",
    )


def test_check_conformance_false_when_clause_exceeds_6_words():
    too_long = "This Clause Has Way More Than Six Words In It Definitely"
    assert not tt.check_conformance(
        f"Aspose.PDF FOSS for .NET — {too_long}", "docs_devguide_index", family="PDF", platform=".NET",
    )


def test_check_conformance_false_for_wrong_family():
    assert not tt.check_conformance(
        "Aspose.Words FOSS for .NET — Some Clause", "docs_devguide_index", family="PDF", platform=".NET",
    )


def test_check_conformance_rigid_kb_faq_exact_match_only():
    assert tt.check_conformance(
        "Aspose.Page FOSS for Python — Frequently Asked Questions", "kb_faq", family="Page", platform="Python",
    )
    assert not tt.check_conformance("Frequently Asked Questions", "kb_faq", family="Page", platform="Python")


def test_check_conformance_rigid_reference_class():
    assert tt.check_conformance("A3DObject", "reference_class", family="3d", class_name="A3DObject")
    assert not tt.check_conformance("A3dObject", "reference_class", family="3d", class_name="A3DObject")


def test_products_family_root_is_marked_codify_only_not_a_backfill_target():
    registry = tt.load_registry()
    assert registry["page_types"]["products_family_root"]["codify_only"] is True
