# Adapted from aspose.org
"""Canonical metrics-aware ProfessionalizeClient wrapper.

Makes professionalize chat and embedding calls, extracts usage metadata,
counts API attempts, redacts secrets, and produces MetricsEvent objects
using the Slice 1 schema.

Inert on import — no HTTP calls are made until chat() or embed() is called.
No event ledger writing. No Google Sheet posting. No RunMetrics.

Slice 2 of Agent Metrics Integration (METRICS-PLAN-001 v7.1).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

import requests
from requests.exceptions import Timeout as RequestsTimeout

from commands.ops.metrics_schema import (
    MetricsEvent,
    generate_event_id,
    now_iso8601,
    redact_secret_like_values,
    validate_event,
)


# --------------------------------------------------------------------------- #
# Transport Protocol
# --------------------------------------------------------------------------- #


@runtime_checkable
class HTTPTransport(Protocol):
    """Minimal interface for an HTTP client used by ProfessionalizeClient.

    Any object with a ``post()`` method matching this signature is accepted.
    This allows tests to inject a fake transport without depending on requests
    internals.
    """

    def post(
        self,
        url: str,
        *,
        json: Any,
        headers: dict,
        timeout: float | int,
    ) -> Any: ...


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #


class ProfessionalizeClientError(Exception):
    """Raised for client configuration errors (e.g., blank base_url)."""


# --------------------------------------------------------------------------- #
# Result
# --------------------------------------------------------------------------- #


@dataclass
class ProfessionalizeCallResult:
    """Outcome of a single professionalize API call.

    Carries a MetricsEvent (with no prompt/completion text) plus the decoded
    response payload. ``__repr__`` never exposes API keys, prompts, or
    completion text.
    """

    ok: bool
    event: MetricsEvent
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    api_calls_count_delta: int
    http_status: int | None
    latency_ms: int | None
    model: str | None
    endpoint: str
    error_summary: str | None  # always redacted via redact_secret_like_values()
    content: str | None = None  # chat: completion text (not stored in event)
    data: list | None = None  # embed: list of vector objects (not stored in event)

    def __repr__(self) -> str:
        return (
            f"ProfessionalizeCallResult("
            f"ok={self.ok}, "
            f"model={self.model!r}, "
            f"total_tokens={self.total_tokens}, "
            f"http_status={self.http_status}, "
            f"latency_ms={self.latency_ms}, "
            f"content=[{len(self.content or '')} chars hidden], "
            f"data=[{len(self.data or [])} vectors hidden]"
            f")"
        )


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #


def _normalize_base_url(base_url: str) -> str:
    """Strip trailing slashes. Raise ProfessionalizeClientError if blank."""
    if not isinstance(base_url, str) or not base_url.strip():
        raise ProfessionalizeClientError("base_url must not be blank")
    return base_url.strip().rstrip("/")


def _build_endpoint(base_url: str, path: str) -> str:
    """Join normalized base_url with path; no double slashes."""
    return base_url.rstrip("/") + "/" + path.lstrip("/")


def _extract_usage(body: dict) -> tuple[int, int, int]:
    """Safely extract (prompt_tokens, completion_tokens, total_tokens).

    Returns (0, 0, 0) when usage is absent, malformed, or negative.
    Uses total_tokens from the response when present and non-negative;
    falls back to prompt_tokens + completion_tokens otherwise.
    """
    usage = body.get("usage") if isinstance(body, dict) else None
    if not isinstance(usage, dict):
        return 0, 0, 0

    pt = usage.get("prompt_tokens", 0)
    ct = usage.get("completion_tokens", 0)
    tt = usage.get("total_tokens")

    pt = pt if (isinstance(pt, int) and pt >= 0) else 0
    ct = ct if (isinstance(ct, int) and ct >= 0) else 0

    if isinstance(tt, int) and tt >= 0:
        return pt, ct, tt
    return pt, ct, pt + ct


def _safe_latency_ms(elapsed_s: float) -> int:
    """Convert elapsed seconds to non-negative integer milliseconds."""
    ms = int(elapsed_s * 1000)
    return max(ms, 0)


def _extract_chat_content(body: dict) -> tuple[str | None, str | None]:
    """Extract completion text from OpenAI-compatible chat response.

    Returns (content_str, None) on success, or (None, error_msg) on failure.
    """
    if not isinstance(body, dict):
        return None, "Response body is not a dict"
    choices = body.get("choices")
    if not choices or not isinstance(choices, list):
        return None, "Response missing 'choices' field"
    first = choices[0]
    if not isinstance(first, dict):
        return None, "choices[0] is not a dict"
    message = first.get("message", {})
    text = message.get("content")
    if text is None:
        return None, "choices[0].message.content is None"
    return str(text), None


def _extract_embedding_data(body: dict) -> tuple[list | None, str | None]:
    """Extract embedding vectors from OpenAI-compatible embeddings response.

    Returns (data_list, None) on success, or (None, error_msg) on failure.
    """
    if not isinstance(body, dict):
        return None, "Response body is not a dict"
    data = body.get("data")
    if data is None or not isinstance(data, list):
        return None, "Response missing 'data' field"
    return data, None


# --------------------------------------------------------------------------- #
# Client
# --------------------------------------------------------------------------- #


class ProfessionalizeClient:
    """Metrics-aware HTTP client for llm.professionalize.com.

    Emits a MetricsEvent for every chat() or embed() call. Events contain
    usage metadata, status, model, call_site_id, and timing — never prompts
    or completions.

    No event ledger writing occurs in this class. Callers receive a
    ProfessionalizeCallResult containing the event and may persist it as
    needed in a later slice.

    Dependency injection
    --------------------
    Pass ``http_client`` (any object with a ``.post()`` method) to substitute
    a fake transport in tests. When ``http_client`` is None, ``requests`` is
    used at call time.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        default_chat_model: str | None = None,
        default_embedding_model: str | None = None,
        timeout: float | int = 30,
        http_client: HTTPTransport | None = None,
        call_site_id: str | None = None,
        agent_name: str | None = None,
        job_type: str | None = None,
        parent_run_id: str | None = None,
        work_slice_id: str | None = None,
    ) -> None:
        self._base_url = _normalize_base_url(base_url)  # raises on blank
        self._api_key = api_key
        self._default_chat_model = default_chat_model
        self._default_embedding_model = default_embedding_model
        self._timeout = timeout
        self._http_client = http_client  # None → use requests at call time
        self._default_call_site_id = call_site_id or "CS-UNKNOWN"
        self._default_agent_name = agent_name
        self._default_job_type = job_type
        self._default_parent_run_id = parent_run_id
        self._default_work_slice_id = work_slice_id

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def chat(
        self,
        *,
        messages: list[dict],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        call_site_id: str | None = None,
        agent_name: str | None = None,
        job_type: str | None = None,
        parent_run_id: str | None = None,
        work_slice_id: str | None = None,
    ) -> ProfessionalizeCallResult:
        """Make a chat/completion call to professionalize.

        Returns ProfessionalizeCallResult — never raises.
        Input ``messages`` and completion text are NOT stored in the event.
        """
        effective_model = model or self._default_chat_model
        endpoint = _build_endpoint(self._base_url, "chat/completions")

        payload: dict = {"messages": messages}
        if effective_model:
            payload["model"] = effective_model
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        return self._call(
            endpoint=endpoint,
            payload=payload,
            request_type="chat",
            call_site_id=call_site_id or self._default_call_site_id,
            agent_name=agent_name or self._default_agent_name,
            job_type=job_type or self._default_job_type,
            parent_run_id=parent_run_id or self._default_parent_run_id,
            work_slice_id=work_slice_id or self._default_work_slice_id,
            model=effective_model,
            result_extractor=_extract_chat_content,
        )

    def embed(
        self,
        *,
        texts: list[str],
        model: str | None = None,
        call_site_id: str | None = None,
        agent_name: str | None = None,
        job_type: str | None = None,
        parent_run_id: str | None = None,
        work_slice_id: str | None = None,
    ) -> ProfessionalizeCallResult:
        """Make an embeddings call to professionalize.

        Returns ProfessionalizeCallResult — never raises.
        Input ``texts`` are NOT stored in the event.
        """
        effective_model = model or self._default_embedding_model
        endpoint = _build_endpoint(self._base_url, "embeddings")

        payload: dict = {"input": texts}
        if effective_model:
            payload["model"] = effective_model

        return self._call(
            endpoint=endpoint,
            payload=payload,
            request_type="embedding",
            call_site_id=call_site_id or self._default_call_site_id,
            agent_name=agent_name or self._default_agent_name,
            job_type=job_type or self._default_job_type,
            parent_run_id=parent_run_id or self._default_parent_run_id,
            work_slice_id=work_slice_id or self._default_work_slice_id,
            model=effective_model,
            result_extractor=_extract_embedding_data,
        )

    # ------------------------------------------------------------------ #
    # Internal transport + event emission
    # ------------------------------------------------------------------ #

    def _post(self, url: str, *, json_body: dict, headers: dict) -> Any:
        """Dispatch HTTP POST via injected client or requests module."""
        if self._http_client is not None:
            return self._http_client.post(
                url, json=json_body, headers=headers, timeout=self._timeout
            )
        return requests.post(
            url, json=json_body, headers=headers, timeout=self._timeout
        )

    def _build_headers(self) -> dict:
        h: dict = {"Content-Type": "application/json"}
        if self._api_key:
            h["Authorization"] = f"Bearer {self._api_key}"
        return h

    def _call(
        self,
        *,
        endpoint: str,
        payload: dict,
        request_type: str,
        call_site_id: str,
        agent_name: str | None,
        job_type: str | None,
        parent_run_id: str | None,
        work_slice_id: str | None,
        model: str | None,
        result_extractor,
    ) -> ProfessionalizeCallResult:
        """Core transport + event emission. Shared by chat() and embed()."""
        # Redact any token-like query params that may have crept into endpoint
        safe_endpoint = redact_secret_like_values(endpoint)
        headers = self._build_headers()
        timestamp = now_iso8601()
        event_id = generate_event_id()

        # api_calls_count_delta = 1: transport is always attempted from here.
        api_calls_count_delta = 1
        http_status: int | None = None
        status = "failure"
        prompt_tokens = completion_tokens = total_tokens = 0
        latency_ms: int | None = None
        error_summary: str | None = None
        content: str | None = None
        data: list | None = None

        t0 = time.monotonic()
        try:
            resp = self._post(safe_endpoint, json_body=payload, headers=headers)
            latency_ms = _safe_latency_ms(time.monotonic() - t0)
            http_status = resp.status_code

            body = resp.json()
            prompt_tokens, completion_tokens, total_tokens = _extract_usage(body)

            extracted, extract_error = result_extractor(body)
            if extract_error:
                status = "failure"
                error_summary = redact_secret_like_values(extract_error)
            else:
                status = "success"
                if request_type == "chat":
                    content = extracted
                else:
                    data = extracted

        except RequestsTimeout:
            latency_ms = _safe_latency_ms(time.monotonic() - t0)
            status = "timeout"
            error_summary = "Request timed out"

        except ValueError as exc:
            latency_ms = _safe_latency_ms(time.monotonic() - t0)
            status = "failure"
            error_summary = redact_secret_like_values(f"JSON decode error: {exc}")

        except Exception as exc:  # noqa: BLE001
            latency_ms = _safe_latency_ms(time.monotonic() - t0)
            status = "failure"
            error_summary = redact_secret_like_values(str(exc))

        event = MetricsEvent(
            event_id=event_id,
            call_site_id=call_site_id,
            endpoint=safe_endpoint,
            request_type=request_type,
            status=status,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            api_calls_count_delta=api_calls_count_delta,
            timestamp=timestamp,
            parent_run_id=parent_run_id,
            work_slice_id=work_slice_id,
            agent_name=agent_name,
            job_type=job_type,
            model=model,
            http_status=http_status,
            latency_ms=latency_ms,
            redacted_error_summary=error_summary,
        )

        return ProfessionalizeCallResult(
            ok=(status == "success"),
            event=event,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            api_calls_count_delta=api_calls_count_delta,
            http_status=http_status,
            latency_ms=latency_ms,
            model=model,
            endpoint=safe_endpoint,
            error_summary=error_summary,
            content=content,
            data=data,
        )
