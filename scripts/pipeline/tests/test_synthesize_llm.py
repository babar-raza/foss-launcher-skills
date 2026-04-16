"""Tests for synthesize.py LLMRouter migration (TC-14 / SR-02).

Covers:
  - embed_findings: happy path via LLMRouter, metadata in output
  - embed_findings: TF-IDF fallback when router unavailable
  - name_cluster: happy path via LLMRouter
  - name_cluster: fallback when router unavailable
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

_GAP_EVAL_DIR = Path(__file__).resolve().parents[2] / "gap-eval"
_PIPELINE_DIR = Path(__file__).resolve().parents[2] / "pipeline"
if str(_GAP_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_GAP_EVAL_DIR))
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

from synthesize import embed_findings, name_cluster, _tfidf_embed  # type: ignore  # noqa: E402
from llm_router import EndpointStatus, CallResult  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _sample_findings(n=3):
    return [
        {
            "id": f"F-{i:03d}",
            "_repo": f"product-{i}",
            "description": f"Finding {i} description text",
            "type": "wrong-api",
            "severity": "M",
        }
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# embed_findings — happy path
# ---------------------------------------------------------------------------

class TestEmbedFindingsHappyPath:
    def test_returns_vectors_via_llm_router(self, tmp_path):
        findings = _sample_findings(2)
        mock_vectors = [[0.1] * 128, [0.2] * 128]

        mock_cr = CallResult(
            provider="professionalize",
            model="qwen3-embedding-8b",
            status=EndpointStatus.OK,
            data=mock_vectors,
        )

        mock_router = MagicMock()
        mock_router.call_embeddings.return_value = mock_cr

        with patch("synthesize._get_router", return_value=mock_router), \
             patch("synthesize._VECTORS_DIR", tmp_path):
            result = embed_findings(findings)

        assert len(result) == 2
        # Check router was called with the right text list
        mock_router.call_embeddings.assert_called_once()
        call_args = mock_router.call_embeddings.call_args
        texts = call_args[0][0]  # first positional arg
        assert len(texts) == 2

    def test_writes_metadata_to_file(self, tmp_path):
        findings = _sample_findings(2)
        mock_vectors = [[0.5] * 64, [0.6] * 64]

        mock_cr = CallResult(
            provider="professionalize",
            model="qwen3-embedding-8b",
            status=EndpointStatus.OK,
            data=mock_vectors,
        )

        mock_router = MagicMock()
        mock_router.call_embeddings.return_value = mock_cr

        with patch("synthesize._get_router", return_value=mock_router), \
             patch("synthesize._VECTORS_DIR", tmp_path):
            embed_findings(findings)

        out_path = tmp_path / "findings.vectors.json"
        assert out_path.exists()
        data = json.loads(out_path.read_text())
        assert data["dimensions"] == 64
        assert data["provider"] == "professionalize"
        assert data["model"] == "qwen3-embedding-8b"
        assert data["count"] == 2


# ---------------------------------------------------------------------------
# embed_findings — TF-IDF fallback
# ---------------------------------------------------------------------------

class TestEmbedFindingsFallback:
    def test_tfidf_fallback_when_router_unavailable(self):
        findings = _sample_findings(2)

        with patch("synthesize._get_router", side_effect=ImportError("no router")):
            result = embed_findings(findings)

        # Should return TF-IDF vectors (non-empty dict)
        assert len(result) == 2
        # TF-IDF vectors are lists of floats
        first_key = next(iter(result))
        assert isinstance(result[first_key], list)

    def test_tfidf_fallback_when_embeddings_fail(self):
        findings = _sample_findings(2)

        mock_cr = CallResult(
            provider="professionalize",
            status=EndpointStatus.UNREACHABLE,
            error="connection refused",
        )

        mock_router = MagicMock()
        mock_router.call_embeddings.return_value = mock_cr

        with patch("synthesize._get_router", return_value=mock_router):
            result = embed_findings(findings)

        # Should fall back to TF-IDF
        assert len(result) == 2

    def test_empty_findings_returns_empty(self):
        result = embed_findings([])
        assert result == {}


# ---------------------------------------------------------------------------
# name_cluster — happy path
# ---------------------------------------------------------------------------

class TestNameClusterHappyPath:
    def test_returns_llm_pattern(self):
        findings = _sample_findings(3)

        llm_data = {
            "pattern_name": "Missing API Members",
            "description": "Multiple products reference non-existent API members",
            "root_cause": "API surface extraction incomplete",
            "prevention": "Add member existence validation",
        }

        mock_cr = CallResult(
            provider="professionalize",
            status=EndpointStatus.OK,
            data=llm_data,
        )

        mock_router = MagicMock()
        mock_router.call_chat.return_value = mock_cr

        with patch("synthesize._get_router", return_value=mock_router):
            result = name_cluster(findings)

        assert result["pattern_name"] == "Missing API Members"
        assert "description" in result
        mock_router.call_chat.assert_called_once()


# ---------------------------------------------------------------------------
# name_cluster — fallback
# ---------------------------------------------------------------------------

class TestNameClusterFallback:
    def test_fallback_when_router_unavailable(self):
        findings = _sample_findings(3)

        with patch("synthesize._get_router", side_effect=ImportError("no router")):
            result = name_cluster(findings)

        # Fallback produces a heuristic pattern name
        assert "pattern_name" in result
        assert "description" in result
        assert "root_cause" in result

    def test_fallback_when_llm_fails(self):
        findings = _sample_findings(3)

        mock_cr = CallResult(
            provider="professionalize",
            status=EndpointStatus.UNREACHABLE,
            error="timeout",
        )

        mock_router = MagicMock()
        mock_router.call_chat.return_value = mock_cr

        with patch("synthesize._get_router", return_value=mock_router):
            result = name_cluster(findings)

        assert "pattern_name" in result
        # Heuristic: should contain the finding type
        assert "wrong" in result["pattern_name"].lower() or "Pattern" in result["pattern_name"]
