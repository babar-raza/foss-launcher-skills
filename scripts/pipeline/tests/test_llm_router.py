"""Tests for llm_router.py — LLMRouter, EndpointStatus, CallResult.

Mock-only tests (zero network calls). Live tests skipped when no API key.
"""

import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from commands.ops.llm_router import (
    LLMRouter,
    EndpointStatus,
    CallResult,
    _load_registry,
    _sorted_providers,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def registry_path(tmp_path):
    """Write a minimal registry YAML for tests."""
    import yaml
    reg = {
        "providers": {
            "professionalize": {
                "priority": 1,
                "base_url": "https://llm.professionalize.com/v1",
                "api_key_env": "PROFESSIONALIZE_API_KEY",
                "chat": {
                    "endpoint": "/chat/completions",
                    "model": "gpt-oss",
                    "default_timeout": 90,
                    "default_temperature": 0.0,
                    "default_max_tokens": 8000,
                },
                "embeddings": {
                    "endpoint": "/embeddings",
                    "model": "qwen3-embedding-8b",
                    "default_timeout": 30,
                    "embed_dimensions": 4096,
                },
            },
            "ollama": {
                "priority": 2,
                "base_url": "http://localhost:11434/v1",
                "api_key_env": None,
                "preferred_models": ["llama3.2", "llama3.1", "mistral", "qwen2.5"],
                "chat": {
                    "endpoint": "/chat/completions",
                    "model": "llama3.2",
                    "default_timeout": 90,
                    "default_temperature": 0.0,
                    "default_max_tokens": 8000,
                },
                "embeddings": {
                    "endpoint": "/embeddings",
                    "model": "nomic-embed-text",
                    "default_timeout": 30,
                    "embed_dimensions": 768,
                },
            },
        }
    }
    p = tmp_path / "llm_registry.yaml"
    p.write_text(yaml.dump(reg), encoding="utf-8")
    return p


@pytest.fixture
def router(registry_path):
    """Router with test registry and a valid professionalize key."""
    with patch.dict(os.environ, {"PROFESSIONALIZE_API_KEY": "test-key-123"}):
        return LLMRouter(registry_path=registry_path)


@pytest.fixture
def router_no_key(registry_path):
    """Router with no professionalize key set."""
    with patch.dict(os.environ, {"PROFESSIONALIZE_API_KEY": ""}, clear=False):
        return LLMRouter(registry_path=registry_path)


def _mock_chat_response(content: str, status_code: int = 200):
    """Build a mock requests.Response for chat completions."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = content
    resp.json.return_value = {
        "choices": [{"message": {"content": content}}]
    }
    return resp


def _mock_embed_response(vectors: list[list[float]], status_code: int = 200):
    """Build a mock requests.Response for embeddings."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = json.dumps({"data": vectors})
    resp.json.return_value = {
        "data": [
            {"index": i, "embedding": v} for i, v in enumerate(vectors)
        ]
    }
    return resp


# ---------------------------------------------------------------------------
# Registry loading
# ---------------------------------------------------------------------------

class TestRegistryLoading:
    def test_load_valid(self, registry_path):
        reg = _load_registry(registry_path)
        assert "providers" in reg
        assert "professionalize" in reg["providers"]
        assert "ollama" in reg["providers"]

    def test_load_missing_file(self, tmp_path):
        with pytest.raises(RuntimeError, match="not found"):
            _load_registry(tmp_path / "nonexistent.yaml")

    def test_sorted_providers(self, registry_path):
        reg = _load_registry(registry_path)
        providers = _sorted_providers(reg)
        assert providers[0][0] == "professionalize"
        assert providers[1][0] == "ollama"


# ---------------------------------------------------------------------------
# call_chat — happy path
# ---------------------------------------------------------------------------

class TestCallChatHappy:
    def test_primary_200_returns_ok(self, router):
        mock_resp = _mock_chat_response('{"answer": "hello"}')
        with patch("commands.ops.llm_router.requests") as mock_req:
            mock_req.post.return_value = mock_resp
            mock_req.exceptions = __import__("requests").exceptions
            result = router.call_chat("system", "user")

        assert result.status == EndpointStatus.OK
        assert result.data == {"answer": "hello"}
        assert result.provider == "professionalize"
        assert result.http_status == 200
        assert result.latency_ms > 0
        assert result.fallback_artifact == ""

    def test_json_array_extraction(self, router):
        mock_resp = _mock_chat_response('[{"a": 1}, {"b": 2}]')
        with patch("commands.ops.llm_router.requests") as mock_req:
            mock_req.post.return_value = mock_resp
            mock_req.exceptions = __import__("requests").exceptions
            result = router.call_chat("system", "user", json_array=True)

        assert result.status == EndpointStatus.OK
        assert isinstance(result.data, list)
        assert len(result.data) == 2

    def test_no_json_extract(self, router):
        mock_resp = _mock_chat_response("Just plain text response")
        with patch("commands.ops.llm_router.requests") as mock_req:
            mock_req.post.return_value = mock_resp
            mock_req.exceptions = __import__("requests").exceptions
            result = router.call_chat("system", "user", json_extract=False)

        assert result.status == EndpointStatus.OK
        assert result.data == "Just plain text response"


# ---------------------------------------------------------------------------
# call_chat — missing key → Ollama attempted
# ---------------------------------------------------------------------------

class TestCallChatMissingKey:
    def test_no_key_skips_primary_tries_ollama(self, registry_path):
        mock_resp = _mock_chat_response('{"answer": "from ollama"}')
        with patch.dict(os.environ, {"PROFESSIONALIZE_API_KEY": ""}, clear=False):
            router = LLMRouter(registry_path=registry_path)
            with patch("commands.ops.llm_router.requests") as mock_req:
                mock_req.post.return_value = mock_resp
                mock_req.exceptions = __import__("requests").exceptions
                result = router.call_chat("system", "user")

        assert result.status == EndpointStatus.OK
        assert result.provider == "ollama"
        assert result.data == {"answer": "from ollama"}
        # Fallback artifact should be written
        assert result.fallback_artifact != ""


# ---------------------------------------------------------------------------
# call_chat — 401 → auth_failed, Ollama attempted
# ---------------------------------------------------------------------------

class TestCallChatAuthFailed:
    def test_401_falls_back_to_ollama(self, router):
        resp_401 = MagicMock()
        resp_401.status_code = 401
        resp_401.text = "Unauthorized"

        resp_ok = _mock_chat_response('{"answer": "fallback"}')

        with patch("commands.ops.llm_router.requests") as mock_req:
            mock_req.post.side_effect = [resp_401, resp_ok]
            mock_req.exceptions = __import__("requests").exceptions
            result = router.call_chat("system", "user")

        assert result.status == EndpointStatus.OK
        assert result.provider == "ollama"
        assert result.fallback_artifact != ""

    def test_403_is_auth_failed(self, router):
        resp_403 = MagicMock()
        resp_403.status_code = 403
        resp_403.text = "Forbidden"

        resp_ok = _mock_chat_response('{"answer": "fallback"}')

        with patch("commands.ops.llm_router.requests") as mock_req:
            mock_req.post.side_effect = [resp_403, resp_ok]
            mock_req.exceptions = __import__("requests").exceptions
            result = router.call_chat("system", "user")

        assert result.status == EndpointStatus.OK
        assert result.provider == "ollama"


# ---------------------------------------------------------------------------
# call_chat — connection refused → unreachable, Ollama attempted
# ---------------------------------------------------------------------------

class TestCallChatUnreachable:
    def test_connection_refused_falls_back(self, router):
        import requests as real_requests

        resp_ok = _mock_chat_response('{"answer": "fallback"}')

        with patch("commands.ops.llm_router.requests") as mock_req:
            mock_req.post.side_effect = [
                real_requests.exceptions.ConnectionError("Connection refused"),
                resp_ok,
            ]
            mock_req.exceptions = real_requests.exceptions
            result = router.call_chat("system", "user")

        assert result.status == EndpointStatus.OK
        assert result.provider == "ollama"
        assert result.fallback_artifact != ""

    def test_timeout_falls_back(self, router):
        import requests as real_requests

        resp_ok = _mock_chat_response('{"answer": "fallback"}')

        with patch("commands.ops.llm_router.requests") as mock_req:
            mock_req.post.side_effect = [
                real_requests.exceptions.Timeout("Read timed out"),
                resp_ok,
            ]
            mock_req.exceptions = real_requests.exceptions
            result = router.call_chat("system", "user")

        assert result.status == EndpointStatus.OK
        assert result.provider == "ollama"


# ---------------------------------------------------------------------------
# call_chat — both fail → CallResult with error
# ---------------------------------------------------------------------------

class TestCallChatBothFail:
    def test_both_unreachable(self, router):
        import requests as real_requests

        with patch("commands.ops.llm_router.requests") as mock_req:
            mock_req.post.side_effect = real_requests.exceptions.ConnectionError(
                "Connection refused"
            )
            mock_req.exceptions = real_requests.exceptions
            result = router.call_chat("system", "user")

        assert result.status == EndpointStatus.UNREACHABLE
        assert result.data is None
        assert result.provider == "professionalize"

    def test_no_requests_library(self, router):
        with patch("commands.ops.llm_router.requests", None):
            result = router.call_chat("system", "user")

        assert result.status == EndpointStatus.NOT_CONFIGURED
        assert "requests" in result.error


# ---------------------------------------------------------------------------
# call_embeddings — happy path with dimension validation
# ---------------------------------------------------------------------------

class TestCallEmbeddingsHappy:
    def test_4096_dim_ok(self, router):
        vectors = [[0.1] * 4096, [0.2] * 4096]
        mock_resp = _mock_embed_response(vectors)
        with patch("commands.ops.llm_router.requests") as mock_req:
            mock_req.post.return_value = mock_resp
            mock_req.exceptions = __import__("requests").exceptions
            result = router.call_embeddings(["text1", "text2"])

        assert result.status == EndpointStatus.OK
        assert len(result.data) == 2
        assert len(result.data[0]) == 4096
        assert result.provider == "professionalize"


# ---------------------------------------------------------------------------
# call_embeddings — dimension mismatch → PARSE_FAILED
# ---------------------------------------------------------------------------

class TestCallEmbeddingsDimensionMismatch:
    def test_wrong_dims_rejected(self, router):
        # professionalize expects 4096, return 512 → mismatch
        vectors_bad = [[0.1] * 512, [0.2] * 512]
        mock_resp_bad = _mock_embed_response(vectors_bad)
        # Ollama expects 768, return 768 → ok
        vectors_ok = [[0.3] * 768, [0.4] * 768]
        mock_resp_ok = _mock_embed_response(vectors_ok)

        with patch("commands.ops.llm_router.requests") as mock_req:
            mock_req.post.side_effect = [mock_resp_bad, mock_resp_ok]
            mock_req.exceptions = __import__("requests").exceptions
            result = router.call_embeddings(["text1", "text2"])

        assert result.status == EndpointStatus.OK
        assert result.provider == "ollama"
        assert len(result.data[0]) == 768


# ---------------------------------------------------------------------------
# Primary always before secondary
# ---------------------------------------------------------------------------

class TestProviderOrder:
    def test_professionalize_probed_first(self, router):
        call_urls = []

        def track_calls(*args, **kwargs):
            url = args[0] if args else kwargs.get("url", "")
            call_urls.append(url)
            resp = _mock_chat_response('{"ok": true}')
            return resp

        with patch("commands.ops.llm_router.requests") as mock_req:
            mock_req.post.side_effect = track_calls
            mock_req.exceptions = __import__("requests").exceptions
            router.call_chat("system", "user")

        assert len(call_urls) >= 1
        assert "professionalize" in call_urls[0]


# ---------------------------------------------------------------------------
# Probe
# ---------------------------------------------------------------------------

class TestProbe:
    def test_probe_ok(self, router):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("commands.ops.llm_router.requests") as mock_req:
            mock_req.post.return_value = mock_resp
            mock_req.exceptions = __import__("requests").exceptions
            results = router.probe()

        assert results["professionalize"]["status"] == "ok"
        assert results["ollama"]["status"] == "ok"

    def test_probe_filter(self, router):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("commands.ops.llm_router.requests") as mock_req:
            mock_req.post.return_value = mock_resp
            mock_req.exceptions = __import__("requests").exceptions
            results = router.probe(provider_filter="professionalize")

        assert "professionalize" in results
        assert "ollama" not in results

    def test_probe_no_key(self, registry_path):
        with patch.dict(os.environ, {"PROFESSIONALIZE_API_KEY": ""}, clear=False):
            router = LLMRouter(registry_path=registry_path)
            results = router.probe()
        assert results["professionalize"]["status"] == "not_configured"


# ---------------------------------------------------------------------------
# CallResult defaults
# ---------------------------------------------------------------------------

class TestCallResultDefaults:
    def test_default_values(self):
        r = CallResult()
        assert r.provider == ""
        assert r.status == EndpointStatus.UNKNOWN
        assert r.data is None
        assert r.latency_ms == 0.0
        assert r.http_status == 0
        assert r.error == ""
        assert r.fallback_artifact == ""


# ---------------------------------------------------------------------------
# EndpointStatus enum
# ---------------------------------------------------------------------------

class TestEndpointStatus:
    def test_string_values(self):
        assert EndpointStatus.OK == "ok"
        assert EndpointStatus.UNREACHABLE == "unreachable"
        assert EndpointStatus.AUTH_FAILED == "auth_failed"
        assert EndpointStatus.NOT_CONFIGURED == "not_configured"
        assert EndpointStatus.INTENTIONAL_SKIP == "intentional_skip"
        assert EndpointStatus.PARSE_FAILED == "parse_failed"

    def test_json_serializable(self):
        # EndpointStatus is str enum — serializes directly
        data = {"status": EndpointStatus.OK}
        assert json.dumps(data) == '{"status": "ok"}'



# ---------------------------------------------------------------------------
# Ollama discovery (TC-01)
# ---------------------------------------------------------------------------

class TestOllamaDiscovery:
    def test_discovery_returns_preferred_order(self, router_no_key):
        """Mock /api/tags -> verify preferred order with exact names."""
        tags_resp = MagicMock()
        tags_resp.status_code = 200
        tags_resp.json.return_value = {
            "models": [
                {"name": "mistral:7b", "size": 4000000000},
                {"name": "llama3.2:latest", "size": 2000000000},
                {"name": "llama3.1:latest", "size": 3000000000},
            ]
        }
        with patch("commands.ops.llm_router.requests") as mock_req:
            mock_req.get.return_value = tags_resp
            mock_req.exceptions = __import__("requests").exceptions
            models = router_no_key.discover_ollama_models()

        assert models[0] == "llama3.2:latest"
        assert models[1] == "llama3.1:latest"
        assert models[2] == "mistral:7b"

    def test_discovery_base_name_match(self, router_no_key):
        tags_resp = MagicMock()
        tags_resp.status_code = 200
        tags_resp.json.return_value = {
            "models": [{"name": "llama3.1:latest", "size": 3000000000}]
        }
        with patch("commands.ops.llm_router.requests") as mock_req:
            mock_req.get.return_value = tags_resp
            mock_req.exceptions = __import__("requests").exceptions
            models = router_no_key.discover_ollama_models()
        assert "llama3.1:latest" in models

    def test_discovery_preserves_exact_tags(self, router_no_key):
        tags_resp = MagicMock()
        tags_resp.status_code = 200
        tags_resp.json.return_value = {
            "models": [{"name": "qwen2.5:14b", "size": 8000000000}]
        }
        with patch("commands.ops.llm_router.requests") as mock_req:
            mock_req.get.return_value = tags_resp
            mock_req.exceptions = __import__("requests").exceptions
            models = router_no_key.discover_ollama_models()
        assert models[0] == "qwen2.5:14b"

    def test_discovery_timeout_returns_empty(self, router_no_key):
        import requests as real_requests
        with patch("commands.ops.llm_router.requests") as mock_req:
            mock_req.get.side_effect = real_requests.exceptions.Timeout("timeout")
            mock_req.exceptions = real_requests.exceptions
            models = router_no_key.discover_ollama_models()
        assert models == []

    def test_discovery_cached(self, router_no_key):
        tags_resp = MagicMock()
        tags_resp.status_code = 200
        tags_resp.json.return_value = {"models": [{"name": "llama3.2:latest", "size": 1}]}
        with patch("commands.ops.llm_router.requests") as mock_req:
            mock_req.get.return_value = tags_resp
            mock_req.exceptions = __import__("requests").exceptions
            m1 = router_no_key.discover_ollama_models()
            m2 = router_no_key.discover_ollama_models()
            assert mock_req.get.call_count == 1
        assert m1 == m2

    def test_no_discovery_when_model_works(self, router):
        mock_resp = _mock_chat_response('{"ok": true}')
        with patch("commands.ops.llm_router.requests") as mock_req:
            mock_req.post.return_value = mock_resp
            mock_req.exceptions = __import__("requests").exceptions
            router.call_chat("system", "user")
            mock_req.get.assert_not_called()

    def test_404_fallback_uses_discovered_model(self, registry_path):
        resp_404 = MagicMock()
        resp_404.status_code = 404
        resp_404.text = "model not found"
        resp_ok = _mock_chat_response('{"answer": "from discovered"}')
        tags_resp = MagicMock()
        tags_resp.status_code = 200
        tags_resp.json.return_value = {
            "models": [{"name": "llama3.1:latest", "size": 3000000000}]
        }
        with patch.dict(os.environ, {"PROFESSIONALIZE_API_KEY": ""}, clear=False):
            router = LLMRouter(registry_path=registry_path)
            with patch("commands.ops.llm_router.requests") as mock_req:
                mock_req.post.side_effect = [resp_404, resp_ok]
                mock_req.get.return_value = tags_resp
                mock_req.exceptions = __import__("requests").exceptions
                result = router.call_chat("system", "user")
        assert result.status == EndpointStatus.OK
        assert result.provider == "ollama"
        assert result.model == "llama3.1:latest"

# ---------------------------------------------------------------------------
# Live tests (skipped without API key)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not os.environ.get("PROFESSIONALIZE_API_KEY"),
    reason="PROFESSIONALIZE_API_KEY not set — skipping live tests",
)
class TestLive:
    def test_live_chat(self):
        router = LLMRouter()
        result = router.call_chat(
            "Reply with the single word OK.",
            "Confirm you are working.",
            max_tokens=50,
            timeout=30,
            json_extract=False,
        )
        assert result.status == EndpointStatus.OK
        assert result.provider == "professionalize"

    def test_live_probe(self):
        router = LLMRouter()
        results = router.probe(provider_filter="professionalize")
        assert results["professionalize"]["status"] == "ok"
