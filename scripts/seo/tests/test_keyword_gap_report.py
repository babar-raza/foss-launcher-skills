"""SEO-KEYWORD-GAP-REPORT: keyword_gap_report.py tests."""
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

import seo.pipeline.keyword_gap_report as gap_report  # noqa: E402


def test_classify_root_is_structural():
    assert gap_report._classify("https://blog.aspose.org/") == "structural"


def test_classify_single_segment_is_structural():
    assert gap_report._classify("https://blog.aspose.org/cells/") == "structural"


def test_classify_multi_segment_is_investigate():
    assert gap_report._classify("https://docs.aspose.org/pdf/net/some-old-page/") == "investigate"


def test_build_gap_report_excludes_matched_and_non_english(monkeypatch):
    monkeypatch.setattr(gap_report, "build_url_map", lambda: {
        "url_map": [
            {"gsc_url": "https://docs.aspose.org/pdf/net/gone/", "content_path": None, "lang": "en"},
            {"gsc_url": "https://docs.aspose.org/pdf/net/live/", "content_path": "content/x.md", "lang": "en"},
            {"gsc_url": "https://docs.aspose.org/fr/pdf/net/gone/", "content_path": None, "lang": "fr"},
        ],
        "match_stats": {"total_gsc_urls": 3},
    })
    monkeypatch.setattr(gap_report, "top_queries_for_url", lambda url, **kw: [{"query": "q", "impressions": 5}])

    report = gap_report.build_gap_report()
    urls = [c["gsc_url"] for c in report["investigate"] + report["structural"]]
    assert urls == ["https://docs.aspose.org/pdf/net/gone/"]
    assert report["meta"]["total_gap_candidates"] == 1


def test_build_gap_report_sorts_by_impressions_descending(monkeypatch):
    monkeypatch.setattr(gap_report, "build_url_map", lambda: {
        "url_map": [
            {"gsc_url": "https://docs.aspose.org/pdf/net/a/", "content_path": None, "lang": "en"},
            {"gsc_url": "https://docs.aspose.org/pdf/net/b/", "content_path": None, "lang": "en"},
        ],
        "match_stats": {"total_gsc_urls": 2},
    })

    def _fake_queries(url, **kw):
        return [{"query": "q", "impressions": 5 if url.endswith("a/") else 50}]

    monkeypatch.setattr(gap_report, "top_queries_for_url", _fake_queries)
    report = gap_report.build_gap_report()
    assert report["investigate"][0]["gsc_url"].endswith("b/")


def test_build_gap_report_handles_no_query_data(monkeypatch):
    monkeypatch.setattr(gap_report, "build_url_map", lambda: {
        "url_map": [{"gsc_url": "https://docs.aspose.org/pdf/net/a/", "content_path": None, "lang": "en"}],
        "match_stats": {"total_gsc_urls": 1},
    })
    monkeypatch.setattr(gap_report, "top_queries_for_url", lambda url, **kw: None)
    report = gap_report.build_gap_report()
    assert report["investigate"][0]["total_impressions"] == 0
    assert report["investigate"][0]["top_queries"] == []


def test_real_report_runs_against_live_data():
    """Smoke test against the real repo -- must not raise, and every
    candidate must be a genuinely unmatched, English URL."""
    report = gap_report.build_gap_report()
    assert report["meta"]["total_gap_candidates"] == (
        report["meta"]["investigate_count"] + report["meta"]["structural_count"]
    )
    for c in report["investigate"] + report["structural"]:
        assert c["classification"] in ("investigate", "structural")
