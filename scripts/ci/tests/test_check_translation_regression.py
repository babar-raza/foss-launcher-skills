"""Tests for scripts/ci/checks/check_translation_regression.py (TC-W3H-006).

Coverage:
  Unit — looks_english(): non-Latin ascii-fraction path, Latin stopword path,
          English locale exempt, short strings exempt
  Unit — locale_of(): path shapes
  Unit — check_pair(): R1 regression, no-fail when previous was also English,
          no-fail when current is translated, R2 prompt-leak, unparseable skip
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci" / "checks"))

from check_translation_regression import (  # noqa: E402
    check_pair,
    english_counterpart_path,
    locale_of,
    looks_english,
)


def _page(desc: str) -> str:
    return f"---\ntitle: x\ndescription: '{desc}'\n---\n\nBody.\n"


AR_DESC = "ارفع وتشغيل مع Aspose.3D FOSS for Java – المعايير، إعداد Maven"
EN_DESC = ("Get up and running with the library and learn how to use all "
           "of the features for your project from the start")
DE_DESC = ("Erfahren Sie, wie man 3D-Szenen aus Python exportiert, "
           "einschließlich Speicheroptionen und formatspezifischer Exporteure")
LEAK_TEXT = ("---\ntitle: 'Reglas:\n\n  - Salida SÓLO la traducción. "
             "No explicaciones, notas ni comentarios.'\n---\nBody.\n")


class TestLooksEnglish:
    def test_english_in_arabic_locale(self):
        assert looks_english(EN_DESC, "ar") is True

    def test_arabic_in_arabic_locale(self):
        assert looks_english(AR_DESC, "ar") is False

    def test_english_in_german_locale(self):
        assert looks_english(EN_DESC, "de") is True

    def test_german_in_german_locale(self):
        assert looks_english(DE_DESC, "de") is False

    def test_en_locale_always_false(self):
        assert looks_english(EN_DESC, "en") is False

    def test_short_string_exempt(self):
        assert looks_english("API docs", "ar") is False


class TestLocaleOf:
    def test_docs_locale(self):
        assert locale_of("content/docs.aspose.org/bg/cells/net/features.md") == "bg"

    def test_reference_locale(self):
        assert locale_of("content/reference.aspose.org/es/pdf/net/Do.md") == "es"

    def test_unexpected_shape_defaults_en(self):
        assert locale_of("README.md") == "en"


class TestCheckPair:
    def test_r1_regression_blocks(self):
        assert check_pair(_page(EN_DESC), _page(AR_DESC.replace("'", "''")), "ar") == ["R1"]

    def test_preexisting_english_not_blocked(self):
        # Previous version was ALSO English — pre-existing debt, not a regression
        assert check_pair(_page(EN_DESC), _page(EN_DESC), "ar") == []

    def test_translated_current_passes(self):
        assert check_pair(_page(DE_DESC), _page(EN_DESC), "de") == []

    def test_new_file_english_not_blocked(self):
        # No previous version -> R1 cannot fire (quality issue, not regression)
        assert check_pair(_page(EN_DESC), None, "ar") == []

    def test_r2_prompt_leak_blocks(self):
        assert "R2" in check_pair(LEAK_TEXT, None, "es")

    def test_unparseable_frontmatter_skipped(self):
        # Broken YAML is check_frontmatter_yaml's job — description is None here
        broken = "---\ndescription: 'unterminated\ntitle: x\n---\nBody.\n"
        assert check_pair(broken, _page(AR_DESC.replace("'", "''")), "ar") == []

    def test_r3_fence_stripping_blocks(self):
        old = _page(DE_DESC) + "\n```csharp\ncode();\n```\n"
        cur = _page(DE_DESC) + "\n\ncode();\n```\n"  # opener stripped
        assert check_pair(cur, old, "de") == ["R3"]

    def test_r3_fence_added_passes(self):
        old = _page(DE_DESC)
        cur = _page(DE_DESC) + "\n```csharp\ncode();\n```\n"
        assert check_pair(cur, old, "de") == []

    def test_r3_block_replaced_by_maven_coord_shortcode_passes(self):
        # Mission MT008 (plans/master-plan.md, TC-MT008-08): a whole fenced
        # dependency block cleanly replaced by the maven-coord shortcode is
        # NOT wave-3 fence-stripping -- the code content is gone too, and a
        # validly-argumented shortcode call took its place.
        old = _page(DE_DESC) + "\n```xml\n<dependency/>\n```\n"
        cur = _page(DE_DESC) + '\n{{< maven-coord "cells" "java" >}}\n'
        assert check_pair(cur, old, "de") == []

    def test_r3_two_blocks_replaced_by_two_shortcodes_passes(self):
        old = _page(DE_DESC) + "\n```xml\nA\n```\n```xml\nB\n```\n"
        cur = _page(DE_DESC) + (
            '\n{{< maven-coord "cells" "java" >}}\n'
            '{{< maven-gav "cells" "java" >}}\n'
        )
        assert check_pair(cur, old, "de") == []

    def test_r3_block_removed_without_shortcode_still_blocks(self):
        # Same fence-pair reduction as the passing case above, but no new
        # shortcode call -- must still be treated as real fence-stripping.
        old = _page(DE_DESC) + "\n```xml\n<dependency/>\n```\n"
        cur = _page(DE_DESC) + "\n<dependency/>\n"
        assert check_pair(cur, old, "de") == ["R3"]

    def test_r3_odd_reduction_with_shortcode_still_blocks(self):
        # One marker of a pair stripped (odd reduction) even though a
        # shortcode call is present elsewhere -- cannot be a clean
        # pair-for-shortcode substitution, so it must still fail.
        old = _page(DE_DESC) + "\n```xml\n<a/>\n```\n```xml\n<b/>\n```\n"
        cur = _page(DE_DESC) + '\n<a/>\n```\n{{< maven-coord "cells" "java" >}}\n'
        assert check_pair(cur, old, "de") == ["R3"]


class TestEnglishCounterpartPath:
    def test_docs_locale(self):
        assert english_counterpart_path(
            "content/docs.aspose.org/ar/3d/typescript/features.md"
        ) == "content/docs.aspose.org/en/3d/typescript/features.md"

    def test_already_english_returns_none(self):
        assert english_counterpart_path("content/docs.aspose.org/en/3d/typescript/features.md") is None

    def test_unexpected_shape_returns_none(self):
        assert english_counterpart_path("README.md") is None

    def test_backslash_path(self):
        assert english_counterpart_path(
            r"content\docs.aspose.org\ar\3d\typescript\features.md"
        ) == "content/docs.aspose.org/en/3d/typescript/features.md"


class TestR3EnglishCounterpartOverride:
    """ST-153: a locale page catching up to a removal that already happened
    on English must not be blocked as fence-stripping, but a locale that is
    still behind English's own current fence count must still fail -- the
    exact live incident this was hardened from (an Arabic page correctly
    received a marker for a code example already removed from English)."""

    def test_fence_drop_matching_current_english_count_passes(self):
        # English currently has 1 fence pair (2 markers); the locale page
        # drops from 2 fences to 1, matching the corresponding real incident
        # exactly -- catching up, not diverging.
        old = _page(DE_DESC) + "\n```csharp\nA();\n```\n\n<!-- removed -->\n\n```csharp\nB();\n```\n"
        cur = _page(DE_DESC) + "\n<!-- removed -->\n\n<!-- removed -->\n\n```csharp\nB();\n```\n"
        assert check_pair(cur, old, "de", english_fence_count=2) == []

    def test_fence_drop_below_current_english_count_still_blocks(self):
        # English currently has 2 fence pairs (4 markers) -- the locale
        # page drops below that, so it is NOT merely catching up; still a
        # real divergence and must fail.
        old = _page(DE_DESC) + "\n```csharp\nA();\n```\n```csharp\nB();\n```\n"
        cur = _page(DE_DESC) + "\nA();\n```\n```csharp\nB();\n```\n"  # opener stripped
        assert check_pair(cur, old, "de", english_fence_count=4) == ["R3"]

    def test_no_english_fence_count_preserves_prior_behavior(self):
        # english_fence_count defaults to None (English counterpart missing
        # or unreadable) -- behaves exactly as before this fix, still fails.
        old = _page(DE_DESC) + "\n```csharp\ncode();\n```\n"
        cur = _page(DE_DESC) + "\n\ncode();\n```\n"
        assert check_pair(cur, old, "de") == ["R3"]
        assert check_pair(cur, old, "de", english_fence_count=None) == ["R3"]

    def test_clean_shortcode_substitution_unaffected_by_english_count(self):
        # The pre-existing shortcode-substitution exemption still applies
        # independently of english_fence_count.
        old = _page(DE_DESC) + "\n```xml\n<dependency/>\n```\n"
        cur = _page(DE_DESC) + '\n{{< maven-coord "cells" "java" >}}\n'
        assert check_pair(cur, old, "de", english_fence_count=0) == []
