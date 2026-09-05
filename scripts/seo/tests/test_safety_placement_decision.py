"""SEO-KEYWORD-INTENT-CONTRACT (Contract A): safety.py's new
_check_placement_decision backstop -- "never trust an upstream stage's
decision without a downstream re-check" applied to the new contract.

Acceptance check mirrored here: safety-backstop-catches-a-bypassed-do-not-use
-- a synthetic recommendation whose signals['placement'] is do_not_use but
which still proposes injecting the literal keyword must be rejected, not
silently passed through. A real adversarial test, not a passing-case
demonstration.
"""
from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[2]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import seo.pipeline.safety as safety  # noqa: E402


def _rec(field_recs, family=None, platform=None):
    return {
        "page_path": "content/docs.aspose.org/en/pdf/python/_index.md",
        "family": family,
        "platform": platform,
        "recommendations": field_recs,
    }


class TestCheckPlacementDecisionUnit:
    def test_bypassed_do_not_use_is_rejected(self):
        r = {
            "field": "seoTitle",
            "proposed": "The Best PDF to Word Converter Tool for Python",
            "signals": {"placement": "do_not_use", "source_query": "pdf to word converter"},
        }
        passed, code, detail = safety._check_placement_decision(r)
        assert not passed
        assert code == "placement_decision_bypass"
        assert "pdf to word converter" in detail

    def test_bypassed_human_review_is_rejected(self):
        r = {
            "field": "description",
            "proposed": "Learn how to use our free online PDF converter today.",
            "signals": {"placement": "human_review", "source_query": "free online pdf converter"},
        }
        passed, code, detail = safety._check_placement_decision(r)
        assert not passed
        assert code == "placement_decision_bypass"

    def test_case_insensitive_match(self):
        r = {
            "field": "seoTitle",
            "proposed": "Best PDF TO WORD Converter",
            "signals": {"placement": "do_not_use", "source_query": "pdf to word"},
        }
        passed, _, _ = safety._check_placement_decision(r)
        assert not passed

    def test_do_not_use_but_proposed_text_avoids_the_query_passes(self):
        """The backstop only fires when the literal query is actually
        injected -- a proposal that respected the disposition and wrote
        around it must not be penalized."""
        r = {
            "field": "seoTitle",
            "proposed": "Document Processing Library for Python Developers",
            "signals": {"placement": "do_not_use", "source_query": "pdf to word converter"},
        }
        passed, _, _ = safety._check_placement_decision(r)
        assert passed

    def test_use_exact_disposition_never_blocks(self):
        r = {
            "field": "seoTitle",
            "proposed": "Convert PDF to Word in Python",
            "signals": {"placement": "use_exact", "source_query": "convert pdf to word python"},
        }
        passed, _, _ = safety._check_placement_decision(r)
        assert passed

    def test_missing_signals_block_is_not_a_violation(self):
        """Every recommendation shape that predates this contract (and
        fields this contract doesn't classify, e.g. tags) has no signals
        block at all -- nothing to re-check, must not be rejected."""
        r = {"field": "tags", "proposed": ["convert", "pdf"]}
        passed, _, _ = safety._check_placement_decision(r)
        assert passed

    def test_proposed_none_is_not_a_violation(self):
        r = {
            "field": "seoTitle",
            "proposed": None,
            "signals": {"placement": "do_not_use", "source_query": "pdf to word"},
        }
        passed, _, _ = safety._check_placement_decision(r)
        assert passed

    def test_missing_source_query_is_not_a_violation(self):
        r = {
            "field": "seoTitle",
            "proposed": "PDF to Word Converter",
            "signals": {"placement": "do_not_use"},
        }
        passed, _, _ = safety._check_placement_decision(r)
        assert passed


class TestGateRecommendationEndToEnd:
    def test_bypassed_do_not_use_rejected_through_full_gate(self):
        """Real adversarial test through _gate_recommendation (not just the
        unit function): a full recommendation entry, built the same shape
        recommend.py emits, must be rejected end-to-end."""
        rec = _rec([{
            "field": "seoTitle",
            "action": "rewrite",
            "current": "Aspose.PDF for Python",
            "proposed": "The Ultimate PDF to Word Converter for Python Developers",
            "char_count": 58,
            "source_keywords": ["pdf to word converter"],
            "rationale": "LLM-proposed rewrite.",
            "signals": {
                "placement": "do_not_use",
                "confidence": 0.9,
                "reasons": ["cannibalization risk"],
                "source_query": "pdf to word converter",
            },
        }])
        passed, rejections = safety._gate_recommendation(rec, {}, {})
        assert not passed
        assert any(r["reason_code"] == "placement_decision_bypass" for r in rejections)

    def test_use_exact_disposition_passes_through_full_gate(self):
        rec = _rec([{
            "field": "seoTitle",
            "action": "rewrite",
            "current": "Aspose.PDF for Python",
            "proposed": "Convert PDF to Word Documents Using Python Today Online",
            "char_count": 55,
            "source_keywords": ["convert pdf to word python"],
            "rationale": "LLM-proposed rewrite.",
            "signals": {
                "placement": "use_exact",
                "confidence": 0.9,
                "reasons": ["deterministic parse"],
                "source_query": "convert pdf to word python",
            },
        }])
        passed, rejections = safety._gate_recommendation(rec, {}, {})
        assert passed
        assert rejections == []
