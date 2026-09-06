"""SEO-PAGE-METADATA-CONSISTENCY (Contract E): page-level title/description/
subtitle consistency -- WARN-only, never a hard FAIL, routes to
requires_human_review via safety.py's own existing checks-8-9 precedent.

Acceptance checks mirrored here (per the design doc's own named checks):
  - near-literal title/description repetition (normalized containment or
    Jaccard > 0.7) -> WARN
  - a source_keywords phrase appearing verbatim in both fields -> WARN
  - family-root subtitle drifting to share zero significant tokens with a
    newly-proposed title -> WARN
Plus the real load_current_subtitle/is_family_root_page loaders (against
disposable tmp_path fixtures) and safety.py's real integration (check 4.5:
never rejects, correctly folds into requires_human_review).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[2]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import seo.pipeline.metadata_consistency as mc  # noqa: E402
import seo.pipeline.safety as safety  # noqa: E402


@pytest.fixture(autouse=True)
def _reset(tmp_path):
    mc.configure()
    yield
    mc.configure()


# ---------------------------------------------------------------------------
# check_page_metadata_consistency: near-literal repetition
# ---------------------------------------------------------------------------


class TestNearLiteralRepetition:
    def test_containment_is_flagged(self):
        report = mc.check_page_metadata_consistency(
            "x", "Convert PDF to Word",
            "Convert PDF to Word using our tool for developers today reliably.",
        )
        assert any(f.code == "title_description_near_literal_repetition" for f in report.findings)

    def test_reverse_containment_is_flagged(self):
        report = mc.check_page_metadata_consistency(
            "x", "Convert PDF to Word using our tool for developers today reliably",
            "Convert PDF to Word",
        )
        assert any(f.code == "title_description_near_literal_repetition" for f in report.findings)

    def test_high_jaccard_without_containment_is_flagged(self):
        report = mc.check_page_metadata_consistency(
            "x", "Convert PDF Word Excel PowerPoint",
            "PDF Word Excel PowerPoint Convert tool",
        )
        assert any(f.code == "title_description_near_literal_repetition" for f in report.findings)

    def test_distinct_summary_is_not_flagged(self):
        report = mc.check_page_metadata_consistency(
            "x", "Convert PDF to Word Documents Easily",
            "Use our reliable Python library to transform files into editable "
            "formats for developers today with high fidelity output.",
        )
        assert report.findings == []

    def test_missing_title_or_description_is_not_flagged(self):
        assert mc.check_page_metadata_consistency("x", None, "A description here.").findings == []
        assert mc.check_page_metadata_consistency("x", "A title here", None).findings == []

    def test_has_warnings_property(self):
        report = mc.check_page_metadata_consistency("x", "Same Text Here", "Same Text Here")
        assert report.has_warnings is True
        assert mc.ConsistencyReport().has_warnings is False


# ---------------------------------------------------------------------------
# check_page_metadata_consistency: source keyword in both fields
# ---------------------------------------------------------------------------


class TestSourceKeywordInBoth:
    def test_phrase_in_both_fields_is_flagged(self):
        report = mc.check_page_metadata_consistency(
            "x", "Best PDF Converter Tool Ever",
            "Our PDF Converter handles documents reliably for every developer need today.",
            source_keywords=["pdf converter"],
        )
        assert any(f.code == "source_keyword_in_both_fields" for f in report.findings)

    def test_phrase_in_only_one_field_is_not_flagged(self):
        report = mc.check_page_metadata_consistency(
            "x", "Best PDF Converter Tool Ever",
            "Totally different phrasing about documents entirely unrelated here today.",
            source_keywords=["pdf converter"],
        )
        assert report.findings == []

    def test_no_source_keywords_is_not_flagged(self):
        report = mc.check_page_metadata_consistency(
            "x", "Best PDF Converter Tool Ever", "Our PDF Converter handles documents reliably today.",
        )
        assert report.findings == []

    def test_case_insensitive_match(self):
        report = mc.check_page_metadata_consistency(
            "x", "Best PDF CONVERTER Tool Ever", "Our pdf converter handles documents today.",
            source_keywords=["PDF Converter"],
        )
        assert any(f.code == "source_keyword_in_both_fields" for f in report.findings)


# ---------------------------------------------------------------------------
# check_page_metadata_consistency: family-root subtitle drift
# ---------------------------------------------------------------------------


class TestFamilyRootSubtitleDrift:
    def test_zero_overlap_with_newly_proposed_title_is_flagged(self):
        report = mc.check_page_metadata_consistency(
            "x", None, None,
            "Free MIT-licensed PDF library for developers",
            proposed_title="Completely Unrelated Marketing Copy Here",
        )
        assert any(f.code == "family_root_subtitle_title_drift" for f in report.findings)

    def test_shared_significant_token_is_not_flagged(self):
        report = mc.check_page_metadata_consistency(
            "x", None, None,
            "Free MIT-licensed PDF library for developers",
            proposed_title="Aspose PDF Library for Developers",
        )
        assert report.findings == []

    def test_no_subtitle_is_not_flagged(self):
        report = mc.check_page_metadata_consistency(
            "x", None, None, None, proposed_title="Any New Title",
        )
        assert report.findings == []

    def test_no_newly_proposed_title_is_not_flagged(self):
        """An unchanged title cannot "drift" from a subtitle it was
        presumably already consistent with -- only a genuinely NEW
        proposal is checked."""
        report = mc.check_page_metadata_consistency(
            "x", None, None, "Free MIT-licensed PDF library for developers", proposed_title=None,
        )
        assert report.findings == []

    def test_only_stopwords_overlap_still_counts_as_zero_significant_overlap(self):
        report = mc.check_page_metadata_consistency(
            "x", None, None, "A library for the developers", proposed_title="This is for you and your team",
        )
        assert any(f.code == "family_root_subtitle_title_drift" for f in report.findings)


# ---------------------------------------------------------------------------
# is_family_root_page / load_current_subtitle (real repo fixture reads)
# ---------------------------------------------------------------------------


class TestIsFamilyRootPage:
    def test_family_root_shapes_across_sites(self):
        assert mc.is_family_root_page("content/docs.aspose.org/en/pdf/_index.md")
        assert mc.is_family_root_page("content/kb.aspose.org/en/words/_index.md")
        assert mc.is_family_root_page("content/reference.aspose.org/en/cells/_index.md")
        assert mc.is_family_root_page("content/products.aspose.org/en/3d/_index.md")

    def test_platform_level_page_is_not_family_root(self):
        assert not mc.is_family_root_page("content/docs.aspose.org/en/pdf/python/developer-guide/_index.md")
        assert not mc.is_family_root_page("content/docs.aspose.org/en/pdf/python/_index.md")

    def test_non_index_page_is_not_family_root(self):
        assert not mc.is_family_root_page("content/docs.aspose.org/en/pdf/getting-started.md")

    def test_unrecognized_site_is_not_family_root(self):
        assert not mc.is_family_root_page("content/blog.aspose.org/en/pdf/_index.md")

    def test_windows_backslashes_are_normalized(self):
        assert mc.is_family_root_page("content\\docs.aspose.org\\en\\pdf\\_index.md")


class TestLoadCurrentSubtitle:
    def _write_family_root(self, tmp_path, rel_path, subtitle=None):
        page = tmp_path / rel_path
        page.parent.mkdir(parents=True, exist_ok=True)
        fm = "---\ntitle: Family Root\n"
        if subtitle is not None:
            fm += f"subtitle: {subtitle}\n"
        fm += "---\nBody.\n"
        page.write_text(fm, encoding="utf-8")

    def test_real_subtitle_is_returned(self, tmp_path):
        self._write_family_root(tmp_path, "content/docs.aspose.org/en/pdf/_index.md", "A real subtitle here")
        assert mc.load_current_subtitle(
            "content/docs.aspose.org/en/pdf/_index.md", repo_root=tmp_path,
        ) == "A real subtitle here"

    def test_missing_subtitle_returns_none(self, tmp_path):
        self._write_family_root(tmp_path, "content/docs.aspose.org/en/pdf/_index.md")
        assert mc.load_current_subtitle("content/docs.aspose.org/en/pdf/_index.md", repo_root=tmp_path) is None

    def test_non_family_root_page_returns_none_without_reading(self, tmp_path):
        """A platform-level page is never even considered -- no file read
        attempted, so a missing file there is not an error."""
        assert mc.load_current_subtitle(
            "content/docs.aspose.org/en/pdf/python/x.md", repo_root=tmp_path,
        ) is None

    def test_missing_page_never_raises(self, tmp_path):
        assert mc.load_current_subtitle("content/docs.aspose.org/en/pdf/_index.md", repo_root=tmp_path) is None

    def test_real_repo_family_root_page(self):
        """Against the real repo (no repo_root override) -- confirms the
        module-level REPO_ROOT default resolves correctly, not just the
        test-seam configure() path."""
        subtitle = mc.load_current_subtitle("content/docs.aspose.org/en/3d/_index.md")
        assert isinstance(subtitle, str) and subtitle.strip()


# ---------------------------------------------------------------------------
# safety.py integration: check 4.5
# ---------------------------------------------------------------------------


def _title_rec(proposed, current="Old Title"):
    return {"field": "seoTitle", "action": "rewrite", "current": current, "proposed": proposed,
            "char_count": len(proposed) if proposed else None, "source_keywords": ["pdf"], "rationale": "x"}


def _desc_rec(proposed, current="Old description"):
    return {"field": "description", "action": "rewrite", "current": current, "proposed": proposed,
            "char_count": len(proposed) if proposed else None, "source_keywords": ["pdf"], "rationale": "x"}


def _rec(field_recs, page_path="content/docs.aspose.org/en/nonexistentfam/nonexistentplat/x.md"):
    return {
        "batch_id": "b1", "page_path": page_path, "site": "docs.aspose.org",
        "family": "nonexistentfam", "platform": "nonexistentplat",
        "opportunity_level": "HIGH", "llm_skipped": False,
        "recommendations": field_recs, "requires_human_review": False,
    }


# Length-valid (50-70 / 130-160), near-literal-repetition pair -- also
# shares the source keyword "pdf" in both fields -- exercises 2 of the 3
# checks in one real _gate_recommendation pass.
_REPEATED_TITLE = "Convert PDF To Word Documents Reliably Right Now Today"
_REPEATED_DESC = (
    "Convert PDF To Word Documents Reliably Right Now Today Using Our Fast "
    "Python Library For All Developers Who Need Reliable Fast Output Always."
)
# A length-valid, genuinely distinct pair that shares no significant tokens
# and no source keyword duplication -- the clean-pass control.
_CLEAN_TITLE = "Transform Documents Into Editable Word Files Instantly"
_CLEAN_DESC = (
    "Use our reliable open-source library to process files into fully "
    "editable formats, built for teams that need dependable automation."
)


class TestCheckPageMetadataConsistency:
    def test_helper_extracts_proposed_over_current(self):
        recs = [_title_rec("New Title"), _desc_rec("New Desc")]
        assert safety._effective_field_value(recs, "seoTitle") == "New Title"
        assert safety._proposed_field_value(recs, "seoTitle") == "New Title"

    def test_helper_falls_back_to_current_when_no_proposal(self):
        recs = [_title_rec(None, current="Existing Title")]
        assert safety._effective_field_value(recs, "seoTitle") == "Existing Title"
        assert safety._proposed_field_value(recs, "seoTitle") is None

    def test_helper_returns_none_when_field_absent(self):
        recs = [_title_rec("New Title")]
        assert safety._effective_field_value(recs, "description") is None

    def test_no_title_and_no_description_yields_no_findings(self):
        """A LOW-tier, tags-only entry has nothing for this check to
        compare -- must not fabricate a finding from nothing."""
        rec = _rec([{"field": "tags", "action": "add", "current": [], "proposed": ["pdf"],
                      "char_count": None, "source_keywords": ["pdf"], "rationale": "x"}])
        findings = safety._check_page_metadata_consistency(rec)
        assert findings == []


class TestSafetyGateIntegration:
    def test_consistency_warning_never_rejects_the_entry(self):
        rec = _rec([_title_rec(_REPEATED_TITLE), _desc_rec(_REPEATED_DESC)])
        passed, rejections = safety._gate_recommendation(rec, {}, {})
        assert passed is True
        assert rejections == []

    def test_consistency_warning_sets_requires_human_review(self):
        rec = _rec([_title_rec(_REPEATED_TITLE), _desc_rec(_REPEATED_DESC)])
        safety._gate_recommendation(rec, {}, {})
        assert rec["requires_human_review"] is True
        codes = {f["code"] for f in rec["metadata_consistency_findings"]}
        assert "title_description_near_literal_repetition" in codes
        assert "source_keyword_in_both_fields" in codes

    def test_clean_pair_yields_no_findings_and_no_forced_human_review(self):
        rec = _rec([_title_rec(_CLEAN_TITLE, current="Old Title"), _desc_rec(_CLEAN_DESC, current="Old description")])
        passed, rejections = safety._gate_recommendation(rec, {}, {})
        assert passed is True
        assert rejections == []
        assert rec["metadata_consistency_findings"] == []
        assert rec["requires_human_review"] is False

    def test_a_hard_reject_still_fires_before_check_4_5_ever_runs(self):
        """The per-field reject loop (checks 4-7) still short-circuits
        first -- check 4.5 only ever evaluates entries that already
        cleared every hard-reject gate."""
        too_short_title = "Too Short"
        rec = _rec([_title_rec(too_short_title), _desc_rec(_REPEATED_DESC)])
        passed, rejections = safety._gate_recommendation(rec, {}, {})
        assert passed is False
        assert rejections[0]["reason_code"] == "seo_title_length_violation"
        assert "metadata_consistency_findings" not in rec
