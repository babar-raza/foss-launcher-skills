"""Tests for Tier3Result dataclass and tier3_verify() in gap-eval/run.py.

Covers:
  - Happy path: tier3_verify returns Tier3Result(status=OK, verdict=<dict>)
  - --no-llm path is handled by caller (not tier3_verify itself)
  - No source context: Tier3Result(status=INTENTIONAL_SKIP, reason="no_source_context")
    → must NOT attempt Ollama (data problem, not endpoint problem)
  - LLM HTTP 401: Tier3Result with appropriate status
  - requests missing: Tier3Result(status=NOT_CONFIGURED)
  - Finding JSON schema: endpoint_status and endpoint_used fields present
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_GAP_EVAL_DIR = Path(__file__).resolve().parents[2] / "gap-eval" / "src"
_PIPELINE_DIR = Path(__file__).resolve().parents[2] / "pipeline"
if str(_GAP_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_GAP_EVAL_DIR))
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

from run import tier3_verify, Tier3Result  # type: ignore  # noqa: E402
from llm_router import EndpointStatus, CallResult  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_claim(value="SomeClass.SomeMethod"):
    return {
        "file": "content/docs/test.md",
        "line": 42,
        "type": "api-token",
        "value": value,
    }


def _mock_call_result(data: dict | None, status=EndpointStatus.OK, provider="professionalize"):
    """Build a CallResult matching _llm_call_full() output."""
    return CallResult(
        provider=provider,
        status=status,
        data=data,
    )


# ---------------------------------------------------------------------------
# Happy path: LLM finds claim inaccurate
# ---------------------------------------------------------------------------

class TestTier3HappyPath:
    def test_inaccurate_claim_returns_verdict(self, tmp_path):
        claim = _make_claim()
        clone = tmp_path / "clone"
        clone.mkdir()

        llm_data = {
            "accurate": False,
            "confidence": 0.85,
            "issue": "Method does not exist",
            "correction": "SomeClass.OtherMethod",
            "severity": "M",
            "root_cause": "phantom-api",
        }

        with patch("run._get_source_context", return_value="some source code"), \
             patch("run._llm_call_full", return_value=_mock_call_result(llm_data)):
            result = tier3_verify(claim, "cells", "net", clone)

        assert isinstance(result, Tier3Result)
        assert result.status == EndpointStatus.OK
        assert result.verdict is not None
        assert result.verdict["type"] == "phantom-api"
        assert result.verdict["severity"] == "M"
        assert result.verdict["old_value"] == "SomeClass.SomeMethod"
        assert result.verdict["correct_value"] == "SomeClass.OtherMethod"
        assert result.endpoint_used == "professionalize"

    def test_accurate_claim_returns_none_verdict(self, tmp_path):
        claim = _make_claim()
        clone = tmp_path / "clone"
        clone.mkdir()

        llm_data = {"accurate": True, "confidence": 0.95}

        with patch("run._get_source_context", return_value="some source code"), \
             patch("run._llm_call_full", return_value=_mock_call_result(llm_data)):
            result = tier3_verify(claim, "cells", "net", clone)

        assert isinstance(result, Tier3Result)
        assert result.status == EndpointStatus.OK
        assert result.verdict is None
        assert result.reason == "claim confirmed accurate"
        assert result.endpoint_used == "professionalize"


# ---------------------------------------------------------------------------
# No source context → INTENTIONAL_SKIP (NOT Ollama attempt)
# ---------------------------------------------------------------------------

class TestTier3NoSourceContext:
    def test_no_source_context_is_intentional_skip(self, tmp_path):
        claim = _make_claim()
        clone = tmp_path / "clone"
        clone.mkdir()

        with patch("run._get_source_context", return_value=""):
            result = tier3_verify(claim, "cells", "net", clone)

        assert isinstance(result, Tier3Result)
        assert result.status == EndpointStatus.INTENTIONAL_SKIP
        assert result.reason == "no_source_context"
        assert result.verdict is None

    def test_no_source_context_does_not_call_llm(self, tmp_path):
        """Ensure _llm_call_full is never invoked when source context is missing."""
        claim = _make_claim()
        clone = tmp_path / "clone"
        clone.mkdir()

        with patch("run._get_source_context", return_value=""), \
             patch("run._llm_call_full") as mock_llm:
            tier3_verify(claim, "cells", "net", clone)

        mock_llm.assert_not_called()


# ---------------------------------------------------------------------------
# requests missing → NOT_CONFIGURED
# ---------------------------------------------------------------------------

class TestTier3RequestsMissing:
    def test_no_requests_returns_not_configured(self, tmp_path):
        claim = _make_claim()
        clone = tmp_path / "clone"
        clone.mkdir()

        # Temporarily make requests import fail inside tier3_verify
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "requests":
                raise ImportError("No module named 'requests'")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            result = tier3_verify(claim, "cells", "net", clone)

        assert isinstance(result, Tier3Result)
        assert result.status == EndpointStatus.NOT_CONFIGURED
        assert "requests" in result.reason


# ---------------------------------------------------------------------------
# LLM call failed → UNREACHABLE
# ---------------------------------------------------------------------------

class TestTier3LLMFailed:
    def test_llm_returns_none(self, tmp_path):
        """_llm_call_full returns None when router is unavailable."""
        claim = _make_claim()
        clone = tmp_path / "clone"
        clone.mkdir()

        with patch("run._get_source_context", return_value="some source code"), \
             patch("run._llm_call_full", return_value=None):
            result = tier3_verify(claim, "cells", "net", clone)

        assert isinstance(result, Tier3Result)
        assert result.status == EndpointStatus.UNREACHABLE
        assert result.verdict is None

    def test_llm_returns_failed_status(self, tmp_path):
        """_llm_call_full returns a CallResult with non-OK status."""
        claim = _make_claim()
        clone = tmp_path / "clone"
        clone.mkdir()

        failed_result = CallResult(
            provider="professionalize",
            status=EndpointStatus.AUTH_FAILED,
            error="401 Unauthorized",
            fallback_artifact="/reports/fallback.json",
        )

        with patch("run._get_source_context", return_value="some source code"), \
             patch("run._llm_call_full", return_value=failed_result):
            result = tier3_verify(claim, "cells", "net", clone)

        assert result.status == EndpointStatus.AUTH_FAILED
        assert result.endpoint_used == "professionalize"
        assert result.fallback_artifact == "/reports/fallback.json"


# ---------------------------------------------------------------------------
# Tier3Result dataclass
# ---------------------------------------------------------------------------

class TestTier3ResultDataclass:
    def test_default_fields(self):
        r = Tier3Result(verdict=None, status=EndpointStatus.OK, reason="test")
        assert r.endpoint_used is None
        assert r.fallback_artifact is None

    def test_all_fields(self):
        r = Tier3Result(
            verdict={"type": "wrong-api"},
            status=EndpointStatus.OK,
            reason="found issue",
            endpoint_used="https://llm.professionalize.com/v1/chat/completions",
            fallback_artifact="/reports/test.json",
        )
        assert r.verdict["type"] == "wrong-api"
        assert r.endpoint_used is not None

    def test_status_is_endpoint_status_enum(self):
        r = Tier3Result(verdict=None, status=EndpointStatus.INTENTIONAL_SKIP, reason="test")
        assert r.status.value == "intentional_skip"
