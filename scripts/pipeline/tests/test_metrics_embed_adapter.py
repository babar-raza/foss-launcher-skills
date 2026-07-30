"""CS-004: Metrics adapter tests for EmbeddingClient.embed_batch (embed.py).

Verifies that the professionalize tier emits MetricsEvent objects per HTTP
batch call and that the ollama tier (no call_site_id) does NOT emit events.

Zero real network calls — all HTTP injected via _http_client / _FakeHTTPClient.

Slice 4 of Agent Metrics Integration (METRICS-PLAN-001 v7.1).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

# Ensure scripts/pipeline is on sys.path (mirrors conftest.py)
_PIPELINE_ROOT = Path(__file__).resolve().parent.parent
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from commands.knowledge.embed import EmbeddingClient, _PROF_CLIENT_AVAILABLE
from commands.ops.metrics_schema import MetricsEvent, validate_event

_CANONICAL_EMBED_DIMENSIONS = 512


@pytest.fixture(autouse=True)
def _canonical_test_credential(monkeypatch):
    """Keep adapter tests hermetic while preserving registry-owned credentials."""
    monkeypatch.setenv("LLM_API_KEY", "st043-test-only-key")


# ---------------------------------------------------------------------------
# Fake HTTP transport for ProfessionalizeClient injection
# ---------------------------------------------------------------------------


class _FakeHTTPClient:
    """Fake transport implementing the HTTPTransport Protocol."""

    def __init__(self, side_effects: list):
        self._effects = list(side_effects)
        self.calls: list[dict] = []

    def post(self, url: str, *, json: Any, headers: dict, timeout: float) -> Any:
        self.calls.append({"url": url, "json": json, "headers": headers})
        if not self._effects:
            raise ConnectionError("No more configured responses")
        effect = self._effects.pop(0)
        if isinstance(effect, BaseException):
            raise effect
        return effect


def _embed_resp(vectors: list[list[float]], total_tokens: int = 100) -> MagicMock:
    """Build a fake HTTP response for an embeddings request."""
    vectors = [
        v + [0.0] * (_CANONICAL_EMBED_DIMENSIONS - len(v))
        for v in vectors
    ]
    resp = MagicMock()
    resp.status_code = 200
    data = [{"object": "embedding", "index": i, "embedding": v} for i, v in enumerate(vectors)]
    body = {
        "object": "list",
        "data": data,
        "usage": {
            "prompt_tokens": total_tokens,
            "total_tokens": total_tokens,
        },
    }
    resp.content = json.dumps(body).encode("utf-8")
    resp.json.return_value = body
    return resp


def _embed_error_resp(status_code: int = 500) -> MagicMock:
    """Build a fake HTTP error response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = {"error": {"message": f"HTTP {status_code}"}}
    return resp


def _make_prof_client(http_responses: list) -> EmbeddingClient:
    """Create an EmbeddingClient for the professionalize tier with injected transport."""
    http = _FakeHTTPClient(http_responses)
    return EmbeddingClient(
        "https://llm.professionalize.com/v1/embeddings",
        "qwen3-embedding-8b",
        "test-api-key",
        call_site_id="CS-004",
        _http_client=http,
    )


def _make_ollama_client() -> EmbeddingClient:
    """Legacy constructor arguments still route through the canonical client."""
    return EmbeddingClient(
        "http://localhost:11434/v1/embeddings",
        "nomic-embed-text",
        "",
        _http_client=_FakeHTTPClient([_embed_resp([[0.5, 0.6]])]),
    )


# ===========================================================================
# Fixture check
# ===========================================================================


@pytest.mark.skipif(not _PROF_CLIENT_AVAILABLE, reason="ProfessionalizeClient not importable")
def test_prof_client_available():
    """ProfessionalizeClient must be importable for CS-004 adapter to work."""
    assert _PROF_CLIENT_AVAILABLE is True


# ===========================================================================
# TC-S4-C004-01 through TC-S4-C004-12: CS-004 embed_batch metrics
# ===========================================================================


@pytest.mark.skipif(not _PROF_CLIENT_AVAILABLE, reason="ProfessionalizeClient not importable")
def test_embed_batch_emits_metrics_event():
    """CS-004: professionalize embed_batch emits MetricsEvent."""
    client = _make_prof_client([_embed_resp([[0.1, 0.2, 0.3]])])
    client.embed_batch(["hello world"])
    assert len(client.metrics_events) == 1


@pytest.mark.skipif(not _PROF_CLIENT_AVAILABLE, reason="ProfessionalizeClient not importable")
def test_embed_batch_event_call_site_id():
    """CS-004: emitted event has call_site_id='CS-004'."""
    client = _make_prof_client([_embed_resp([[0.1, 0.2, 0.3]])])
    client.embed_batch(["hello world"])
    event = client.metrics_events[0]
    assert isinstance(event, MetricsEvent)
    assert event.call_site_id == "CS-004"


@pytest.mark.skipif(not _PROF_CLIENT_AVAILABLE, reason="ProfessionalizeClient not importable")
def test_embed_batch_event_status_success():
    """CS-004: successful batch → event.status='success'."""
    client = _make_prof_client([_embed_resp([[0.1, 0.2, 0.3]])])
    client.embed_batch(["hello world"])
    assert client.metrics_events[0].status == "success"


@pytest.mark.skipif(not _PROF_CLIENT_AVAILABLE, reason="ProfessionalizeClient not importable")
def test_embed_batch_event_request_type():
    """CS-004: event.request_type='embedding'."""
    client = _make_prof_client([_embed_resp([[0.1, 0.2, 0.3]])])
    client.embed_batch(["hello world"])
    assert client.metrics_events[0].request_type == "embedding"


@pytest.mark.skipif(not _PROF_CLIENT_AVAILABLE, reason="ProfessionalizeClient not importable")
def test_embed_batch_event_token_usage():
    """CS-004: token_usage is extracted from usage metadata."""
    client = _make_prof_client([_embed_resp([[0.1]], total_tokens=256)])
    client.embed_batch(["hello world"])
    assert client.metrics_events[0].total_tokens == 256


@pytest.mark.skipif(not _PROF_CLIENT_AVAILABLE, reason="ProfessionalizeClient not importable")
def test_embed_batch_api_calls_count_delta():
    """CS-004: api_calls_count_delta=1 per batch HTTP call."""
    client = _make_prof_client([_embed_resp([[0.1, 0.2]])])
    client.embed_batch(["text1"])
    assert client.metrics_events[0].api_calls_count_delta == 1


@pytest.mark.skipif(not _PROF_CLIENT_AVAILABLE, reason="ProfessionalizeClient not importable")
def test_embed_batch_single_batch_one_event():
    """CS-004: single batch (texts < batch_size) → exactly 1 event."""
    client = _make_prof_client([_embed_resp([[0.1], [0.2], [0.3]])])
    client.embed_batch(["a", "b", "c"])
    assert len(client.metrics_events) == 1


@pytest.mark.skipif(not _PROF_CLIENT_AVAILABLE, reason="ProfessionalizeClient not importable")
def test_embed_batch_two_batches_two_events():
    """CS-004: two HTTP batches → two events, api_calls cumulate correctly."""
    vectors_batch1 = [[0.1] * 3] * 2  # 2 vectors per batch
    vectors_batch2 = [[0.2] * 3] * 2
    client = _make_prof_client([
        _embed_resp(vectors_batch1, total_tokens=100),
        _embed_resp(vectors_batch2, total_tokens=80),
    ])
    result = client.embed_batch(["a", "b", "c", "d"], batch_size=2)
    assert len(client.metrics_events) == 2
    assert len(result) == 4


@pytest.mark.skipif(not _PROF_CLIENT_AVAILABLE, reason="ProfessionalizeClient not importable")
def test_embed_batch_event_validates():
    """CS-004: emitted MetricsEvent passes schema validation."""
    client = _make_prof_client([_embed_resp([[0.1, 0.2, 0.3]])])
    client.embed_batch(["hello world"])
    result = validate_event(client.metrics_events[0])
    assert result.valid, result.errors


@pytest.mark.skipif(not _PROF_CLIENT_AVAILABLE, reason="ProfessionalizeClient not importable")
def test_embed_batch_endpoint_contains_embeddings():
    """CS-004: event.endpoint contains 'embeddings'."""
    client = _make_prof_client([_embed_resp([[0.1, 0.2, 0.3]])])
    client.embed_batch(["hello world"])
    assert "embeddings" in client.metrics_events[0].endpoint


@pytest.mark.skipif(not _PROF_CLIENT_AVAILABLE, reason="ProfessionalizeClient not importable")
def test_embed_batch_failure_emits_event():
    """CS-004: HTTP failure → MetricsEvent is still emitted with status='failure'."""
    from requests.exceptions import ConnectionError as ReqConnError

    client = _make_prof_client([ReqConnError("network down")])
    with pytest.raises(RuntimeError):
        client.embed_batch(["hello world"])
    assert len(client.metrics_events) == 1
    assert client.metrics_events[0].status in ("failure", "timeout")


@pytest.mark.skipif(not _PROF_CLIENT_AVAILABLE, reason="ProfessionalizeClient not importable")
def test_embed_batch_metrics_events_reset_per_call():
    """CS-004: metrics_events resets at the start of each embed_batch call."""
    client = _make_prof_client([
        _embed_resp([[0.1]]),
        _embed_resp([[0.2]]),
    ])
    client.embed_batch(["first call"])
    assert len(client.metrics_events) == 1

    # Second call: events should be reset (only the new call's event)
    client.embed_batch(["second call"])
    assert len(client.metrics_events) == 1


# ===========================================================================
# TC-S4-C004-13 to TC-S4-C004-15: Ollama isolation (no metrics)
# ===========================================================================


def test_legacy_constructor_routes_through_canonical_metrics():
    """Legacy endpoint arguments cannot bypass router/client metrics."""
    client = _make_ollama_client()
    client.embed_batch(["hello"])
    assert len(client.metrics_events) == 1
    assert client.metrics_events[0].call_site_id == "CS-004"


# ===========================================================================
# TC-S4-C004-16: Vectors returned correctly
# ===========================================================================


@pytest.mark.skipif(not _PROF_CLIENT_AVAILABLE, reason="ProfessionalizeClient not importable")
def test_embed_batch_returns_correct_vectors():
    """CS-004: embed_batch returns correct list of vectors."""
    expected = [
        [0.1, 0.2] + [0.0] * (_CANONICAL_EMBED_DIMENSIONS - 2),
        [0.3, 0.4] + [0.0] * (_CANONICAL_EMBED_DIMENSIONS - 2),
    ]
    client = _make_prof_client([_embed_resp(expected)])
    result = client.embed_batch(["text1", "text2"])
    assert result == expected


def test_embed_batch_rejects_retired_4096_dimension_contract():
    """A real 4,096-dimensional response is a contract mismatch, not success."""
    response = MagicMock()
    response.status_code = 200
    body = {
        "data": [{"index": 0, "embedding": [0.1] * 4096}],
        "usage": {"total_tokens": 1},
    }
    response.content = json.dumps(body).encode("utf-8")
    client = _make_prof_client([response])

    with pytest.raises(RuntimeError, match="contract_mismatch"):
        client.embed_batch(["legacy-dimension"])
