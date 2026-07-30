"""CS-009: Metrics adapter tests for recommend.py _call_llm.

Verifies that SEO uses the canonical router and preserves attributed metrics.

When LITELLM_KEY is absent (llm_skipped=True), _call_llm is never called,
so no MetricsEvents are emitted.

Zero real network calls — openai is injected via sys.modules.

Slice 4 of Agent Metrics Integration (METRICS-PLAN-001 v7.1).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure scripts/seo and scripts/pipeline are on sys.path
_SCRIPTS = Path(__file__).resolve().parents[2]
_PIPELINE = _SCRIPTS / "pipeline"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
if str(_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_PIPELINE))

# Import the module under test
import seo.pipeline.recommend as recommend
from seo.pipeline.recommend import _call_llm, _METRICS_AVAILABLE
from commands.ops.llm_router import CallResult, EndpointStatus
from commands.ops.metrics_schema import MetricsEvent, now_iso8601, validate_event


# ---------------------------------------------------------------------------
# Helper: build fake openai responses
# ---------------------------------------------------------------------------


def _openai_resp(
    content: str = '{"proposed_title": "Best Title", "rationale": "good"}',
    total_tokens: int = 80,
) -> MagicMock:
    usage = MagicMock()
    usage.total_tokens = total_tokens
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = usage
    return resp


def _openai_empty_resp() -> MagicMock:
    usage = MagicMock()
    usage.total_tokens = 0
    message = MagicMock()
    message.content = ""
    choice = MagicMock()
    choice.message = message
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = usage
    return resp


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_openai():
    """Patch the canonical router used by SEO."""
    router = MagicMock()
    with patch("seo.pipeline.recommend.LLMRouter", return_value=router):
        yield router


@pytest.fixture(autouse=True)
def clear_metrics_events():
    """Clear the module-level metrics_events list before/after each test."""
    recommend.metrics_events.clear()
    yield
    recommend.metrics_events.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_client(mock_openai_fixture, *, side_effect=None, return_value=None) -> MagicMock:
    """Configure a canonical-router result from legacy-shaped fixture data."""
    def event(status: str, tokens: int = 0) -> MetricsEvent:
        return MetricsEvent(
            event_id="evt", call_site_id="CS-009",
            endpoint="https://llm.professionalize.com/v1/chat/completions",
            request_type="seo", status=status,
            prompt_tokens=0, completion_tokens=0, total_tokens=tokens,
            api_calls_count_delta=1, timestamp=now_iso8601(),
            consumer_id="seo-recommend", provider="professionalize",
        )

    def convert(response) -> CallResult:
        raw = response.choices[0].message.content
        tokens = response.usage.total_tokens
        if not raw:
            evt = event("failure", tokens)
            return CallResult(
                status=EndpointStatus.PARSE_FAILED, error="empty",
                metrics_events=[evt],
            )
        evt = event("success", tokens)
        return CallResult(
            provider="professionalize", status=EndpointStatus.OK,
            data=json.loads(raw), metrics_events=[evt],
        )

    if side_effect is not None:
        events = []
        final = None
        try:
            for _ in range(3):
                candidate = convert(side_effect())
                events.extend(candidate.metrics_events)
                final = candidate
                if candidate.status == EndpointStatus.OK:
                    break
        except Exception as exc:
            events.append(event("failure"))
            final = CallResult(
                status=EndpointStatus.UNREACHABLE, error=str(exc),
                metrics_events=events,
            )
        assert final is not None
        final.metrics_events = events
        mock_openai_fixture.call_chat.return_value = final
    else:
        mock_openai_fixture.call_chat.return_value = convert(return_value)
    return mock_openai_fixture


# ===========================================================================
# TC-S4-C009-01 through TC-S4-C009-10: _call_llm metrics
# ===========================================================================


@pytest.mark.skipif(not _METRICS_AVAILABLE, reason="metrics_schema not importable")
def test_call_llm_emits_metrics_event_on_success(mock_openai):
    """CS-009: _call_llm emits MetricsEvent when LLM returns valid JSON."""
    schema = {"proposed_title": "str", "rationale": "str"}
    _setup_client(
        mock_openai,
        return_value=_openai_resp('{"proposed_title": "New Title Here for SEO", "rationale": "Better."}'),
    )
    result = _call_llm("test prompt", "recommended", schema, "test-litellm-key")
    assert result is not None
    assert len(recommend.metrics_events) == 1


@pytest.mark.skipif(not _METRICS_AVAILABLE, reason="metrics_schema not importable")
def test_call_llm_event_call_site_id(mock_openai):
    """CS-009: emitted event has call_site_id='CS-009'."""
    schema = {"proposed_title": "str", "rationale": "str"}
    _setup_client(mock_openai, return_value=_openai_resp('{"proposed_title": "Title", "rationale": "OK"}'))
    _call_llm("test", "recommended", schema, "test-key")
    assert recommend.metrics_events[0].call_site_id == "CS-009"


@pytest.mark.skipif(not _METRICS_AVAILABLE, reason="metrics_schema not importable")
def test_call_llm_event_status_success(mock_openai):
    """CS-009: success → event.status='success'."""
    schema = {"proposed_title": "str", "rationale": "str"}
    _setup_client(mock_openai, return_value=_openai_resp('{"proposed_title": "T", "rationale": "OK"}'))
    _call_llm("test", "recommended", schema, "test-key")
    assert recommend.metrics_events[0].status == "success"


@pytest.mark.skipif(not _METRICS_AVAILABLE, reason="metrics_schema not importable")
def test_call_llm_event_request_type(mock_openai):
    """CS-009: event.request_type='seo'."""
    schema = {"proposed_title": "str", "rationale": "str"}
    _setup_client(mock_openai, return_value=_openai_resp('{"proposed_title": "T", "rationale": "OK"}'))
    _call_llm("test", "recommended", schema, "test-key")
    assert recommend.metrics_events[0].request_type == "seo"


@pytest.mark.skipif(not _METRICS_AVAILABLE, reason="metrics_schema not importable")
def test_call_llm_event_token_usage(mock_openai):
    """CS-009: token_usage from response.usage.total_tokens."""
    schema = {"proposed_title": "str", "rationale": "str"}
    _setup_client(
        mock_openai,
        return_value=_openai_resp('{"proposed_title": "T", "rationale": "OK"}', total_tokens=123),
    )
    _call_llm("test", "recommended", schema, "test-key")
    assert recommend.metrics_events[0].total_tokens == 123


@pytest.mark.skipif(not _METRICS_AVAILABLE, reason="metrics_schema not importable")
def test_call_llm_event_validates(mock_openai):
    """CS-009: emitted event passes schema validation."""
    schema = {"proposed_title": "str", "rationale": "str"}
    _setup_client(mock_openai, return_value=_openai_resp('{"proposed_title": "T", "rationale": "OK"}'))
    _call_llm("test", "recommended", schema, "test-key")
    result = validate_event(recommend.metrics_events[0])
    assert result.valid, result.errors


@pytest.mark.skipif(not _METRICS_AVAILABLE, reason="metrics_schema not importable")
def test_call_llm_empty_response_emits_failure_event(mock_openai):
    """CS-009: empty content → event.status='failure' per retry attempt."""
    schema = {"proposed_title": "str", "rationale": "str"}
    _setup_client(mock_openai, return_value=_openai_empty_resp())
    with patch("seo.pipeline.recommend.time.sleep"):
        result = _call_llm("test", "recommended", schema, "test-key")
    assert result is None
    assert len(recommend.metrics_events) >= 1
    assert all(e.status == "failure" for e in recommend.metrics_events)


@pytest.mark.skipif(not _METRICS_AVAILABLE, reason="metrics_schema not importable")
def test_call_llm_exception_emits_event(mock_openai):
    """CS-009: LLM API exception → MetricsEvent emitted per retry attempt."""
    schema = {"proposed_title": "str", "rationale": "str"}
    _setup_client(mock_openai, side_effect=RuntimeError("API down"))
    with patch("seo.pipeline.recommend.time.sleep"):
        result = _call_llm("test", "recommended", schema, "test-key")
    assert result is None
    assert len(recommend.metrics_events) >= 1
    for evt in recommend.metrics_events:
        assert evt.call_site_id == "CS-009"
        assert evt.status in ("failure", "timeout")


@pytest.mark.skipif(not _METRICS_AVAILABLE, reason="metrics_schema not importable")
def test_call_llm_retry_emits_event_per_attempt(mock_openai):
    """CS-009: 2 failed attempts then success → 3 events total."""
    schema = {"proposed_title": "str", "rationale": "str"}
    call_count = 0

    def _side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return _openai_empty_resp()
        return _openai_resp('{"proposed_title": "Good SEO Title Now", "rationale": "OK"}')

    _setup_client(mock_openai, side_effect=_side_effect)
    with patch("seo.pipeline.recommend.time.sleep"):
        result = _call_llm("test", "recommended", schema, "test-key")

    assert result == {"proposed_title": "Good SEO Title Now", "rationale": "OK"}
    assert len(recommend.metrics_events) == 3
    assert recommend.metrics_events[0].status == "failure"
    assert recommend.metrics_events[1].status == "failure"
    assert recommend.metrics_events[2].status == "success"


@pytest.mark.skipif(not _METRICS_AVAILABLE, reason="metrics_schema not importable")
def test_call_llm_api_calls_count_delta(mock_openai):
    """CS-009: api_calls_count_delta=1 per HTTP attempt."""
    schema = {"proposed_title": "str", "rationale": "str"}
    _setup_client(mock_openai, return_value=_openai_resp('{"proposed_title": "T", "rationale": "OK"}'))
    _call_llm("test", "recommended", schema, "test-key")
    assert recommend.metrics_events[0].api_calls_count_delta == 1


# ===========================================================================
# TC-S4-C009-11: LITELLM_KEY absent → no events (boundary test)
# ===========================================================================


@pytest.mark.skipif(not _METRICS_AVAILABLE, reason="metrics_schema not importable")
def test_litellm_key_absent_no_events():
    """CS-009 boundary: when LITELLM_KEY is None, _call_llm never called → no events."""
    from seo.pipeline.recommend import _gen_high_recommendations

    opp = {
        "page_path": "content/docs.aspose.org/en/words/python/some-page.md",
        "signals": {
            "primary_query": "aspose words python",
            "matched_keywords": ["aspose words python"],
            "title_aligned": False,
            "description_ok": True,
            "tag_gap_count": 0,
        },
        "seo_fields": {
            "seo_title": "Aspose Words for Python",
            "description": "Convert documents",
            "tags": [],
        },
    }
    _gen_high_recommendations(opp, litellm_key=None)
    assert len(recommend.metrics_events) == 0


# ===========================================================================
# TC-S4-C009-12: module-level metrics_events list exists
# ===========================================================================


def test_module_metrics_events_attribute_exists():
    """CS-009: recommend module exposes metrics_events list attribute."""
    assert hasattr(recommend, "metrics_events")
    assert isinstance(recommend.metrics_events, list)
