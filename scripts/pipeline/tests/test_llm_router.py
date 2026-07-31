"""Tests for llm_router.py — LLMRouter, EndpointStatus, CallResult.

Mock-only tests (zero network calls). Live tests skipped when no API key.

Slice 3 additions: metrics emission tests for CS-001 (chat) and CS-002
(embeddings) via injected FakeHTTPClient.
"""

import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
import requests as real_requests

from commands.ops.llm_router import (
    LLMRouter,
    EndpointStatus,
    CallResult,
    _load_registry,
    _sorted_providers,
    _map_prof_status,
    _PROF_CLIENT_AVAILABLE,
)


# ---------------------------------------------------------------------------
# Fake HTTP transport (Slice 3 — injected into ProfessionalizeClient)
# ---------------------------------------------------------------------------

class _FakeHTTPClient:
    """Minimal fake transport for ProfessionalizeClient in router tests."""

    def __init__(self, side_effects):
        """side_effects: list of response objects or exceptions to return/raise."""
        self._effects = list(side_effects)
        self.calls = []

    def post(self, url, *, json, headers, timeout):
        self.calls.append({"url": url, "json": json})
        if not self._effects:
            raise ConnectionError("No more configured responses")
        effect = self._effects.pop(0)
        if isinstance(effect, BaseException):
            raise effect
        return effect

    @property
    def call_count(self):
        return len(self.calls)


class _FakeHTTPResponse:
    """Minimal fake HTTP response for router tests."""

    def __init__(self, body: dict, status_code: int = 200):
        self.status_code = status_code
        self._body = body
        self.text = json.dumps(body)
        self.content = json.dumps(body).encode("utf-8")

    def json(self):
        return self._body


def _prof_chat_resp(content: str, prompt_tokens=10, completion_tokens=5, status_code=200):
    """Build a _FakeHTTPResponse for a chat/completions call."""
    body = {
        "choices": [{"message": {"content": content}}],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }
    return _FakeHTTPResponse(body, status_code)


def _prof_embed_resp(vectors: list, prompt_tokens=4, status_code=200):
    """Build a _FakeHTTPResponse for an embeddings call."""
    body = {
        "data": [{"index": i, "embedding": v} for i, v in enumerate(vectors)],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": 0,
            "total_tokens": prompt_tokens,
        },
    }
    return _FakeHTTPResponse(body, status_code)


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
def router_no_key(registry_path):
    """Router with no professionalize key set (ollama-only path).

    Uses the _credential_env injection seam (not os.environ patching) so the
    "no key" state is deterministic regardless of the ambient shell — see
    LLMRouter._env_get. Pinning PROFESSIONALIZE_API_KEY to "" in the override
    guarantees it resolves empty even if the real env var happens to be set.
    """
    return LLMRouter(registry_path=registry_path, _credential_env={"PROFESSIONALIZE_API_KEY": ""})


def _make_router(registry_path, http_responses=None, api_key="test-key-123"):
    """Build a router with optional injected FakeHTTPClient.

    Credentials are injected via LLMRouter's _credential_env seam, not
    os.environ patching: LLMRouter reads credentials lazily inside
    call_chat()/call_embeddings()/probe(), not at construction time, so a
    `with patch.dict(...)` scoped to construction would revert before the
    caller ever invokes those methods. The injection seam sidesteps that
    entirely and needs no teardown.
    """
    http = _FakeHTTPClient(http_responses) if http_responses is not None else None
    return LLMRouter(
        registry_path=registry_path,
        _http_client=http,
        _credential_env={"PROFESSIONALIZE_API_KEY": api_key},
    )


@pytest.fixture
def router(registry_path):
    """Router with valid professionalize key and no injected http client.

    For Slice 3: most professionalize-path tests should use _make_router()
    with injected fake responses instead of this fixture.
    """
    return LLMRouter(
        registry_path=registry_path,
        _credential_env={"PROFESSIONALIZE_API_KEY": "test-key-123"},
    )


def _mock_chat_response(content: str, status_code: int = 200):
    """Build a mock requests.Response for chat completions (ollama path)."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = content
    _body = {"choices": [{"message": {"content": content}}]}
    resp.json.return_value = _body
    resp.content = json.dumps(_body).encode("utf-8")
    return resp


def _mock_embed_response(vectors: list[list[float]], status_code: int = 200):
    """Build a mock requests.Response for embeddings (ollama path)."""
    resp = MagicMock()
    resp.status_code = status_code
    _body = {
        "data": [
            {"index": i, "embedding": v} for i, v in enumerate(vectors)
        ]
    }
    resp.text = json.dumps({"data": vectors})
    resp.json.return_value = _body
    resp.content = json.dumps(_body).encode("utf-8")
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


class TestRegistryHotReload:
    def test_same_instance_observes_dimension_update(self, registry_path):
        import yaml

        vectors_4096 = [[0.1] * 4096]
        vectors_512 = [[0.2] * 512]
        router = _make_router(
            registry_path,
            [_prof_embed_resp(vectors_4096), _prof_embed_resp(vectors_512)],
        )
        with patch.dict(os.environ, {"PROFESSIONALIZE_API_KEY": "test-key"}):
            first = router.call_embeddings(["one"], operation="index_build")
            registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
            registry["providers"]["professionalize"]["embeddings"]["embed_dimensions"] = 512
            registry_path.write_text(yaml.safe_dump(registry), encoding="utf-8")
            second = router.call_embeddings(["two"], operation="index_build")

        assert first.status == EndpointStatus.OK
        assert first.embedding_profile.dimensions == 4096
        assert second.status == EndpointStatus.OK
        assert second.embedding_profile.dimensions == 512
        assert first.config_digest != second.config_digest

    def test_invalid_changed_registry_fails_closed(self, registry_path):
        router = _make_router(registry_path, [_prof_chat_resp('{"ok": true}')])
        registry_path.write_text("schema_version: 2\nproviders: []\n", encoding="utf-8")
        result = router.call_chat("system", "user")
        assert result.status == EndpointStatus.CONFIG_INVALID
        assert router._http_client.call_count == 0

    def test_invalid_retry_policy_fails_validation(self, registry_path):
        import yaml

        registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
        registry["providers"]["professionalize"]["retry"] = {
            "max_attempts": 0,
            "retry_statuses": [503],
        }
        registry_path.write_text(yaml.safe_dump(registry), encoding="utf-8")
        with pytest.raises(RuntimeError, match="retry.max_attempts"):
            LLMRouter(registry_path=registry_path)


class TestCredentialRotation:
    def test_401_rotates_to_next_alias_without_exposing_secret(self, registry_path):
        import yaml

        registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
        provider = registry["providers"]["professionalize"]
        provider["credential_aliases"] = ["FIRST_TEST_KEY", "SECOND_TEST_KEY"]
        registry_path.write_text(yaml.safe_dump(registry), encoding="utf-8")
        router = _make_router(
            registry_path,
            [
                _prof_chat_resp('{"error": "unauthorized"}', status_code=401),
                _prof_chat_resp('{"ok": true}'),
            ],
        )
        with patch.dict(
            os.environ,
            {"FIRST_TEST_KEY": "secret-first", "SECOND_TEST_KEY": "secret-second"},
        ):
            result = router.call_chat("system", "user")

        assert result.status == EndpointStatus.OK
        assert result.api_calls_count == 2
        assert [attempt.credential_env_name for attempt in result.attempts] == [
            "FIRST_TEST_KEY", "SECOND_TEST_KEY",
        ]
        assert "secret-first" not in repr(result)
        assert "secret-second" not in repr(result)

    def test_registry_retry_policy_reaches_transport(self, registry_path):
        import yaml

        registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
        registry["providers"]["professionalize"]["retry"] = {
            "max_attempts": 2,
            "retry_statuses": [503],
        }
        registry_path.write_text(yaml.safe_dump(registry), encoding="utf-8")
        router = _make_router(
            registry_path,
            [
                _prof_chat_resp('{"error": "temporary"}', status_code=503),
                _prof_chat_resp('{"ok": true}'),
            ],
        )
        result = router.call_chat("system", "user")
        assert result.status == EndpointStatus.OK
        assert result.api_calls_count == 2
        assert [attempt.status for attempt in result.attempts] == [
            EndpointStatus.UNKNOWN,
            EndpointStatus.OK,
        ]


# ---------------------------------------------------------------------------
# call_chat — happy path
# ---------------------------------------------------------------------------

class TestCallChatHappy:
    def test_primary_200_returns_ok(self, registry_path):
        router = _make_router(registry_path, [_prof_chat_resp('{"answer": "hello"}')])
        result = router.call_chat("system", "user")

        assert result.status == EndpointStatus.OK
        assert result.data == {"answer": "hello"}
        assert result.provider == "professionalize"
        assert result.http_status == 200
        assert result.latency_ms >= 0
        assert result.fallback_artifact == ""

    def test_json_array_extraction(self, registry_path):
        router = _make_router(registry_path, [_prof_chat_resp('[{"a": 1}, {"b": 2}]')])
        result = router.call_chat("system", "user", json_array=True)

        assert result.status == EndpointStatus.OK
        assert isinstance(result.data, list)
        assert len(result.data) == 2

    def test_no_json_extract(self, registry_path):
        router = _make_router(registry_path, [_prof_chat_resp("Just plain text response")])
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
                mock_req.exceptions = real_requests.exceptions
                result = router.call_chat("system", "user")

        assert result.status == EndpointStatus.OK
        assert result.provider == "ollama"
        assert result.data == {"answer": "from ollama"}
        # Routing is recorded in the metrics ledger; anonymous artifacts are retired.
        assert result.fallback_artifact == ""


# ---------------------------------------------------------------------------
# call_chat — 401 → auth_failed, Ollama attempted
# ---------------------------------------------------------------------------

class TestCallChatAuthFailed:
    def test_401_falls_back_to_ollama(self, registry_path):
        # Professionalize returns 401 via FakeHTTPClient
        prof_resp = _FakeHTTPResponse({"error": "unauthorized"}, 401)
        router = _make_router(registry_path, [prof_resp])
        # Ollama succeeds via requests mock
        ollama_resp = _mock_chat_response('{"answer": "fallback"}')
        with patch("commands.ops.llm_router.requests") as mock_req:
            mock_req.post.return_value = ollama_resp
            mock_req.exceptions = real_requests.exceptions
            result = router.call_chat("system", "user")

        assert result.status == EndpointStatus.OK
        assert result.provider == "ollama"
        assert result.fallback_artifact == ""
        # Proves professionalize's 401 was actually hit (not skipped as
        # not_configured) — this is the scenario the test name claims.
        assert router._http_client.call_count == 1

    def test_403_is_auth_failed_then_ollama(self, registry_path):
        prof_resp = _FakeHTTPResponse({"error": "forbidden"}, 403)
        router = _make_router(registry_path, [prof_resp])
        ollama_resp = _mock_chat_response('{"answer": "fallback"}')
        with patch("commands.ops.llm_router.requests") as mock_req:
            mock_req.post.return_value = ollama_resp
            mock_req.exceptions = real_requests.exceptions
            result = router.call_chat("system", "user")

        assert result.status == EndpointStatus.OK
        assert result.provider == "ollama"
        assert router._http_client.call_count == 1


# ---------------------------------------------------------------------------
# call_chat — connection refused → unreachable, Ollama attempted
# ---------------------------------------------------------------------------

class TestCallChatUnreachable:
    def test_connection_refused_falls_back(self, registry_path):
        router = _make_router(
            registry_path,
            [real_requests.exceptions.ConnectionError("Connection refused")]
        )
        ollama_resp = _mock_chat_response('{"answer": "fallback"}')
        with patch("commands.ops.llm_router.requests") as mock_req:
            mock_req.post.return_value = ollama_resp
            mock_req.exceptions = real_requests.exceptions
            result = router.call_chat("system", "user")

        assert result.status == EndpointStatus.OK
        assert result.provider == "ollama"
        assert result.fallback_artifact == ""
        # Proves professionalize's connection error was actually hit (not
        # skipped as not_configured) — the scenario the test name claims.
        assert router._http_client.call_count == 1

    def test_timeout_falls_back(self, registry_path):
        router = _make_router(
            registry_path,
            [real_requests.exceptions.Timeout("Read timed out")]
        )
        ollama_resp = _mock_chat_response('{"answer": "fallback"}')
        with patch("commands.ops.llm_router.requests") as mock_req:
            mock_req.post.return_value = ollama_resp
            mock_req.exceptions = real_requests.exceptions
            result = router.call_chat("system", "user")

        assert result.status == EndpointStatus.OK
        assert result.provider == "ollama"
        assert router._http_client.call_count == 1


# ---------------------------------------------------------------------------
# call_chat — both fail → CallResult with error
# ---------------------------------------------------------------------------

class TestCallChatBothFail:
    def test_both_unreachable(self, registry_path):
        router = _make_router(
            registry_path,
            [real_requests.exceptions.ConnectionError("Connection refused")]
        )
        with patch("commands.ops.llm_router.requests") as mock_req:
            mock_req.post.side_effect = real_requests.exceptions.ConnectionError(
                "Connection refused"
            )
            mock_req.exceptions = real_requests.exceptions
            result = router.call_chat("system", "user")

        assert result.status == EndpointStatus.UNREACHABLE
        assert result.data is None
        assert result.provider == "professionalize"

    def test_no_requests_library_prof_still_works(self, registry_path):
        """With ProfessionalizeClient available, missing requests doesn't break prof."""
        router = _make_router(registry_path, [_prof_chat_resp('{"ok": true}')])
        with patch("commands.ops.llm_router.requests", None):
            result = router.call_chat("system", "user")

        assert result.status == EndpointStatus.OK
        assert result.provider == "professionalize"


# ---------------------------------------------------------------------------
# call_embeddings — happy path with dimension validation
# ---------------------------------------------------------------------------

class TestCallEmbeddingsHappy:
    def test_4096_dim_ok(self, registry_path):
        vectors = [[0.1] * 4096, [0.2] * 4096]
        router = _make_router(registry_path, [_prof_embed_resp(vectors)])
        result = router.call_embeddings(["text1", "text2"])

        assert result.status == EndpointStatus.OK
        assert len(result.data) == 2
        assert len(result.data[0]) == 4096
        assert result.provider == "professionalize"
        assert router._http_client.calls[0]["json"]["dimensions"] == 4096


# ---------------------------------------------------------------------------
# call_embeddings — dimension mismatch → CONTRACT_MISMATCH
# ---------------------------------------------------------------------------

class TestCallEmbeddingsDimensionMismatch:
    def test_wrong_dims_rejected(self, registry_path):
        # professionalize expects 4096, return 512 → mismatch
        vectors_bad = [[0.1] * 512, [0.2] * 512]
        router = _make_router(registry_path, [_prof_embed_resp(vectors_bad)])
        # Ollama expects 768, return 768 → ok
        vectors_ok = [[0.3] * 768, [0.4] * 768]
        mock_resp_ok = _mock_embed_response(vectors_ok)

        with patch("commands.ops.llm_router.requests") as mock_req:
            mock_req.post.return_value = mock_resp_ok
            mock_req.exceptions = real_requests.exceptions
            result = router.call_embeddings(["text1", "text2"])

        assert result.status == EndpointStatus.OK
        assert result.provider == "ollama"
        assert len(result.data[0]) == 768
        assert [attempt.status for attempt in result.attempts] == [
            EndpointStatus.CONTRACT_MISMATCH,
            EndpointStatus.OK,
        ]
        assert result.attempts[0].observed_dimensions == 512
        assert result.embedding_profile.provider == "ollama"


class TestOllamaEmbeddingResultContract:
    @staticmethod
    def _ollama_only_registry(registry_path):
        import yaml

        registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
        registry["providers"].pop("professionalize")
        registry_path.write_text(yaml.safe_dump(registry), encoding="utf-8")
        return LLMRouter(registry_path=registry_path)

    def test_malformed_payload_is_parse_failed(self, registry_path):
        router = self._ollama_only_registry(registry_path)
        malformed = _FakeHTTPResponse({"data": [{}]})
        with patch("commands.ops.llm_router.requests") as mock_req:
            mock_req.post.return_value = malformed
            mock_req.exceptions = real_requests.exceptions
            result = router.call_embeddings(["text"])
        assert result.status == EndpointStatus.PARSE_FAILED
        assert result.attempts[-1].status == EndpointStatus.PARSE_FAILED
        assert result.config_digest
        assert result.embedding_profile.provider == "ollama"

    def test_dimension_drift_is_contract_mismatch(self, registry_path):
        router = self._ollama_only_registry(registry_path)
        wrong_dims = _mock_embed_response([[0.1] * 512])
        with patch("commands.ops.llm_router.requests") as mock_req:
            mock_req.post.return_value = wrong_dims
            mock_req.exceptions = real_requests.exceptions
            result = router.call_embeddings(["text"])
        assert result.status == EndpointStatus.CONTRACT_MISMATCH
        assert result.attempts[-1].status == EndpointStatus.CONTRACT_MISMATCH
        assert result.attempts[-1].observed_dimensions == 512
        assert result.embedding_profile.dimensions == 768


# ---------------------------------------------------------------------------
# Primary always before secondary
# ---------------------------------------------------------------------------

class TestProviderOrder:
    def test_professionalize_called_first(self, registry_path):
        """Professionalize is priority 1 — its FakeHTTPClient must be called first."""
        fake_http = _FakeHTTPClient([_prof_chat_resp('{"ok": true}')])
        router = _make_router(registry_path, [_prof_chat_resp('{"ok": true}')])
        # Extract the injected client to verify it was used
        result = router.call_chat("system", "user")
        assert result.status == EndpointStatus.OK
        assert result.provider == "professionalize"


# ---------------------------------------------------------------------------
# Probe
# ---------------------------------------------------------------------------

class TestProbe:
    def test_probe_ok(self, router):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("commands.ops.llm_router.requests") as mock_req:
            mock_req.post.return_value = mock_resp
            mock_req.exceptions = real_requests.exceptions
            results = router.probe()

        assert results["professionalize"]["status"] == "ok"
        assert results["ollama"]["status"] == "ok"

    def test_probe_filter(self, router):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("commands.ops.llm_router.requests") as mock_req:
            mock_req.post.return_value = mock_resp
            mock_req.exceptions = real_requests.exceptions
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
        assert r.token_usage == 0
        assert r.api_calls_count == 0
        assert r.metrics_events == []


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
        _tags_body = {
            "models": [
                {"name": "mistral:7b", "size": 4000000000},
                {"name": "llama3.2:latest", "size": 2000000000},
                {"name": "llama3.1:latest", "size": 3000000000},
            ]
        }
        tags_resp.json.return_value = _tags_body
        tags_resp.content = json.dumps(_tags_body).encode("utf-8")
        with patch("commands.ops.llm_router.requests") as mock_req:
            mock_req.get.return_value = tags_resp
            mock_req.exceptions = real_requests.exceptions
            models = router_no_key.discover_ollama_models()

        assert models[0] == "llama3.2:latest"
        assert models[1] == "llama3.1:latest"
        assert models[2] == "mistral:7b"

    def test_discovery_base_name_match(self, router_no_key):
        tags_resp = MagicMock()
        tags_resp.status_code = 200
        _tags_body = {"models": [{"name": "llama3.1:latest", "size": 3000000000}]}
        tags_resp.json.return_value = _tags_body
        tags_resp.content = json.dumps(_tags_body).encode("utf-8")
        with patch("commands.ops.llm_router.requests") as mock_req:
            mock_req.get.return_value = tags_resp
            mock_req.exceptions = real_requests.exceptions
            models = router_no_key.discover_ollama_models()
        assert "llama3.1:latest" in models

    def test_discovery_preserves_exact_tags(self, router_no_key):
        tags_resp = MagicMock()
        tags_resp.status_code = 200
        _tags_body = {"models": [{"name": "qwen2.5:14b", "size": 8000000000}]}
        tags_resp.json.return_value = _tags_body
        tags_resp.content = json.dumps(_tags_body).encode("utf-8")
        with patch("commands.ops.llm_router.requests") as mock_req:
            mock_req.get.return_value = tags_resp
            mock_req.exceptions = real_requests.exceptions
            models = router_no_key.discover_ollama_models()
        assert models[0] == "qwen2.5:14b"

    def test_discovery_timeout_returns_empty(self, router_no_key):
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
            mock_req.exceptions = real_requests.exceptions
            m1 = router_no_key.discover_ollama_models()
            m2 = router_no_key.discover_ollama_models()
            assert mock_req.get.call_count == 1
        assert m1 == m2

    def test_no_discovery_when_model_works(self, registry_path):
        router = _make_router(registry_path, [_prof_chat_resp('{"ok": true}')])
        result = router.call_chat("system", "user")
        assert result.status == EndpointStatus.OK
        # No ollama discovery was triggered (professionalize succeeded)
        assert result.provider == "professionalize"

    def test_404_fallback_uses_discovered_model(self, registry_path):
        resp_404 = MagicMock()
        resp_404.status_code = 404
        resp_404.text = "model not found"
        resp_ok = _mock_chat_response('{"answer": "from discovered"}')
        tags_resp = MagicMock()
        tags_resp.status_code = 200
        _tags_body = {"models": [{"name": "llama3.1:latest", "size": 3000000000}]}
        tags_resp.json.return_value = _tags_body
        tags_resp.content = json.dumps(_tags_body).encode("utf-8")
        with patch.dict(os.environ, {"PROFESSIONALIZE_API_KEY": ""}, clear=False):
            router = LLMRouter(registry_path=registry_path)
            with patch("commands.ops.llm_router.requests") as mock_req:
                mock_req.post.side_effect = [resp_404, resp_ok]
                mock_req.get.return_value = tags_resp
                mock_req.exceptions = real_requests.exceptions
                result = router.call_chat("system", "user")
        assert result.status == EndpointStatus.OK
        assert result.provider == "ollama"
        assert result.model == "llama3.1:latest"


# ---------------------------------------------------------------------------
# Slice 3: Metrics emission — chat (CS-001)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _PROF_CLIENT_AVAILABLE, reason="ProfessionalizeClient not available")
class TestSlice3MetricsChat:
    """25 required Slice 3 test scenarios (TC-S3-01 through TC-S3-25).

    Tests 1-13 cover chat CS-001 metrics emission.
    Tests 14-18 cover embeddings CS-002 metrics emission.
    Tests 19-22 cover ollama isolation (no professionalize metrics).
    Tests 23-25 cover all-providers-fail and CallResult field checks.
    """

    # TC-S3-01
    def test_chat_emits_metrics_event(self, registry_path):
        router = _make_router(registry_path, [_prof_chat_resp('{"answer": "hi"}')])
        result = router.call_chat("system", "user")
        assert result.status == EndpointStatus.OK
        assert len(result.metrics_events) == 1

    # TC-S3-02
    def test_chat_event_call_site_id_is_cs001(self, registry_path):
        router = _make_router(registry_path, [_prof_chat_resp('{"answer": "hi"}')])
        result = router.call_chat("system", "user")
        assert result.metrics_events[0].call_site_id == "CS-001"

    # TC-S3-03
    def test_chat_event_status_success_on_ok(self, registry_path):
        router = _make_router(registry_path, [_prof_chat_resp('{"answer": "hi"}')])
        result = router.call_chat("system", "user")
        assert result.metrics_events[0].status == "success"

    # TC-S3-04
    def test_chat_event_endpoint_contains_completions(self, registry_path):
        router = _make_router(registry_path, [_prof_chat_resp('{"answer": "hi"}')])
        result = router.call_chat("system", "user")
        assert "chat/completions" in result.metrics_events[0].endpoint

    # TC-S3-05
    def test_chat_token_usage_populated(self, registry_path):
        router = _make_router(
            registry_path,
            [_prof_chat_resp('{"answer": "hi"}', prompt_tokens=10, completion_tokens=5)]
        )
        result = router.call_chat("system", "user")
        assert result.token_usage == 15

    # TC-S3-06
    def test_chat_api_calls_count_is_1(self, registry_path):
        router = _make_router(registry_path, [_prof_chat_resp('{"answer": "hi"}')])
        result = router.call_chat("system", "user")
        assert result.api_calls_count == 1

    # TC-S3-07
    def test_chat_metrics_events_list_has_one_event(self, registry_path):
        router = _make_router(registry_path, [_prof_chat_resp('{"answer": "hi"}')])
        result = router.call_chat("system", "user")
        assert len(result.metrics_events) == 1
        from commands.ops.metrics_schema import MetricsEvent
        assert isinstance(result.metrics_events[0], MetricsEvent)

    # TC-S3-08
    def test_chat_failure_500_event_status_failure(self, registry_path):
        """HTTP 500 → event.status == 'failure', result.status == UNKNOWN."""
        router = _make_router(
            registry_path,
            [_FakeHTTPResponse({"error": "server error"}, 500)]
        )
        with patch("commands.ops.llm_router.requests") as mock_req:
            # Ollama also fails so first_result is returned with prof events
            mock_req.post.side_effect = real_requests.exceptions.ConnectionError("off")
            mock_req.exceptions = real_requests.exceptions
            result = router.call_chat("system", "user")
        assert result.status in (EndpointStatus.UNKNOWN, EndpointStatus.UNREACHABLE)
        assert len(result.metrics_events) == 1
        assert result.metrics_events[0].status == "failure"

    # TC-S3-09
    def test_chat_failure_401_maps_to_auth_failed(self, registry_path):
        router = _make_router(
            registry_path,
            [_FakeHTTPResponse({"error": "unauthorized"}, 401)]
        )
        with patch("commands.ops.llm_router.requests") as mock_req:
            mock_req.post.side_effect = real_requests.exceptions.ConnectionError("off")
            mock_req.exceptions = real_requests.exceptions
            result = router.call_chat("system", "user")
        assert result.status == EndpointStatus.AUTH_FAILED

    # TC-S3-10
    def test_chat_failure_timeout_maps_to_unreachable(self, registry_path):
        router = _make_router(
            registry_path,
            [real_requests.exceptions.Timeout("timed out")]
        )
        with patch("commands.ops.llm_router.requests") as mock_req:
            mock_req.post.side_effect = real_requests.exceptions.ConnectionError("off")
            mock_req.exceptions = real_requests.exceptions
            result = router.call_chat("system", "user")
        assert result.status == EndpointStatus.UNREACHABLE

    # TC-S3-11
    def test_chat_failure_connection_error_maps_to_unreachable(self, registry_path):
        router = _make_router(
            registry_path,
            [real_requests.exceptions.ConnectionError("refused")]
        )
        with patch("commands.ops.llm_router.requests") as mock_req:
            mock_req.post.side_effect = real_requests.exceptions.ConnectionError("off")
            mock_req.exceptions = real_requests.exceptions
            result = router.call_chat("system", "user")
        assert result.status == EndpointStatus.UNREACHABLE

    # TC-S3-12
    def test_chat_failure_still_has_metrics_event(self, registry_path):
        """Even on failure, the professionalize event is in first_result.metrics_events."""
        router = _make_router(
            registry_path,
            [real_requests.exceptions.ConnectionError("refused")]
        )
        with patch("commands.ops.llm_router.requests") as mock_req:
            mock_req.post.side_effect = real_requests.exceptions.ConnectionError("off")
            mock_req.exceptions = real_requests.exceptions
            result = router.call_chat("system", "user")
        assert len(result.metrics_events) == 1

    # TC-S3-13
    def test_chat_fallback_prof_event_preserved_in_result(self, registry_path):
        """Professionalize fails → fallback to ollama → prof event still in result."""
        router = _make_router(
            registry_path,
            [real_requests.exceptions.ConnectionError("refused")]
        )
        ollama_resp = _mock_chat_response('{"answer": "from ollama"}')
        with patch("commands.ops.llm_router.requests") as mock_req:
            mock_req.post.return_value = ollama_resp
            mock_req.exceptions = real_requests.exceptions
            result = router.call_chat("system", "user")

        assert result.status == EndpointStatus.OK
        assert result.provider == "ollama"
        # The professionalize failure event must be in metrics_events
        assert len(result.metrics_events) == 1
        assert result.metrics_events[0].call_site_id == "CS-001"

    # TC-S3-14: embeddings — emit event (CS-002)
    def test_embeddings_emits_metrics_event(self, registry_path):
        vectors = [[0.1] * 4096]
        router = _make_router(registry_path, [_prof_embed_resp(vectors)])
        result = router.call_embeddings(["text1"])
        assert result.status == EndpointStatus.OK
        assert len(result.metrics_events) == 1

    # TC-S3-15
    def test_embeddings_event_call_site_id_is_cs002(self, registry_path):
        vectors = [[0.1] * 4096]
        router = _make_router(registry_path, [_prof_embed_resp(vectors)])
        result = router.call_embeddings(["text1"])
        assert result.metrics_events[0].call_site_id == "CS-002"

    # TC-S3-16
    def test_embeddings_token_usage_populated(self, registry_path):
        vectors = [[0.1] * 4096, [0.2] * 4096]
        router = _make_router(registry_path, [_prof_embed_resp(vectors, prompt_tokens=8)])
        result = router.call_embeddings(["t1", "t2"])
        assert result.token_usage == 8

    # TC-S3-17
    def test_embeddings_api_calls_count_1_for_single_batch(self, registry_path):
        vectors = [[0.1] * 4096]
        router = _make_router(registry_path, [_prof_embed_resp(vectors)])
        result = router.call_embeddings(["text1"])
        assert result.api_calls_count == 1

    # TC-S3-18
    def test_embeddings_api_calls_count_2_for_two_batches(self, registry_path):
        """batch_size=1 → 2 texts → 2 HTTP calls → api_calls_count == 2."""
        vectors_a = [[0.1] * 4096]
        vectors_b = [[0.2] * 4096]
        router = _make_router(
            registry_path,
            [_prof_embed_resp(vectors_a, prompt_tokens=3),
             _prof_embed_resp(vectors_b, prompt_tokens=3)]
        )
        result = router.call_embeddings(["t1", "t2"], batch_size=1)
        assert result.api_calls_count == 2
        assert result.token_usage == 6  # 3 + 3

    # TC-S3-19: ollama — no professionalize events
    def test_ollama_chat_no_metrics_events(self, registry_path):
        mock_resp = _mock_chat_response('{"answer": "from ollama"}')
        with patch.dict(os.environ, {"PROFESSIONALIZE_API_KEY": ""}, clear=False):
            router = LLMRouter(registry_path=registry_path)
            with patch("commands.ops.llm_router.requests") as mock_req:
                mock_req.post.return_value = mock_resp
                mock_req.exceptions = real_requests.exceptions
                result = router.call_chat("system", "user")
        assert result.provider == "ollama"
        assert result.metrics_events == []

    # TC-S3-20
    def test_ollama_chat_token_usage_zero(self, registry_path):
        mock_resp = _mock_chat_response('{"answer": "from ollama"}')
        with patch.dict(os.environ, {"PROFESSIONALIZE_API_KEY": ""}, clear=False):
            router = LLMRouter(registry_path=registry_path)
            with patch("commands.ops.llm_router.requests") as mock_req:
                mock_req.post.return_value = mock_resp
                mock_req.exceptions = real_requests.exceptions
                result = router.call_chat("system", "user")
        assert result.token_usage == 0

    # TC-S3-21
    def test_ollama_chat_api_calls_count_zero(self, registry_path):
        mock_resp = _mock_chat_response('{"answer": "from ollama"}')
        with patch.dict(os.environ, {"PROFESSIONALIZE_API_KEY": ""}, clear=False):
            router = LLMRouter(registry_path=registry_path)
            with patch("commands.ops.llm_router.requests") as mock_req:
                mock_req.post.return_value = mock_resp
                mock_req.exceptions = real_requests.exceptions
                result = router.call_chat("system", "user")
        assert result.api_calls_count == 0

    # TC-S3-22: all providers fail — metrics_events in result
    def test_all_providers_fail_first_result_has_events(self, registry_path):
        router = _make_router(
            registry_path,
            [real_requests.exceptions.ConnectionError("refused")]
        )
        with patch("commands.ops.llm_router.requests") as mock_req:
            mock_req.post.side_effect = real_requests.exceptions.ConnectionError("off")
            mock_req.exceptions = real_requests.exceptions
            result = router.call_chat("system", "user")
        # first_result (professionalize failure) should have the event
        assert len(result.metrics_events) >= 1

    # TC-S3-23: CallResult field checks
    def test_call_result_has_token_usage_field(self):
        r = CallResult()
        assert hasattr(r, "token_usage")
        assert r.token_usage == 0

    # TC-S3-24
    def test_call_result_has_api_calls_count_field(self):
        r = CallResult()
        assert hasattr(r, "api_calls_count")
        assert r.api_calls_count == 0

    # TC-S3-25
    def test_router_http_client_reaches_prof_client(self, registry_path):
        """Verify _http_client param is used by ProfessionalizeClient transport."""
        fake_http = _FakeHTTPClient([_prof_chat_resp('{"ok": true}')])
        with patch.dict(os.environ, {"PROFESSIONALIZE_API_KEY": "test-key-123"}):
            router = LLMRouter(registry_path=registry_path, _http_client=fake_http)
            result = router.call_chat("system", "user")
        assert result.status == EndpointStatus.OK
        assert fake_http.call_count == 1
        assert "chat/completions" in fake_http.calls[0]["url"]


# ---------------------------------------------------------------------------
# _map_prof_status unit tests
# ---------------------------------------------------------------------------

class TestMapProfStatus:
    """Verify _map_prof_status maps correctly without calling real HTTP."""

    def _make_mock_result(self, ok, event_status="failure", http_status=None, error_summary=None):
        mock = MagicMock()
        mock.ok = ok
        mock.event.status = event_status
        mock.http_status = http_status
        mock.error_summary = error_summary
        return mock

    def test_ok_maps_to_endpoint_ok(self):
        r = self._make_mock_result(ok=True)
        status, err = _map_prof_status(r)
        assert status == EndpointStatus.OK
        assert err == ""

    def test_timeout_maps_to_unreachable(self):
        r = self._make_mock_result(ok=False, event_status="timeout")
        status, _ = _map_prof_status(r)
        assert status == EndpointStatus.UNREACHABLE

    def test_401_maps_to_auth_failed(self):
        r = self._make_mock_result(ok=False, http_status=401)
        status, _ = _map_prof_status(r)
        assert status == EndpointStatus.AUTH_FAILED

    def test_403_maps_to_auth_failed(self):
        r = self._make_mock_result(ok=False, http_status=403)
        status, _ = _map_prof_status(r)
        assert status == EndpointStatus.AUTH_FAILED

    def test_zero_http_maps_to_unreachable(self):
        r = self._make_mock_result(ok=False, http_status=0)
        status, _ = _map_prof_status(r)
        assert status == EndpointStatus.UNREACHABLE

    def test_successful_http_with_invalid_body_maps_to_parse_failed(self):
        r = self._make_mock_result(
            ok=False,
            http_status=200,
            error_summary="Decode error: empty response",
        )
        status, _ = _map_prof_status(r)
        assert status == EndpointStatus.PARSE_FAILED

    def test_500_maps_to_unknown(self):
        r = self._make_mock_result(ok=False, http_status=500)
        status, _ = _map_prof_status(r)
        assert status == EndpointStatus.UNKNOWN


# ---------------------------------------------------------------------------
# JSON repair and same-provider retry tests (TC-4a / TC-4b)
# ---------------------------------------------------------------------------

def test_json_repair_recovers_malformed_json(registry_path):
    """TC-4a: json_repair recovers malformed JSON → status OK, data returned."""
    try:
        import json_repair  # noqa: F401  # skip test if not installed
    except ImportError:
        pytest.skip("json_repair not installed")

    malformed = '{"a": 1"b": 2}'  # missing comma — classic parse failure
    response = _prof_chat_resp(f"Here is your data: {malformed}")
    router = _make_router(registry_path, http_responses=[response])

    result = router.call_chat("sys", "user", json_extract=True)

    assert result.status == EndpointStatus.OK
    assert isinstance(result.data, dict)
    assert result.data.get("a") == 1
    assert result.data.get("b") == 2


def test_parse_retry_makes_second_http_call(registry_path):
    """TC-4b: When repair unavailable and attempt 0 fails, retry makes new HTTP call."""
    malformed = '{"x": 1"y": 2}'   # missing comma
    good = '{"x": 1, "y": 2}'
    responses = [
        _prof_chat_resp(malformed),  # attempt 0: malformed
        _prof_chat_resp(good),       # attempt 1: valid
    ]
    router = _make_router(registry_path, http_responses=responses)

    with patch("commands.ops.llm_router._HAS_JSON_REPAIR", False):
        result = router.call_chat("sys", "user", json_extract=True)

    assert result.status == EndpointStatus.OK
    assert result.data == {"x": 1, "y": 2}


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
