"""SEO-FAQ-KEYWORD-SEEDING: faq_keyword_seeding.py tests.

Every suggestion must carry unverified_against_claims=True and NEVER
include answer text -- this module only surfaces real search-demand
evidence, it does not (and cannot) verify or fabricate an answer.
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

import seo.pipeline.faq_keyword_seeding as seeding  # noqa: E402


def test_suggest_topics_returns_real_query_text(monkeypatch):
    monkeypatch.setattr(
        seeding, "top_queries_for_family_site",
        lambda site, family, limit=5, **kw: [{"query": "convert pdf to word", "impressions": 30}],
    )
    result = seeding.suggest_faq_question_topics("pdf")
    assert result[0]["topic_hint"] == "convert pdf to word"
    assert result[0]["impressions"] == 30
    assert result[0]["unverified_against_claims"] is True


def test_suggest_topics_never_includes_answer_text(monkeypatch):
    monkeypatch.setattr(
        seeding, "top_queries_for_family_site",
        lambda site, family, limit=5, **kw: [{"query": "q", "impressions": 1}],
    )
    result = seeding.suggest_faq_question_topics("pdf")
    assert "answer" not in result[0]
    assert set(result[0].keys()) == {"topic_hint", "impressions", "source_site", "unverified_against_claims"}


def test_suggest_topics_empty_when_no_query_data(monkeypatch):
    monkeypatch.setattr(seeding, "top_queries_for_family_site", lambda site, family, limit=5, **kw: None)
    assert seeding.suggest_faq_question_topics("pdf") == []


def test_suggest_topics_sorted_by_impressions_descending(monkeypatch):
    def _fake(site, family, limit=5, **kw):
        if site == "kb.aspose.org":
            return [{"query": "low", "impressions": 5}]
        return [{"query": "high", "impressions": 50}]
    monkeypatch.setattr(seeding, "top_queries_for_family_site", _fake)
    result = seeding.suggest_faq_question_topics("pdf")
    assert result[0]["topic_hint"] == "high"


def test_suggest_topics_dedupes_across_sites_keeping_highest_impressions(monkeypatch):
    def _fake(site, family, limit=5, **kw):
        if site == "kb.aspose.org":
            return [{"query": "shared query", "impressions": 5}]
        return [{"query": "shared query", "impressions": 50}]
    monkeypatch.setattr(seeding, "top_queries_for_family_site", _fake)
    result = seeding.suggest_faq_question_topics("pdf")
    assert len(result) == 1
    assert result[0]["impressions"] == 50


def test_suggest_topics_respects_limit(monkeypatch):
    monkeypatch.setattr(
        seeding, "top_queries_for_family_site",
        lambda site, family, limit=5, **kw: [{"query": f"q{i}", "impressions": i} for i in range(10)],
    )
    result = seeding.suggest_faq_question_topics("pdf", limit=3)
    assert len(result) == 3


def test_suggest_topics_degrades_gracefully_on_lookup_failure(monkeypatch):
    def _raise(site, family, limit=5, **kw):
        raise RuntimeError("simulated failure")
    monkeypatch.setattr(seeding, "top_queries_for_family_site", _raise)
    assert seeding.suggest_faq_question_topics("pdf") == []


def test_real_lookup_runs_against_live_data():
    """Smoke test against real repo data -- must not raise regardless of
    whether real signal exists for this family."""
    result = seeding.suggest_faq_question_topics("pdf")
    for entry in result:
        assert entry["unverified_against_claims"] is True
        assert "answer" not in entry
