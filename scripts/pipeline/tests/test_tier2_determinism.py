"""Tests for Tier 2 embedding similarity determinism band (S2-2 fix).

The determinism band ensures scores in [0.65, 0.75) always escalate to Tier 3,
eliminating non-deterministic flips near the old 0.70 threshold.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Allow imports from scripts/gap-eval/
_GAP_EVAL_DIR = Path(__file__).resolve().parents[2] / "gap-eval" / "src"
if str(_GAP_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_GAP_EVAL_DIR))

import run as _run_mod  # noqa: E402

from run import (  # type: ignore  # noqa: E402
    tier2_verify,
    TIER2_MATCH_HIGH,
    TIER2_MATCH_LOW,
    TIER2_BAND_LOW,
    TIER2_MISMATCH,
)


@pytest.fixture(autouse=True)
def _reset_run():
    yield
    _run_mod.configure()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_claim(value: str = "SomeClass.someMethod") -> dict:
    return {"file": "content/docs/index.md", "line": 10, "type": "api-token", "value": value}


def _setup_vectors(tmp_path: Path, family: str, platform: str, vec: list[float]) -> Path:
    """Write a minimal api.vectors.json and return the repo root."""
    vdir = tmp_path / "knowledge" / "_vectors" / family / platform
    vdir.mkdir(parents=True, exist_ok=True)
    data = {"vectors": {"SomeClass.someMethod": vec}}
    (vdir / "api.vectors.json").write_text(json.dumps(data), encoding="utf-8")
    return tmp_path


def _patch_embed_and_cosine(cosine_score: float):
    """Return patches that make _embed_text return a dummy vector and _cosine return a fixed score."""
    dummy_vec = [1.0, 0.0, 0.0]
    return (
        patch("run._embed_text", return_value=dummy_vec),
        patch("run._cosine", return_value=cosine_score),
    )


# ---------------------------------------------------------------------------
# Constant sanity checks
# ---------------------------------------------------------------------------

class TestTier2Constants:
    def test_match_high_above_match_low(self):
        assert TIER2_MATCH_HIGH > TIER2_MATCH_LOW

    def test_band_low_below_match_low(self):
        assert TIER2_BAND_LOW < TIER2_MATCH_LOW

    def test_mismatch_below_band_low(self):
        assert TIER2_MISMATCH < TIER2_BAND_LOW

    def test_exact_values(self):
        assert TIER2_MATCH_HIGH == 0.75
        assert TIER2_MATCH_LOW == 0.70
        assert TIER2_BAND_LOW == 0.65
        assert TIER2_MISMATCH == 0.40


# ---------------------------------------------------------------------------
# Tier 2 verdict tests
# ---------------------------------------------------------------------------

class TestTier2DeterminismBand:
    """Verify that the determinism band [0.65, 0.75) always escalates."""

    def test_score_above_075_is_match(self, tmp_path):
        """Score >= 0.75 must always be MATCH."""
        repo = _setup_vectors(tmp_path, "test", "python", [1.0, 0.0, 0.0])
        claim = _make_claim()
        p_embed, p_cosine = _patch_embed_and_cosine(0.80)
        _run_mod.configure(repo_root=repo)
        with p_embed, p_cosine:
            result = tier2_verify(claim, "test", "python")
        assert result is not None
        verdict, score = result
        assert verdict == "MATCH"
        assert score == 0.80

    def test_score_at_exactly_075_is_match(self, tmp_path):
        """Score at exactly 0.75 must be MATCH (boundary)."""
        repo = _setup_vectors(tmp_path, "test", "python", [1.0, 0.0, 0.0])
        claim = _make_claim()
        p_embed, p_cosine = _patch_embed_and_cosine(0.75)
        _run_mod.configure(repo_root=repo)
        with p_embed, p_cosine:
            result = tier2_verify(claim, "test", "python")
        assert result is not None
        verdict, score = result
        assert verdict == "MATCH"
        assert score == 0.75

    def test_score_in_band_065_075_is_unverifiable(self, tmp_path):
        """Score in [0.65, 0.75) must always be UNVERIFIABLE (escalate)."""
        repo = _setup_vectors(tmp_path, "test", "python", [1.0, 0.0, 0.0])
        claim = _make_claim()
        for test_score in [0.65, 0.68, 0.70, 0.72, 0.749]:
            p_embed, p_cosine = _patch_embed_and_cosine(test_score)
            _run_mod.configure(repo_root=repo)
            with p_embed, p_cosine:
                result = tier2_verify(claim, "test", "python")
            assert result is not None, f"Expected result for score {test_score}"
            verdict, score = result
            assert verdict == "UNVERIFIABLE", (
                f"Score {test_score} should be UNVERIFIABLE (escalate), got {verdict}"
            )

    def test_score_at_exactly_070_escalates(self, tmp_path):
        """Score at exactly 0.70 (old threshold) must now escalate, not match."""
        repo = _setup_vectors(tmp_path, "test", "python", [1.0, 0.0, 0.0])
        claim = _make_claim()
        p_embed, p_cosine = _patch_embed_and_cosine(0.70)
        _run_mod.configure(repo_root=repo)
        with p_embed, p_cosine:
            result = tier2_verify(claim, "test", "python")
        assert result is not None
        verdict, score = result
        assert verdict == "UNVERIFIABLE", (
            "Score 0.70 was the old MATCH threshold; it must now escalate to Tier 3"
        )

    def test_score_below_040_is_mismatch(self, tmp_path):
        """Score < 0.40 must always be MISMATCH."""
        repo = _setup_vectors(tmp_path, "test", "python", [1.0, 0.0, 0.0])
        claim = _make_claim()
        p_embed, p_cosine = _patch_embed_and_cosine(0.30)
        _run_mod.configure(repo_root=repo)
        with p_embed, p_cosine:
            result = tier2_verify(claim, "test", "python")
        assert result is not None
        verdict, score = result
        assert verdict == "MISMATCH"
        assert score == 0.30

    def test_score_between_040_and_065_is_unverifiable(self, tmp_path):
        """Score in [0.40, 0.65) must be UNVERIFIABLE (escalate, below the band)."""
        repo = _setup_vectors(tmp_path, "test", "python", [1.0, 0.0, 0.0])
        claim = _make_claim()
        p_embed, p_cosine = _patch_embed_and_cosine(0.50)
        _run_mod.configure(repo_root=repo)
        with p_embed, p_cosine:
            result = tier2_verify(claim, "test", "python")
        assert result is not None
        verdict, score = result
        assert verdict == "UNVERIFIABLE"

    def test_score_at_exactly_040_is_unverifiable(self, tmp_path):
        """Score at exactly 0.40 (mismatch boundary) must be UNVERIFIABLE."""
        repo = _setup_vectors(tmp_path, "test", "python", [1.0, 0.0, 0.0])
        claim = _make_claim()
        p_embed, p_cosine = _patch_embed_and_cosine(0.40)
        _run_mod.configure(repo_root=repo)
        with p_embed, p_cosine:
            result = tier2_verify(claim, "test", "python")
        assert result is not None
        verdict, score = result
        assert verdict == "UNVERIFIABLE"


# ---------------------------------------------------------------------------
# Dimension mismatch WARNING (TC-12)
# ---------------------------------------------------------------------------

import logging


class TestTier2DimensionWarning:
    """Verify that tier2_verify logs WARNING when query dims ≠ stored dims."""

    def _setup_vectors_with_dims(self, tmp_path, family, platform, vec, dims):
        """Write api.vectors.json with a 'dimensions' metadata field."""
        vdir = tmp_path / "knowledge" / "_vectors" / family / platform
        vdir.mkdir(parents=True, exist_ok=True)
        data = {
            "dimensions": dims,
            "vectors": {"SomeClass.someMethod": vec},
        }
        (vdir / "api.vectors.json").write_text(json.dumps(data), encoding="utf-8")
        return tmp_path

    def test_dimension_mismatch_logs_warning(self, tmp_path, caplog):
        """When query vector dims ≠ stored dims, a WARNING must be logged."""
        # Stored vectors are 4-dim with metadata saying 4
        stored_vec = [1.0, 0.0, 0.0, 0.0]
        repo = self._setup_vectors_with_dims(tmp_path, "test", "python", stored_vec, 4)
        claim = _make_claim()

        # _embed_text returns a 2-dim vector (mismatched)
        query_vec = [1.0, 0.0]

        _run_mod.configure(repo_root=repo)
        with patch("run._embed_text", return_value=query_vec), \
             caplog.at_level(logging.WARNING, logger="run"):
            result = tier2_verify(claim, "test", "python")

        # Must warn about dimension mismatch
        assert any("Dimension mismatch" in msg for msg in caplog.messages), \
            f"Expected 'Dimension mismatch' WARNING, got: {caplog.messages}"

        # Must still return a result (does not abort — falls through to cosine/TF-IDF)
        assert result is not None

    def test_matching_dims_no_warning(self, tmp_path, caplog):
        """When query vector dims match stored dims, no WARNING should be logged."""
        stored_vec = [1.0, 0.0, 0.0]
        repo = self._setup_vectors_with_dims(tmp_path, "test", "python", stored_vec, 3)
        claim = _make_claim()

        query_vec = [0.5, 0.5, 0.0]

        _run_mod.configure(repo_root=repo)
        with patch("run._embed_text", return_value=query_vec), \
             caplog.at_level(logging.WARNING, logger="run"):
            result = tier2_verify(claim, "test", "python")

        assert not any("Dimension mismatch" in msg for msg in caplog.messages)
        assert result is not None
