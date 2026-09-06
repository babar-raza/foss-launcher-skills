"""Tests for scripts/seo/pipeline/recommendation_memory.py
(SEO-RECOMMENDATION-MEMORY) and its integration into recommend.py's
_gen_high_recommendations/_gen_medium_recommendations.

Finding #69: recommend.py called the LLM unconditionally on every scheduled
run for every misaligned-title/description opportunity, with no memory of
a prior run's proposal or S-116's real verdict on it. These tests cover the
module's 4 acceptance checks (unchanged+approved skips the LLM call,
unchanged+rejected does not regenerate, changed signal regenerates, the
hash function is deterministic) plus the real recommend.py integration
(a mocked _call_llm call-count reduction across two runs), all isolated
against a tmp_path repo root -- never the real reports/seo/ tree.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_SCRIPTS = Path(__file__).resolve().parents[2]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from seo.pipeline import recommendation_memory as rm  # noqa: E402
from seo.pipeline import pipeline_state as ps  # noqa: E402
import seo.pipeline.recommend as recommend  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_repo_root(tmp_path):
    rm.configure(repo_root=tmp_path)
    ps.configure(repo_root=tmp_path)
    yield tmp_path
    rm.configure()
    ps.configure()


@pytest.fixture(autouse=True)
def _clear_metrics_events():
    recommend.metrics_events.clear()
    yield
    recommend.metrics_events.clear()


# ---------------------------------------------------------------------------
# compute_signal_hash
# ---------------------------------------------------------------------------


class TestComputeSignalHash:
    def test_is_deterministic(self):
        kwargs = dict(current_value="Old Title", primary_kw="aspose words python",
                      family="words", platform="python")
        assert rm.compute_signal_hash(**kwargs) == rm.compute_signal_hash(**kwargs)

    def test_differs_when_current_value_changes(self):
        base = dict(primary_kw="aspose words python", family="words", platform="python")
        h1 = rm.compute_signal_hash(current_value="Old Title", **base)
        h2 = rm.compute_signal_hash(current_value="New Title", **base)
        assert h1 != h2

    def test_differs_when_family_changes(self):
        base = dict(current_value="Title", primary_kw="q", platform="python")
        h1 = rm.compute_signal_hash(family="words", **base)
        h2 = rm.compute_signal_hash(family="cells", **base)
        assert h1 != h2


# ---------------------------------------------------------------------------
# load_memory / consult_before_llm_call
# ---------------------------------------------------------------------------


class TestLoadMemory:
    def test_bootstraps_empty_when_no_store_exists(self):
        assert rm.load_memory() == {"schema_version": 1, "entries": {}}

    def test_corrupt_store_is_treated_as_empty_not_raised(self, _isolated_repo_root):
        store = _isolated_repo_root / "reports" / "seo" / "recommendation_memory.json"
        store.parent.mkdir(parents=True, exist_ok=True)
        store.write_text("{not valid json", encoding="utf-8")
        assert rm.load_memory() == {"schema_version": 1, "entries": {}}


class TestConsultBeforeLlmCall:
    _KW = dict(current_value="Old Title", primary_kw="aspose words python",
               family="words", platform="python")

    def test_no_prior_entry_calls_llm(self):
        result = rm.consult_before_llm_call("content/a.md", "seoTitle", **self._KW)
        assert result["should_call_llm"] is True
        assert result["reason"] == "no_prior_entry"

    def test_unchanged_signal_and_approved_outcome_skips_llm_call(self):
        """Acceptance check: unchanged-signal-skips-llm-call."""
        h = rm.compute_signal_hash(**self._KW)
        rm.record_result("content/a.md", "seoTitle", h,
                          {"proposed_title": "Great New Title", "rationale": "better"},
                          outcome="approved")
        result = rm.consult_before_llm_call("content/a.md", "seoTitle", **self._KW)
        assert result["should_call_llm"] is False
        assert result["cached_proposal"] == {"proposed_title": "Great New Title", "rationale": "better"}

    def test_unchanged_signal_and_pending_outcome_skips_llm_call(self):
        h = rm.compute_signal_hash(**self._KW)
        rm.record_result("content/a.md", "seoTitle", h,
                          {"proposed_title": "Pending Title", "rationale": "r"})
        result = rm.consult_before_llm_call("content/a.md", "seoTitle", **self._KW)
        assert result["should_call_llm"] is False
        assert result["cached_proposal"]["proposed_title"] == "Pending Title"

    def test_unchanged_signal_and_rejected_outcome_does_not_regenerate(self):
        """Acceptance check: rejected-and-unchanged-does-not-regenerate."""
        h = rm.compute_signal_hash(**self._KW)
        rm.record_result("content/a.md", "seoTitle", h,
                          {"proposed_title": "Bad Title", "rationale": "r"},
                          outcome="rejected_by_s116")
        result = rm.consult_before_llm_call("content/a.md", "seoTitle", **self._KW)
        assert result["should_call_llm"] is False
        assert result["reason"] == "stuck_rejected_by_s116"
        assert result["cached_proposal"] is None

    def test_unchanged_signal_and_requires_human_review_does_not_regenerate(self):
        h = rm.compute_signal_hash(**self._KW)
        rm.record_result("content/a.md", "seoTitle", h,
                          {"proposed_title": "T", "rationale": "r"},
                          outcome="requires_human_review")
        result = rm.consult_before_llm_call("content/a.md", "seoTitle", **self._KW)
        assert result["should_call_llm"] is False
        assert result["reason"] == "stuck_requires_human_review"

    def test_changed_signal_regenerates(self):
        """Acceptance check: changed-signal-regenerates."""
        h = rm.compute_signal_hash(**self._KW)
        rm.record_result("content/a.md", "seoTitle", h,
                          {"proposed_title": "Old Proposal", "rationale": "r"},
                          outcome="approved")
        changed = dict(self._KW, current_value="A Genuinely Different Title")
        result = rm.consult_before_llm_call("content/a.md", "seoTitle", **changed)
        assert result["should_call_llm"] is True
        assert result["reason"] == "signal_changed"

    def test_unknown_outcome_fails_open_to_regeneration(self):
        h = rm.compute_signal_hash(**self._KW)
        rm.record_result("content/a.md", "seoTitle", h,
                          {"proposed_title": "T", "rationale": "r"},
                          outcome="some_future_outcome_this_module_does_not_know")
        result = rm.consult_before_llm_call("content/a.md", "seoTitle", **self._KW)
        assert result["should_call_llm"] is True

    def test_different_field_is_independent(self):
        h = rm.compute_signal_hash(**self._KW)
        rm.record_result("content/a.md", "seoTitle", h,
                          {"proposed_title": "T", "rationale": "r"}, outcome="approved")
        result = rm.consult_before_llm_call("content/a.md", "description", **self._KW)
        assert result["should_call_llm"] is True
        assert result["reason"] == "no_prior_entry"


# ---------------------------------------------------------------------------
# record_result / record_outcome
# ---------------------------------------------------------------------------


class TestRecordResult:
    def test_writes_are_purely_additive_across_pages(self):
        h = rm.compute_signal_hash(current_value="A", primary_kw="q", family="f", platform="p")
        rm.record_result("content/a.md", "seoTitle", h, {"proposed_title": "A2", "rationale": "r"})
        rm.record_result("content/b.md", "seoTitle", h, {"proposed_title": "B2", "rationale": "r"})
        state = rm.load_memory()
        assert set(state["entries"]) == {"content/a.md", "content/b.md"}

    def test_never_raises_on_internal_failure(self, monkeypatch):
        monkeypatch.setattr(rm, "_save_atomic", lambda state: (_ for _ in ()).throw(OSError("disk full")))
        ok = rm.record_result("content/a.md", "seoTitle", "hash", {"proposed_title": "T"})
        assert ok is False

    def test_registers_into_pipeline_state_manifest(self, _isolated_repo_root):
        rm.record_result("content/a.md", "seoTitle", "hash", {"proposed_title": "T", "rationale": "r"})
        manifest = ps.load_pipeline_state()
        assert "recommendation_memory" in manifest["stages"]
        assert manifest["stages"]["recommendation_memory"]["path"] == "reports/seo/recommendation_memory.json"

    def test_does_not_leak_into_the_real_shared_tree(self, _isolated_repo_root):
        rm.record_result("content/a.md", "seoTitle", "hash", {"proposed_title": "T"})
        real_store = rm._DEFAULT_REPO_ROOT / "reports" / "seo" / "recommendation_memory.json"
        tmp_store = _isolated_repo_root / "reports" / "seo" / "recommendation_memory.json"
        assert tmp_store.exists()
        # The real store must be untouched by this test: either it doesn't
        # exist, or its content is unaffected (this page_path is never used
        # by any real production data, so it must not appear there).
        if real_store.exists():
            real_data = json.loads(real_store.read_text(encoding="utf-8"))
            assert "content/a.md" not in real_data.get("entries", {})


class TestRecordOutcome:
    def test_updates_an_existing_entry(self):
        h = rm.compute_signal_hash(current_value="A", primary_kw="q", family="f", platform="p")
        rm.record_result("content/a.md", "seoTitle", h, {"proposed_title": "T", "rationale": "r"})
        ok = rm.record_outcome("content/a.md", "seoTitle", "approved")
        assert ok is True
        assert rm.get_entry("content/a.md", "seoTitle")["outcome"] == "approved"

    def test_never_fabricates_a_missing_entry(self):
        ok = rm.record_outcome("content/never-seen.md", "seoTitle", "approved")
        assert ok is False
        assert rm.get_entry("content/never-seen.md", "seoTitle") is None

    def test_never_raises_on_internal_failure(self, monkeypatch):
        h = rm.compute_signal_hash(current_value="A", primary_kw="q", family="f", platform="p")
        rm.record_result("content/a.md", "seoTitle", h, {"proposed_title": "T"})
        monkeypatch.setattr(rm, "_save_atomic", lambda state: (_ for _ in ()).throw(OSError("boom")))
        ok = rm.record_outcome("content/a.md", "seoTitle", "approved")
        assert ok is False


# ---------------------------------------------------------------------------
# Real recommend.py integration: a genuine two-run call-count comparison
# ---------------------------------------------------------------------------


def _title_opp(title: str = "Old Unaligned Title") -> dict:
    return {
        "page_path": "content/docs.aspose.org/en/words/python/some-page.md",
        "signals": {
            "primary_query": "aspose words python",
            "matched_keywords": ["aspose words python"],
            "title_aligned": False,
            "description_ok": True,
            "tag_gap_count": 0,
        },
        "family": "words",
        "platform": "python",
        "seo_fields": {
            "seo_title": title,
            "description": "Convert documents",
            "tags": [],
        },
    }


@pytest.fixture
def mock_llm_router():
    router = MagicMock()
    response = MagicMock()
    response.status = "OK"
    with patch("seo.pipeline.recommend.LLMRouter", return_value=router) as router_cls:
        yield router_cls, router


class TestRecommendIntegration:
    def test_second_identical_run_makes_zero_llm_calls_after_approval(self, monkeypatch):
        """The real evidence requirement: a two-run comparison showing call-count
        reduction on the second run, against real recommend.py functions."""
        call_count = 0

        def fake_call_llm(prompt, model, schema, litellm_key):
            nonlocal call_count
            call_count += 1
            return {"proposed_title": "A Great New Title For Words Python SEO", "rationale": "better"}

        monkeypatch.setattr(recommend, "_call_llm", fake_call_llm)
        monkeypatch.setattr(
            recommend, "_compute_placement",
            lambda *a, **kw: (None, None, []),
        )

        opp = _title_opp()
        result1 = recommend._gen_high_recommendations(opp, litellm_key="fake-key")
        assert call_count == 1
        title_rec = next(r for r in result1["recommendations"] if r["field"] == "seoTitle")
        assert title_rec["proposed"] == "A Great New Title For Words Python SEO"

        # Simulate S-116 approving it.
        rm.record_outcome(opp["page_path"], "seoTitle", "approved")

        result2 = recommend._gen_high_recommendations(opp, litellm_key="fake-key")
        assert call_count == 1, "second identical run must not call the LLM again"
        title_rec2 = next(r for r in result2["recommendations"] if r["field"] == "seoTitle")
        assert title_rec2["proposed"] == "A Great New Title For Words Python SEO"

    def test_changed_title_triggers_a_fresh_llm_call(self, monkeypatch):
        call_count = 0

        def fake_call_llm(prompt, model, schema, litellm_key):
            nonlocal call_count
            call_count += 1
            return {"proposed_title": f"Proposal number {call_count}", "rationale": "r"}

        monkeypatch.setattr(recommend, "_call_llm", fake_call_llm)
        monkeypatch.setattr(recommend, "_compute_placement", lambda *a, **kw: (None, None, []))

        opp1 = _title_opp("Original Title")
        recommend._gen_high_recommendations(opp1, litellm_key="fake-key")
        assert call_count == 1

        opp2 = _title_opp("A Completely Different Original Title")
        recommend._gen_high_recommendations(opp2, litellm_key="fake-key")
        assert call_count == 2, "a genuinely changed title must regenerate, not reuse the cache"
