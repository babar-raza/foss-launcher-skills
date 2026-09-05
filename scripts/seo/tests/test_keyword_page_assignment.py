"""SEO-KEYWORD-PAGE-ASSIGNMENT (Contract B) tests.

Design authority: C:\\Users\\prora\\.claude\\plans\\
check-keywords-this-data-curious-feather.md lines 628-659 (Findings #82/#83).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure scripts/seo and scripts/pipeline are on sys.path (same pattern as
# test_map_url_resolution.py).
_SCRIPTS = Path(__file__).resolve().parents[2]
_PIPELINE = _SCRIPTS / "pipeline"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
if str(_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_PIPELINE))

from seo.pipeline.keyword_page_assignment import (  # noqa: E402
    CANNIBALIZATION_AMBIGUOUS,
    CANNIBALIZATION_NONE,
    CANNIBALIZATION_RISK,
    PLACEMENT_DO_NOT_USE,
    PLACEMENT_HUMAN_REVIEW,
    build_query_index,
    check_cannibalization,
    is_locale_pair,
)

_REPO_ROOT = _SCRIPTS.parents[0]
_KEYWORDS_DIR = _REPO_ROOT / "keywords"


def _ranking(query: str, url: str, site: str, impressions: int, position: float) -> dict:
    return {"query": query, "url": url, "site": site, "impressions": impressions, "position": position}


# ---------------------------------------------------------------------------
# Golden case: the historically-confirmed "pip install aspose" pair
# (Finding #73/#82, v14 line 630). Reproduced synthetically -- re-verified
# 2026-09-05 that this exact two-URL case has since drifted out of live
# keywords/docs.aspose.org.json (the cells URL no longer ranks for this
# query at all in current weekly-refreshed data); the historical numbers
# (impressions=6/position=12.17 for cells, impressions=11/position=8.55 for
# words) are preserved here as a fixture, not asserted as still-live.
# ---------------------------------------------------------------------------


class TestPipInstallAsposeGoldenCase:
    _CELLS_URL = "https://docs.aspose.org/cells/python/getting-started/installation/"
    _WORDS_URL = "https://docs.aspose.org/words/python/getting-started/installation/"

    def _index(self) -> dict:
        return {
            "pip install aspose": [
                _ranking("pip install aspose", self._WORDS_URL, "docs.aspose.org", 11, 8.55),
                _ranking("pip install aspose", self._CELLS_URL, "docs.aspose.org", 6, 12.17),
            ]
        }

    def test_cells_candidate_is_risk(self):
        result = check_cannibalization("pip install aspose", self._CELLS_URL, self._index())
        assert result["verdict"] == CANNIBALIZATION_RISK
        assert result["competitor_url"] == self._WORDS_URL
        assert result["margin"] == 12.17 - 8.55
        assert result["margin"] >= 3.0

    def test_words_candidate_is_none(self):
        result = check_cannibalization("pip install aspose", self._WORDS_URL, self._index())
        assert result["verdict"] == CANNIBALIZATION_NONE
        assert result["competitor_url"] is None


# ---------------------------------------------------------------------------
# Real, currently-live cross-site case (re-verified 2026-09-05): "net pdf
# annotation" ranks kb.aspose.org and blog.aspose.org independently -- two
# different Schema B files, discoverable only by a cross-site union index.
# ---------------------------------------------------------------------------


class TestRealCrossSiteCase:
    _KB_URL = "https://kb.aspose.org/pdf/net/how-to-add-pdf-annotations-dotnet/"
    _BLOG_URL = "https://blog.aspose.org/pdf/net/pdf-annotations-forms-net/"

    def test_both_urls_present_and_cross_site(self):
        index = build_query_index(union_all_sites=True, keywords_dir=_KEYWORDS_DIR)
        rankings = index.get("net pdf annotation", [])
        sites = {r["site"] for r in rankings if r["url"] in (self._KB_URL, self._BLOG_URL)}
        assert sites == {"kb.aspose.org", "blog.aspose.org"}, (
            "the real cross-site case this test pins against must still be live -- "
            "if this fails, keywords/*.json data has drifted; find a fresh real "
            "cross-site pair and update this test"
        )

    def test_cross_site_forces_human_review_for_both_candidates(self):
        index = build_query_index(union_all_sites=True, keywords_dir=_KEYWORDS_DIR)
        for candidate in (self._KB_URL, self._BLOG_URL):
            result = check_cannibalization("net pdf annotation", candidate, index)
            assert result["verdict"] == CANNIBALIZATION_RISK
            assert result["placement_override"] == PLACEMENT_HUMAN_REVIEW
            assert result["same_site_only"] is False


# ---------------------------------------------------------------------------
# Cross-site union (Finding #82) -- synthetic, deterministic counterpart
# ---------------------------------------------------------------------------


class TestCrossSiteUnionSynthetic:
    def test_single_site_index_hides_the_second_site(self):
        """A per-site-only index (the pre-Finding-#82 design) cannot see the
        competing site at all -- proves the regression Finding #82 fixed was
        real, not hypothetical."""
        candidate = "https://kb.aspose.org/pt/3d/net/"
        same_site_index = {
            "aspose 3d": [_ranking("aspose 3d", candidate, "kb.aspose.org", 24, 6.0)],
        }
        result = check_cannibalization("aspose 3d", candidate, same_site_index)
        assert result["verdict"] == CANNIBALIZATION_NONE
        assert result["same_site_only"] is True

    def test_cross_site_union_forces_human_review(self):
        candidate = "https://kb.aspose.org/pt/3d/net/"
        competitor = "https://products.aspose.org/es/3d/"
        union_index = {
            "aspose 3d": [
                _ranking("aspose 3d", competitor, "products.aspose.org", 43, 2.37),
                _ranking("aspose 3d", candidate, "kb.aspose.org", 24, 6.0),
            ],
        }
        result = check_cannibalization("aspose 3d", candidate, union_index)
        assert result["verdict"] == CANNIBALIZATION_RISK
        assert result["placement_override"] == PLACEMENT_HUMAN_REVIEW
        assert result["same_site_only"] is False


# ---------------------------------------------------------------------------
# Locale-pair exclusion
# ---------------------------------------------------------------------------


class TestLocalePairExclusion:
    def test_is_locale_pair_true_for_real_live_pair(self):
        # Real, currently-live locale pair (re-verified 2026-09-05):
        # products.aspose.org/pt/pdf/ vs /ru/pdf/, both real floor-clearing
        # entries for "aspose pdf" today.
        assert is_locale_pair(
            "https://products.aspose.org/pt/pdf/",
            "https://products.aspose.org/ru/pdf/",
        )

    def test_is_locale_pair_false_for_different_paths(self):
        assert not is_locale_pair(
            "https://products.aspose.org/pt/pdf/",
            "https://products.aspose.org/pt/words/",
        )

    def test_is_locale_pair_false_for_different_domains(self):
        assert not is_locale_pair(
            "https://products.aspose.org/pt/pdf/",
            "https://kb.aspose.org/pt/pdf/",
        )

    def test_is_locale_pair_true_for_content_path_vs_real_url(self):
        """Regression for a real bug found by independent review: a Path-B
        candidate is identified by its bare content path (no scheme/netloc),
        not a real URL, since it has no observed GSC url of its own. The
        first version of is_locale_pair() urlparsed a schemeless string to
        an empty netloc, which could never equal a real site's netloc, so
        locale-pair exclusion silently never fired for any Path-B page."""
        assert is_locale_pair(
            "content/products.aspose.org/pt/pdf/_index.md",
            "https://products.aspose.org/ru/pdf/",
        )

    def test_is_locale_pair_true_for_two_content_paths(self):
        assert is_locale_pair(
            "content/products.aspose.org/pt/pdf/_index.md",
            "content/products.aspose.org/ru/pdf/_index.md",
        )

    def test_is_locale_pair_false_for_content_path_different_family(self):
        assert not is_locale_pair(
            "content/products.aspose.org/pt/pdf/_index.md",
            "content/products.aspose.org/ru/words/_index.md",
        )

    def test_hr_is_a_recognized_locale_code(self):
        """Regression: hr (Croatian) is a real, currently-declared legacy
        locale in every site's configs/*.toml disableLanguages list (e.g.
        configs/products.aspose.org.toml's [languages.hr] with previously-
        deployed Ceph pages), but was missing from the first version of
        _LOCALE_CODES -- found by independent review."""
        assert is_locale_pair(
            "https://products.aspose.org/hr/pdf/",
            "https://products.aspose.org/ru/pdf/",
        )

    def test_content_path_candidate_excluded_from_margin_check(self):
        """End-to-end regression for the Path-B locale-exclusion bug: a
        content-path candidate's own real locale variant must never be
        surfaced as its competitor_url, exactly like a real-URL candidate.
        The candidate itself has no ranking data (it's a Path-B page with no
        observed GSC url), so the correct verdict is AMBIGUOUS (genuinely
        low signal), not a false RISK naming the locale sibling as a rival."""
        candidate = "content/products.aspose.org/pt/pdf/_index.md"
        locale_variant = "https://products.aspose.org/ru/pdf/"
        index = {
            "aspose pdf": [
                _ranking("aspose pdf", locale_variant, "products.aspose.org", 33, 4.97),
            ],
        }
        result = check_cannibalization("aspose pdf", candidate, index)
        assert result["verdict"] == CANNIBALIZATION_AMBIGUOUS
        assert result["competitor_url"] is None, (
            "the locale variant must never be surfaced as a competitor, even "
            "when it is the only other entry in the index"
        )

    def test_locale_pair_excluded_from_margin_check_despite_large_margin(self):
        candidate = "https://products.aspose.org/pt/pdf/"
        locale_variant = "https://products.aspose.org/ru/pdf/"
        index = {
            "aspose pdf": [
                _ranking("aspose pdf", locale_variant, "products.aspose.org", 33, 4.97),
                _ranking("aspose pdf", candidate, "products.aspose.org", 16, 20.0),  # huge margin
            ],
        }
        result = check_cannibalization("aspose pdf", candidate, index)
        assert result["verdict"] == CANNIBALIZATION_NONE, (
            "a locale variant of the same page must never be treated as a "
            "competitor, no matter how large the position margin"
        )
        assert result["competitor_url"] is None


# ---------------------------------------------------------------------------
# AMBIGUOUS (neither URL clears the floor)
# ---------------------------------------------------------------------------


class TestAmbiguousLowSignal:
    def test_neither_clears_floor_is_ambiguous_not_none(self):
        candidate = "https://docs.aspose.org/a/"
        competitor = "https://docs.aspose.org/b/"
        index = {
            "rare query": [
                _ranking("rare query", competitor, "docs.aspose.org", 3, 5.0),
                _ranking("rare query", candidate, "docs.aspose.org", 2, 40.0),
            ],
        }
        result = check_cannibalization("rare query", candidate, index, impression_floor=10)
        assert result["verdict"] == CANNIBALIZATION_AMBIGUOUS

    def test_no_ranking_at_all_is_none_not_ambiguous(self):
        result = check_cannibalization("never seen query", "https://docs.aspose.org/x/", {})
        assert result["verdict"] == CANNIBALIZATION_NONE
        assert result["competitor_url"] is None


# ---------------------------------------------------------------------------
# Impression-ratio softening (RISK -> HUMAN_REVIEW instead of DO_NOT_USE)
# ---------------------------------------------------------------------------


class TestImpressionRatioSoftening:
    def test_large_margin_similar_impressions_is_do_not_use(self):
        candidate = "https://docs.aspose.org/a/"
        competitor = "https://docs.aspose.org/b/"
        index = {
            "q": [
                _ranking("q", competitor, "docs.aspose.org", 20, 3.0),
                _ranking("q", candidate, "docs.aspose.org", 22, 10.0),
            ],
        }
        result = check_cannibalization("q", candidate, index)
        assert result["verdict"] == CANNIBALIZATION_RISK
        assert result["placement_override"] == PLACEMENT_DO_NOT_USE

    def test_large_margin_skewed_impressions_is_human_review(self):
        candidate = "https://docs.aspose.org/a/"
        competitor = "https://docs.aspose.org/b/"
        index = {
            "q": [
                _ranking("q", competitor, "docs.aspose.org", 500, 3.0),
                _ranking("q", candidate, "docs.aspose.org", 15, 10.0),  # >2x impression ratio
            ],
        }
        result = check_cannibalization("q", candidate, index)
        assert result["verdict"] == CANNIBALIZATION_RISK
        assert result["placement_override"] == PLACEMENT_HUMAN_REVIEW


# ---------------------------------------------------------------------------
# Known residual near-miss gap (v1 scope, Finding #82) -- documented, not
# silently hidden. Synthetic reproduction of the historically-confirmed
# reference.aspose.org "saveformat" near-miss shape (margin ~1-2, ratio
# ~1.1x); re-verified 2026-09-05 that the real competing URL for this query
# has since dropped out of live data, so this is a characterization test of
# the rule set's known limit, not a live-data pin.
# ---------------------------------------------------------------------------


class TestKnownResidualNearMissGap:
    def test_small_margin_both_floor_clearing_silently_returns_none(self):
        candidate = "https://reference.aspose.org/en/slides/net/SaveFormat.md"
        competitor = "https://reference.aspose.org/en/slides/net/SaveFormat.Overload.md"
        index = {
            "saveformat": [
                _ranking("saveformat", competitor, "reference.aspose.org", 8000, 6.6),
                _ranking("saveformat", candidate, "reference.aspose.org", 7400, 8.35),  # margin 1.75
            ],
        }
        result = check_cannibalization("saveformat", candidate, index)
        assert result["verdict"] == CANNIBALIZATION_NONE, (
            "documented known gap: a sub-3.0-margin competitor is not flagged even "
            "though both clear the floor -- see the module docstring and Contract B's "
            "own stated residual-gap note"
        )
        assert any("residual gap" in r for r in result["reasons"])


# ---------------------------------------------------------------------------
# In-run claimed-queries tracking
# ---------------------------------------------------------------------------


class TestInRunClaimedQueries:
    def test_second_page_claiming_same_query_forced_to_human_review(self):
        index: dict = {}  # brand-new query, no historical data at all
        claimed: dict[str, str] = {}

        first = check_cannibalization("brand new query", "https://docs.aspose.org/first/", index, claimed_this_run=claimed)
        claimed["brand new query"] = "https://docs.aspose.org/first/"
        assert first["verdict"] == CANNIBALIZATION_NONE
        assert first["placement_override"] is None

        second = check_cannibalization("brand new query", "https://docs.aspose.org/second/", index, claimed_this_run=claimed)
        assert second["placement_override"] == PLACEMENT_HUMAN_REVIEW

    def test_same_page_reclaiming_its_own_query_is_not_flagged(self):
        index: dict = {}
        claimed = {"q": "https://docs.aspose.org/same/"}
        result = check_cannibalization("q", "https://docs.aspose.org/same/", index, claimed_this_run=claimed)
        assert result["placement_override"] is None


# ---------------------------------------------------------------------------
# Determinism (Tier-1 idempotent, byte-identical output)
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_build_query_index_is_byte_identical_across_runs(self):
        first = build_query_index(union_all_sites=True, keywords_dir=_KEYWORDS_DIR)
        second = build_query_index(union_all_sites=True, keywords_dir=_KEYWORDS_DIR)
        assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)

    def test_union_all_sites_false_requires_site(self):
        import pytest

        with pytest.raises(ValueError):
            build_query_index(union_all_sites=False, keywords_dir=_KEYWORDS_DIR)

    def test_single_site_mode_only_includes_that_site(self):
        index = build_query_index(site="kb.aspose.org", union_all_sites=False, keywords_dir=_KEYWORDS_DIR)
        for rankings in index.values():
            for r in rankings:
                assert r["site"] == "kb.aspose.org"
