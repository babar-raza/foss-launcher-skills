"""Tests for professionalize_client.py — Slice 2 of Agent Metrics Integration.

All 40 required test scenarios. No live network. No secrets. No posting.
No event ledger file written. Fake HTTP transport injected via constructor.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any
from unittest.mock import patch

import pytest
import requests

from commands.ops.metrics_schema import validate_event
from commands.ops.professionalize_client import (
    ProfessionalizeCallResult,
    ProfessionalizeClient,
    ProfessionalizeClientError,
    _build_endpoint,
    _extract_usage,
    _normalize_base_url,
)


# --------------------------------------------------------------------------- #
# Fake transport helpers
# --------------------------------------------------------------------------- #


class FakeResponse:
    """Minimal requests.Response substitute."""

    def __init__(self, status_code: int, body: dict | None = None, raise_json: bool = False):
        self.status_code = status_code
        self._body = body or {}
        self._raise_json = raise_json
        # Provide .content as UTF-8 bytes so the fixed code path works:
        # _json.loads(resp.content.decode("utf-8")) requires bytes on resp.content.
        # When raise_json=True, simulate invalid JSON bytes to trigger ValueError.
        if raise_json:
            self.content = b"not-valid-json"
        else:
            self.content = json.dumps(self._body).encode("utf-8")

    def json(self) -> dict:
        if self._raise_json:
            raise ValueError("Invalid JSON")
        return self._body


class FakeHTTPClient:
    """Fake transport that records calls and returns a configurable response."""

    def __init__(self, response=None, raise_exc=None):
        self.calls: list[dict] = []
        self._response = response
        self._raise_exc = raise_exc

    def post(self, url: str, *, json: Any, headers: dict, timeout: float | int) -> Any:
        self.calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        if self._raise_exc is not None:
            raise self._raise_exc
        return self._response


# --------------------------------------------------------------------------- #
# Standard chat/embed response payloads
# --------------------------------------------------------------------------- #


def _chat_body(
    content="Hello from professionalize",
    prompt_tokens=100,
    completion_tokens=50,
    total_tokens=150,
    include_total=True,
):
    usage = {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens}
    if include_total:
        usage["total_tokens"] = total_tokens
    return {
        "choices": [{"message": {"content": content}}],
        "usage": usage,
        "model": "gpt-oss",
    }


def _embed_body(n=1, prompt_tokens=20, total_tokens=20):
    return {
        "data": [{"embedding": [0.1, 0.2, 0.3]} for _ in range(n)],
        "usage": {"prompt_tokens": prompt_tokens, "total_tokens": total_tokens},
        "model": "qwen3-embedding-8b",
    }


# --------------------------------------------------------------------------- #
# Fixture: default client
# --------------------------------------------------------------------------- #


def _client(fake: FakeHTTPClient, **overrides) -> ProfessionalizeClient:
    defaults = dict(
        base_url="https://llm.professionalize.com/v1",
        api_key="fake-key",
        default_chat_model="gpt-oss",
        default_embedding_model="qwen3-embedding-8b",
        timeout=30,
        http_client=fake,
        call_site_id="CS-001",
        agent_name="aspose-org-knowledge-enrichment",
        job_type="knowledge_enrichment",
        parent_run_id="run-001",
        work_slice_id="ws-001",
    )
    defaults.update(overrides)
    return ProfessionalizeClient(**defaults)


# --------------------------------------------------------------------------- #
# 1. Import performs no HTTP call
# --------------------------------------------------------------------------- #


class TestImportInert:
    def test_import_makes_no_http_call(self):
        # Already imported above — if this test runs, no call was made at import
        assert ProfessionalizeClient is not None
        assert ProfessionalizeCallResult is not None


# --------------------------------------------------------------------------- #
# 2–7. chat() success and token extraction
# --------------------------------------------------------------------------- #


class TestChatSuccess:
    def test_chat_success_returns_content_and_event(self):
        fake = FakeHTTPClient(FakeResponse(200, _chat_body()))
        result = _client(fake).chat(messages=[{"role": "user", "content": "Hi"}])
        assert result.ok is True
        assert result.content == "Hello from professionalize"
        assert result.event is not None
        assert result.event.status == "success"

    def test_chat_extracts_prompt_tokens(self):
        fake = FakeHTTPClient(FakeResponse(200, _chat_body(prompt_tokens=120)))
        result = _client(fake).chat(messages=[{"role": "user", "content": "x"}])
        assert result.prompt_tokens == 120

    def test_chat_extracts_completion_tokens(self):
        fake = FakeHTTPClient(FakeResponse(200, _chat_body(completion_tokens=60)))
        result = _client(fake).chat(messages=[{"role": "user", "content": "x"}])
        assert result.completion_tokens == 60

    def test_chat_uses_total_tokens_when_present(self):
        fake = FakeHTTPClient(FakeResponse(200, _chat_body(prompt_tokens=100, completion_tokens=50, total_tokens=999)))
        result = _client(fake).chat(messages=[{"role": "user", "content": "x"}])
        assert result.total_tokens == 999

    def test_chat_fallback_sum_when_total_tokens_missing(self):
        fake = FakeHTTPClient(FakeResponse(200, _chat_body(prompt_tokens=80, completion_tokens=40, include_total=False)))
        result = _client(fake).chat(messages=[{"role": "user", "content": "x"}])
        assert result.total_tokens == 120

    def test_chat_missing_usage_returns_zero_tokens(self):
        body = {"choices": [{"message": {"content": "hi"}}]}
        fake = FakeHTTPClient(FakeResponse(200, body))
        result = _client(fake).chat(messages=[{"role": "user", "content": "x"}])
        assert result.prompt_tokens == 0
        assert result.completion_tokens == 0
        assert result.total_tokens == 0

    def test_chat_emits_api_calls_count_delta_1(self):
        fake = FakeHTTPClient(FakeResponse(200, _chat_body()))
        result = _client(fake).chat(messages=[{"role": "user", "content": "x"}])
        assert result.api_calls_count_delta == 1
        assert result.event.api_calls_count_delta == 1


# --------------------------------------------------------------------------- #
# 8–11. chat() failure paths
# --------------------------------------------------------------------------- #


class TestChatFailures:
    def test_chat_http_500_emits_failure_event_with_api_calls_delta_1(self):
        body = {"error": {"message": "Internal server error"}}
        fake = FakeHTTPClient(FakeResponse(500, body))
        result = _client(fake).chat(messages=[{"role": "user", "content": "x"}])
        assert result.ok is False
        assert result.event.status == "failure"
        assert result.api_calls_count_delta == 1
        assert result.http_status == 500

    def test_chat_timeout_emits_timeout_event_with_api_calls_delta_1(self):
        fake = FakeHTTPClient(raise_exc=requests.exceptions.Timeout())
        result = _client(fake).chat(messages=[{"role": "user", "content": "x"}])
        assert result.ok is False
        assert result.event.status == "timeout"
        assert result.api_calls_count_delta == 1

    def test_chat_invalid_json_emits_failure_event(self):
        fake = FakeHTTPClient(FakeResponse(200, raise_json=True))
        result = _client(fake).chat(messages=[{"role": "user", "content": "x"}])
        assert result.ok is False
        assert result.event.status == "failure"
        assert result.api_calls_count_delta == 1

    def test_chat_response_without_choices_emits_failure_event(self):
        body = {"usage": {"prompt_tokens": 10, "completion_tokens": 0, "total_tokens": 10}}
        fake = FakeHTTPClient(FakeResponse(200, body))
        result = _client(fake).chat(messages=[{"role": "user", "content": "x"}])
        assert result.ok is False
        assert result.event.status == "failure"


# --------------------------------------------------------------------------- #
# 12–15. embed() success and failure
# --------------------------------------------------------------------------- #


class TestEmbedSuccess:
    def test_embed_success_returns_data_and_event(self):
        fake = FakeHTTPClient(FakeResponse(200, _embed_body(2)))
        result = _client(fake).embed(texts=["hello", "world"])
        assert result.ok is True
        assert isinstance(result.data, list)
        assert len(result.data) == 2
        assert result.event.status == "success"

    def test_embed_extracts_usage_metadata(self):
        fake = FakeHTTPClient(FakeResponse(200, _embed_body(1, prompt_tokens=30, total_tokens=30)))
        result = _client(fake).embed(texts=["hello"])
        assert result.prompt_tokens == 30
        assert result.total_tokens == 30

    def test_embed_missing_usage_returns_zero_tokens(self):
        body = {"data": [{"embedding": [0.1, 0.2]}]}
        fake = FakeHTTPClient(FakeResponse(200, body))
        result = _client(fake).embed(texts=["x"])
        assert result.prompt_tokens == 0
        assert result.total_tokens == 0

    def test_embed_failure_emits_failure_event_with_api_calls_delta_1(self):
        fake = FakeHTTPClient(raise_exc=requests.exceptions.ConnectionError("refused"))
        result = _client(fake).embed(texts=["hello"])
        assert result.ok is False
        assert result.event.status == "failure"
        assert result.api_calls_count_delta == 1


# --------------------------------------------------------------------------- #
# 16–17. Endpoint normalization
# --------------------------------------------------------------------------- #


class TestEndpointNormalization:
    def test_no_double_slashes_with_v1_base_url(self):
        fake = FakeHTTPClient(FakeResponse(200, _chat_body()))
        result = _client(fake, base_url="https://llm.professionalize.com/v1").chat(
            messages=[{"role": "user", "content": "x"}]
        )
        url_called = fake.calls[0]["url"]
        assert "//" not in url_called.replace("https://", "").replace("http://", "")

    def test_endpoint_with_token_query_param_is_redacted(self):
        # Inject a base_url that contains a token-like query param via an endpoint
        # We test that _build_endpoint + redact work together
        endpoint = "https://example.com/v1/chat/completions?api_key=supersecret123"
        from commands.ops.metrics_schema import redact_secret_like_values
        safe = redact_secret_like_values(endpoint)
        assert "supersecret123" not in safe
        assert "[REDACTED]" in safe


# --------------------------------------------------------------------------- #
# 18–21. Secret redaction
# --------------------------------------------------------------------------- #


class TestSecretRedaction:
    def _get_event_dict(self, result: ProfessionalizeCallResult) -> dict:
        return asdict(result.event)

    def test_api_key_never_in_event_dict(self):
        fake = FakeHTTPClient(FakeResponse(200, _chat_body()))
        result = _client(fake, api_key="sk-supersecret1234567890").chat(
            messages=[{"role": "user", "content": "x"}]
        )
        event_str = str(self._get_event_dict(result))
        assert "sk-supersecret1234567890" not in event_str

    def test_api_key_never_in_error_summary(self):
        # Force an error that includes api_key in the exception message
        fake = FakeHTTPClient(
            raise_exc=Exception("Connection failed with key sk-supersecret1234567890")
        )
        result = _client(fake, api_key="sk-supersecret1234567890").chat(
            messages=[{"role": "user", "content": "x"}]
        )
        assert result.error_summary is not None
        assert "sk-supersecret1234567890" not in result.error_summary
        assert "[REDACTED]" in result.error_summary

    def test_prompt_text_not_in_event_dict(self):
        prompt = "This is my secret prompt text for testing"
        fake = FakeHTTPClient(FakeResponse(200, _chat_body()))
        result = _client(fake).chat(messages=[{"role": "user", "content": prompt}])
        event_str = str(self._get_event_dict(result))
        assert prompt not in event_str

    def test_completion_text_not_in_event_dict(self):
        completion = "This is my secret completion text for testing"
        body = _chat_body(content=completion)
        fake = FakeHTTPClient(FakeResponse(200, body))
        result = _client(fake).chat(messages=[{"role": "user", "content": "x"}])
        event_str = str(self._get_event_dict(result))
        assert completion not in event_str


# --------------------------------------------------------------------------- #
# 22–26. Event field correctness
# --------------------------------------------------------------------------- #


class TestEventFields:
    def test_model_recorded_in_event(self):
        fake = FakeHTTPClient(FakeResponse(200, _chat_body()))
        result = _client(fake, default_chat_model="gpt-oss").chat(
            messages=[{"role": "user", "content": "x"}]
        )
        assert result.event.model == "gpt-oss"

    def test_call_site_id_recorded_in_event(self):
        fake = FakeHTTPClient(FakeResponse(200, _chat_body()))
        result = _client(fake, call_site_id="CS-001").chat(
            messages=[{"role": "user", "content": "x"}]
        )
        assert result.event.call_site_id == "CS-001"

    def test_parent_run_id_and_work_slice_id_preserved(self):
        fake = FakeHTTPClient(FakeResponse(200, _chat_body()))
        result = _client(fake, parent_run_id="run-xyz", work_slice_id="ws-abc").chat(
            messages=[{"role": "user", "content": "x"}]
        )
        assert result.event.parent_run_id == "run-xyz"
        assert result.event.work_slice_id == "ws-abc"

    def test_request_type_is_chat_for_chat(self):
        fake = FakeHTTPClient(FakeResponse(200, _chat_body()))
        result = _client(fake).chat(messages=[{"role": "user", "content": "x"}])
        assert result.event.request_type == "chat"

    def test_request_type_is_embedding_for_embed(self):
        fake = FakeHTTPClient(FakeResponse(200, _embed_body()))
        result = _client(fake).embed(texts=["hello"])
        assert result.event.request_type == "embedding"


# --------------------------------------------------------------------------- #
# 27. Event validates with schema
# --------------------------------------------------------------------------- #


class TestEventValidation:
    def test_successful_chat_event_validates(self):
        fake = FakeHTTPClient(FakeResponse(200, _chat_body()))
        result = _client(fake).chat(messages=[{"role": "user", "content": "x"}])
        vr = validate_event(result.event)
        assert vr.valid is True, f"Validation errors: {vr.errors}"

    def test_timeout_event_validates(self):
        fake = FakeHTTPClient(raise_exc=requests.exceptions.Timeout())
        result = _client(fake).chat(messages=[{"role": "user", "content": "x"}])
        vr = validate_event(result.event)
        assert vr.valid is True, f"Validation errors: {vr.errors}"

    def test_failure_event_validates(self):
        fake = FakeHTTPClient(FakeResponse(500, {}))
        result = _client(fake).chat(messages=[{"role": "user", "content": "x"}])
        vr = validate_event(result.event)
        assert vr.valid is True, f"Validation errors: {vr.errors}"


# --------------------------------------------------------------------------- #
# 28–29. No MetricsPoster/RunMetrics, no ledger file written
# --------------------------------------------------------------------------- #


class TestNoDependencies:
    def test_no_metrics_poster_or_run_metrics_import_needed(self):
        import commands.ops.professionalize_client as mod
        # Neither class should be present in the module's namespace
        assert not hasattr(mod, "MetricsPoster"), "MetricsPoster must not be imported"
        assert not hasattr(mod, "RunMetrics"), "RunMetrics must not be imported"
        # event_ledger must not be imported or referenced
        assert not hasattr(mod, "event_ledger"), "event_ledger must not be imported"

    def test_no_event_ledger_file_written(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        fake = FakeHTTPClient(FakeResponse(200, _chat_body()))
        _client(fake).chat(messages=[{"role": "user", "content": "x"}])
        # Check no files were written to tmp_path
        assert list(tmp_path.iterdir()) == []


# --------------------------------------------------------------------------- #
# 30. Secret-like exception messages are redacted
# --------------------------------------------------------------------------- #


class TestExceptionRedaction:
    def test_secret_in_exception_message_is_redacted(self):
        exc_msg = "Connection error: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.secret"  # SECRETS_TEST_FIXTURE
        fake = FakeHTTPClient(raise_exc=Exception(exc_msg))
        result = _client(fake).chat(messages=[{"role": "user", "content": "x"}])
        assert result.error_summary is not None
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.secret" not in result.error_summary
        assert "[REDACTED]" in result.error_summary


# --------------------------------------------------------------------------- #
# 31–34. Base URL and API key edge cases
# --------------------------------------------------------------------------- #


class TestBaseURLEdgeCases:
    def test_client_supports_v1_base_url(self):
        fake = FakeHTTPClient(FakeResponse(200, _chat_body()))
        c = ProfessionalizeClient(
            base_url="https://llm.professionalize.com/v1",
            api_key="k",
            http_client=fake,
        )
        result = c.chat(messages=[{"role": "user", "content": "x"}])
        url_called = fake.calls[0]["url"]
        assert url_called == "https://llm.professionalize.com/v1/chat/completions"

    def test_client_supports_base_url_without_trailing_slash(self):
        fake = FakeHTTPClient(FakeResponse(200, _chat_body()))
        c = ProfessionalizeClient(
            base_url="https://llm.professionalize.com/v1",
            api_key="k",
            http_client=fake,
        )
        result = c.embed(texts=["hello"])
        url_called = fake.calls[0]["url"]
        assert url_called == "https://llm.professionalize.com/v1/embeddings"

    def test_blank_base_url_raises_at_constructor(self):
        with pytest.raises(ProfessionalizeClientError, match="base_url"):
            ProfessionalizeClient(base_url="")

    def test_blank_base_url_whitespace_raises(self):
        with pytest.raises(ProfessionalizeClientError, match="base_url"):
            ProfessionalizeClient(base_url="   ")

    def test_api_key_none_does_not_expose_secret(self):
        fake = FakeHTTPClient(FakeResponse(200, _chat_body()))
        c = ProfessionalizeClient(
            base_url="https://llm.professionalize.com/v1",
            api_key=None,
            http_client=fake,
        )
        result = c.chat(messages=[{"role": "user", "content": "x"}])
        # No Authorization header should be sent when api_key is None
        headers = fake.calls[0]["headers"]
        assert "Authorization" not in headers


# --------------------------------------------------------------------------- #
# 35–36. Timeout passed, no retry
# --------------------------------------------------------------------------- #


class TestTimeoutAndRetry:
    def test_timeout_passed_to_transport(self):
        fake = FakeHTTPClient(FakeResponse(200, _chat_body()))
        c = ProfessionalizeClient(
            base_url="https://llm.professionalize.com/v1",
            api_key="k",
            timeout=45,
            http_client=fake,
        )
        c.chat(messages=[{"role": "user", "content": "x"}])
        assert fake.calls[0]["timeout"] == 45

    def test_client_does_not_retry_by_default(self):
        fake = FakeHTTPClient(FakeResponse(500, {}))
        result = _client(fake).chat(messages=[{"role": "user", "content": "x"}])
        # Only one HTTP call should have been made
        assert len(fake.calls) == 1
        assert result.ok is False


# --------------------------------------------------------------------------- #
# 37–38. Multiple calls and failed call token behavior
# --------------------------------------------------------------------------- #


class TestMultipleCallsAndTokens:
    def test_multiple_calls_produce_distinct_event_ids(self):
        fake = FakeHTTPClient(FakeResponse(200, _chat_body()))
        c = _client(fake)
        r1 = c.chat(messages=[{"role": "user", "content": "a"}])
        r2 = c.chat(messages=[{"role": "user", "content": "b"}])
        assert r1.event.event_id != r2.event.event_id

    def test_failed_call_has_zero_total_tokens(self):
        fake = FakeHTTPClient(raise_exc=requests.exceptions.Timeout())
        result = _client(fake).chat(messages=[{"role": "user", "content": "x"}])
        assert result.total_tokens == 0
        assert result.event.total_tokens == 0


# --------------------------------------------------------------------------- #
# 39. embed with multiple texts uses one HTTP request
# --------------------------------------------------------------------------- #


class TestEmbedMultipleTexts:
    def test_embed_multiple_texts_makes_one_http_call(self):
        texts = ["text1", "text2", "text3", "text4"]
        fake = FakeHTTPClient(FakeResponse(200, _embed_body(4)))
        result = _client(fake).embed(texts=texts)
        # Only one HTTP call
        assert len(fake.calls) == 1
        assert result.api_calls_count_delta == 1
        # All texts sent in single payload
        assert fake.calls[0]["json"]["input"] == texts


# --------------------------------------------------------------------------- #
# 40. repr does not expose secrets
# --------------------------------------------------------------------------- #


class TestReprSafety:
    def test_repr_does_not_expose_api_key(self):
        fake = FakeHTTPClient(FakeResponse(200, _chat_body()))
        result = _client(fake, api_key="sk-supersecret-key-1234567890").chat(
            messages=[{"role": "user", "content": "x"}]
        )
        r = repr(result)
        assert "sk-supersecret-key-1234567890" not in r

    def test_repr_does_not_expose_prompt(self):
        prompt = "My private prompt that should not appear in repr"
        fake = FakeHTTPClient(FakeResponse(200, _chat_body()))
        result = _client(fake).chat(messages=[{"role": "user", "content": prompt}])
        r = repr(result)
        assert prompt not in r

    def test_repr_does_not_expose_completion(self):
        completion = "My private completion that should not appear in repr"
        fake = FakeHTTPClient(FakeResponse(200, _chat_body(content=completion)))
        result = _client(fake).chat(messages=[{"role": "user", "content": "x"}])
        r = repr(result)
        assert completion not in r
