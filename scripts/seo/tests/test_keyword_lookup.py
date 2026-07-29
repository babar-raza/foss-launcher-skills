"""SEO-000b keyword_lookup.py tests.

Covers the foundational URL -> top-queries lookup that every later-phase
consumer (title templates, FAQ seeding, traffic-tier, content-gap) is meant
to share, per Finding #3's scoping (English-matched only, explicit no-data
result, never a fabricated zero).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure scripts/seo and scripts/pipeline are on sys.path
_SCRIPTS = Path(__file__).resolve().parents[2]
_PIPELINE = _SCRIPTS / "pipeline"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
if str(_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_PIPELINE))

import seo.pipeline.keyword_lookup as kl  # noqa: E402

_REPO_ROOT = _SCRIPTS.parents[0]
_KEYWORDS_DIR = _REPO_ROOT / "keywords"


def _write_schema_b_fixture(tmp_path: Path, filename: str, entries: list[dict]) -> None:
    (tmp_path / filename).write_text(json.dumps(entries), encoding="utf-8")


class TestLoadAllQueries:
    def test_english_only(self, tmp_path):
        _write_schema_b_fixture(tmp_path, "docs.aspose.org.json", [
            {"url": "https://docs.aspose.org/en-page/", "lang": "en", "lastUpdated": "2026-07-26",
             "queries": [{"query": "x", "clicks": 1, "impressions": 10, "ctr": 0.1, "position": 5.0}]},
            {"url": "https://docs.aspose.org/de-page/", "lang": "de", "lastUpdated": "2026-07-26",
             "queries": [{"query": "y", "clicks": 1, "impressions": 10, "ctr": 0.1, "position": 5.0}]},
        ])
        result = kl.load_all_queries(tmp_path)
        assert "https://docs.aspose.org/en-page/" in result
        assert "https://docs.aspose.org/de-page/" not in result

    def test_empty_dir(self, tmp_path):
        assert kl.load_all_queries(tmp_path) == {}


class TestTopQueriesForUrl:
    def test_sorted_by_impressions_desc(self, tmp_path):
        _write_schema_b_fixture(tmp_path, "docs.aspose.org.json", [
            {"url": "https://docs.aspose.org/words/", "lang": "en", "lastUpdated": "2026-07-26",
             "queries": [
                 {"query": "low", "clicks": 0, "impressions": 5, "ctr": 0.0, "position": 20.0},
                 {"query": "high", "clicks": 3, "impressions": 50, "ctr": 0.06, "position": 3.0},
                 {"query": "mid", "clicks": 1, "impressions": 15, "ctr": 0.06, "position": 10.0},
             ]},
        ])
        result = kl.top_queries_for_url("https://docs.aspose.org/words/", keywords_dir=tmp_path)
        assert [q["query"] for q in result] == ["high", "mid", "low"]

    def test_respects_limit(self, tmp_path):
        _write_schema_b_fixture(tmp_path, "docs.aspose.org.json", [
            {"url": "https://docs.aspose.org/words/", "lang": "en", "lastUpdated": "2026-07-26",
             "queries": [
                 {"query": f"q{i}", "clicks": 0, "impressions": i, "ctr": 0.0, "position": 5.0}
                 for i in range(10)
             ]},
        ])
        result = kl.top_queries_for_url("https://docs.aspose.org/words/", limit=3, keywords_dir=tmp_path)
        assert len(result) == 3
        assert result[0]["query"] == "q9"

    def test_returns_none_for_unmatched_url(self, tmp_path):
        _write_schema_b_fixture(tmp_path, "docs.aspose.org.json", [
            {"url": "https://docs.aspose.org/words/", "lang": "en", "lastUpdated": "2026-07-26",
             "queries": [{"query": "x", "clicks": 0, "impressions": 5, "ctr": 0.0, "position": 5.0}]},
        ])
        result = kl.top_queries_for_url("https://docs.aspose.org/pdf/", keywords_dir=tmp_path)
        assert result is None, "an unmatched URL must return None, never an empty-but-truthy fallback"

    def test_returns_none_when_no_queries_present(self, tmp_path):
        _write_schema_b_fixture(tmp_path, "docs.aspose.org.json", [
            {"url": "https://docs.aspose.org/words/", "lang": "en", "lastUpdated": "2026-07-26",
             "queries": []},
        ])
        result = kl.top_queries_for_url("https://docs.aspose.org/words/", keywords_dir=tmp_path)
        assert result is None


class TestTopQueriesForFamilySite:
    def test_aggregates_across_family_urls(self, tmp_path):
        _write_schema_b_fixture(tmp_path, "docs.aspose.org.json", [
            {"url": "https://docs.aspose.org/pdf/net/", "lang": "en", "lastUpdated": "2026-07-26",
             "queries": [{"query": "net query", "clicks": 0, "impressions": 5, "ctr": 0.0, "position": 5.0}]},
            {"url": "https://docs.aspose.org/pdf/java/", "lang": "en", "lastUpdated": "2026-07-26",
             "queries": [{"query": "java query", "clicks": 0, "impressions": 20, "ctr": 0.0, "position": 5.0}]},
            {"url": "https://docs.aspose.org/words/net/", "lang": "en", "lastUpdated": "2026-07-26",
             "queries": [{"query": "unrelated", "clicks": 0, "impressions": 999, "ctr": 0.0, "position": 5.0}]},
        ])
        result = kl.top_queries_for_family_site("docs.aspose.org", "pdf", keywords_dir=tmp_path)
        queries = [q["query"] for q in result]
        assert "java query" in queries and "net query" in queries
        assert "unrelated" not in queries, "a different family's queries must not leak in"
        assert queries[0] == "java query", "must be sorted by impressions desc"

    def test_returns_none_when_no_family_match(self, tmp_path):
        _write_schema_b_fixture(tmp_path, "docs.aspose.org.json", [
            {"url": "https://docs.aspose.org/words/net/", "lang": "en", "lastUpdated": "2026-07-26",
             "queries": [{"query": "x", "clicks": 0, "impressions": 5, "ctr": 0.0, "position": 5.0}]},
        ])
        result = kl.top_queries_for_family_site("docs.aspose.org", "pdf", keywords_dir=tmp_path)
        assert result is None


class TestRealDataSmoke:
    """Sanity checks against this repo's real keywords/ directory."""

    def test_loads_without_error_against_real_data(self):
        result = kl.load_all_queries(_KEYWORDS_DIR)
        assert isinstance(result, dict)

    def test_known_real_url_has_data(self):
        # keywords/docs.aspose.org.json's first documented entry (verified
        # directly during this mission's investigation phase).
        result = kl.top_queries_for_url("https://docs.aspose.org/words/", keywords_dir=_KEYWORDS_DIR)
        assert result is not None
        assert any(q["query"] == "foss word" for q in result)
