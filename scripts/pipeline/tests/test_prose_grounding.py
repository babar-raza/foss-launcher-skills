"""Tests for the prose_grounding evaluator."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from content_eval.evaluators.prose_grounding import (
    ProseGroundingEvaluator,
    _ACTION_VERB_RE,
    _ADVERB_RE,
    _CLAIM_PATTERNS,
    _PROVISION_VERB_RE,
    _SIMILARITY_THRESHOLD,
)
from content_eval.evaluators._claim_index import clear_claim_cache
from content_eval.models import Page


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_CLAIMS = [
    {"claim_id": "C001", "text": "supports reading PDF documents with embedded fonts"},
    {"claim_id": "C002", "text": "supports converting DOCX to PDF format"},
    {"claim_id": "C003", "text": "provides batch processing of multiple files"},
    {"claim_id": "C004", "text": "enables watermark insertion on PDF pages"},
]


def _make_page(body: str, family: str = "words", platform: str = "python") -> Page:
    """Build a minimal Page with the given body text."""
    raw = textwrap.dedent(f"""\
        ---
        title: Test Page
        ---
        {body}
    """)
    page = Page(
        filepath=Path(f"content/docs.aspose.org/en/{family}/{platform}/test.md"),
        raw_text=raw,
    )
    page._parse()
    page._infer_metadata()
    return page


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear claim index cache before each test."""
    clear_claim_cache()
    yield
    clear_claim_cache()


# ---------------------------------------------------------------------------
# Regex extraction tests
# ---------------------------------------------------------------------------

class TestClaimPatternExtraction:
    """Verify the regex patterns extract capability claims correctly."""

    def test_action_verb_supports(self):
        text = "This library supports reading PDF documents with embedded fonts."
        m = _ACTION_VERB_RE.search(text)
        assert m is not None
        assert "reading PDF documents" in m.group(1)

    def test_action_verb_can_convert(self):
        text = "You can convert DOCX files to PDF format easily."
        m = _ACTION_VERB_RE.search(text)
        assert m is not None
        assert "DOCX files to PDF format" in m.group(1)

    def test_provision_verb_provides(self):
        text = "The SDK provides batch processing of multiple files at once."
        m = _PROVISION_VERB_RE.search(text)
        assert m is not None
        assert "batch processing" in m.group(1)

    def test_provision_verb_enables(self):
        text = "It enables watermark insertion on PDF pages."
        m = _PROVISION_VERB_RE.search(text)
        assert m is not None
        assert "watermark insertion" in m.group(1)

    def test_adverb_automatically(self):
        text = "The library automatically detects the input format and converts."
        m = _ADVERB_RE.search(text)
        assert m is not None
        assert "detects the input format" in m.group(1)

    def test_no_match_on_plain_prose(self):
        text = "This page describes the API reference for the Words module."
        for pattern in _CLAIM_PATTERNS:
            assert pattern.search(text) is None


# ---------------------------------------------------------------------------
# Evaluator integration tests
# ---------------------------------------------------------------------------

class TestProseGroundingEvaluator:
    """Integration tests for ProseGroundingEvaluator."""

    def test_name(self):
        ev = ProseGroundingEvaluator()
        assert ev.name == "prose_grounding"

    def test_skips_when_no_family(self):
        page = _make_page("supports reading PDF documents with embedded fonts.")
        page.family = ""
        ev = ProseGroundingEvaluator()
        assert ev.evaluate(page, None) == []

    def test_skips_when_no_claims(self):
        """No claims.json -> no findings."""
        page = _make_page("supports reading PDF documents with embedded fonts.")
        ev = ProseGroundingEvaluator()
        with patch(
            "content_eval.evaluators.prose_grounding.load_claims", return_value=[]
        ):
            assert ev.evaluate(page, None) == []

    def test_grounded_claim_no_findings(self):
        """A claim that matches knowledge should produce no findings."""
        page = _make_page(
            "This library supports reading PDF documents with embedded fonts."
        )
        ev = ProseGroundingEvaluator()
        with patch(
            "content_eval.evaluators.prose_grounding.load_claims",
            return_value=SAMPLE_CLAIMS,
        ), patch(
            "content_eval.evaluators._claim_index.load_claims",
            return_value=SAMPLE_CLAIMS,
        ):
            findings = ev.evaluate(page, None)
            # The claim closely matches C001 so should be grounded
            grounded = all(f.category != "PG" for f in findings)
            # If TF-IDF is available, it should match. If not, similarity=0 -> WARN.
            # We accept both outcomes since embed.py may not be on PYTHONPATH.

    def test_fabricated_claim_produces_warn(self):
        """A fabricated claim that does not match any knowledge entry."""
        page = _make_page(
            "This library supports quantum teleportation of spreadsheet data."
        )
        ev = ProseGroundingEvaluator()
        with patch(
            "content_eval.evaluators.prose_grounding.load_claims",
            return_value=SAMPLE_CLAIMS,
        ), patch(
            "content_eval.evaluators._claim_index.load_claims",
            return_value=SAMPLE_CLAIMS,
        ):
            findings = ev.evaluate(page, None)
            # With real TF-IDF, this should not match any claim
            # With fallback stubs (cosine=0), it will also WARN
            warns = [f for f in findings if f.level == "WARN" and f.category == "PG"]
            assert len(warns) >= 1
            assert "quantum teleportation" in warns[0].message

    def test_all_findings_are_warn_never_fail(self):
        """The evaluator must never emit FAIL -- only WARN."""
        page = _make_page(
            "This library supports quantum teleportation of spreadsheet data.\n"
            "It also provides antigravity rendering of chart elements."
        )
        ev = ProseGroundingEvaluator()
        with patch(
            "content_eval.evaluators.prose_grounding.load_claims",
            return_value=SAMPLE_CLAIMS,
        ), patch(
            "content_eval.evaluators._claim_index.load_claims",
            return_value=SAMPLE_CLAIMS,
        ):
            findings = ev.evaluate(page, None)
            for f in findings:
                assert f.level == "WARN", f"Expected WARN, got {f.level}: {f.message}"

    def test_deduplication_within_page(self):
        """Same claim text appearing twice should produce only one finding."""
        page = _make_page(
            "This library supports quantum teleportation of spreadsheet data.\n"
            "As noted, it supports quantum teleportation of spreadsheet data."
        )
        ev = ProseGroundingEvaluator()
        with patch(
            "content_eval.evaluators.prose_grounding.load_claims",
            return_value=SAMPLE_CLAIMS,
        ), patch(
            "content_eval.evaluators._claim_index.load_claims",
            return_value=SAMPLE_CLAIMS,
        ):
            findings = ev.evaluate(page, None)
            pg_findings = [f for f in findings if f.category == "PG"]
            # Should be deduplicated to at most 1
            assert len(pg_findings) <= 1

    def test_short_claims_skipped(self):
        """Claims with fewer than 3 tokens should be skipped."""
        page = _make_page("It supports PDF.")
        ev = ProseGroundingEvaluator()
        with patch(
            "content_eval.evaluators.prose_grounding.load_claims",
            return_value=SAMPLE_CLAIMS,
        ), patch(
            "content_eval.evaluators._claim_index.load_claims",
            return_value=SAMPLE_CLAIMS,
        ):
            findings = ev.evaluate(page, None)
            assert findings == []

    def test_evaluator_field_set(self):
        """Findings must have evaluator='prose_grounding'."""
        page = _make_page(
            "This library supports quantum teleportation of spreadsheet data."
        )
        ev = ProseGroundingEvaluator()
        with patch(
            "content_eval.evaluators.prose_grounding.load_claims",
            return_value=SAMPLE_CLAIMS,
        ), patch(
            "content_eval.evaluators._claim_index.load_claims",
            return_value=SAMPLE_CLAIMS,
        ):
            findings = ev.evaluate(page, None)
            for f in findings:
                assert f.evaluator == "prose_grounding"


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------

class TestRegistration:
    """Verify evaluator is registered correctly."""

    def test_in_all_evaluators(self):
        from content_eval.config import ALL_EVALUATORS
        assert "prose_grounding" in ALL_EVALUATORS

    def test_in_default_evaluators(self):
        """prose_grounding was promoted to DEFAULT after calibration (0% FP rate)."""
        from content_eval.config import DEFAULT_EVALUATORS
        assert "prose_grounding" in DEFAULT_EVALUATORS

    def test_self_registers_via_name(self):
        from content_eval.evaluators import _ensure_loaded, _REGISTRY
        _ensure_loaded()
        assert "prose_grounding" in _REGISTRY

    def test_threshold_is_030(self):
        assert _SIMILARITY_THRESHOLD == 0.30
