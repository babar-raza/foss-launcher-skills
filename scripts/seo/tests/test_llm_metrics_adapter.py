"""Tests for llm_metrics_adapter.py (Finding #59, SEO-LLM-METRICS-UNIFY)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[2]
_PIPELINE = _SCRIPTS / "pipeline"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
if str(_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_PIPELINE))

import seo.llm_metrics_adapter as llm_metrics_adapter  # noqa: E402
from commands.ops.metrics_event_ledger import MetricsEventLedger  # noqa: E402


def _fresh_ledger(tmp_path, run_id="test-run"):
    return MetricsEventLedger(run_id, root_dir=tmp_path / "events")


# ---------------------------------------------------------------------------
# record_gemini_call -- real writes via an injected, isolated ledger
# ---------------------------------------------------------------------------

def test_record_gemini_call_writes_a_real_event(tmp_path):
    ledger = _fresh_ledger(tmp_path)
    ok = llm_metrics_adapter.record_gemini_call(
        "CS-010", "get_keywords", "success",
        model="gemini-flash-lite-latest", prompt_tokens=12, completion_tokens=34,
        latency_ms=567, ledger=ledger,
    )
    assert ok is True
    events = ledger.read_events()
    assert len(events) == 1
    ev = events[0]
    assert ev.call_site_id == "CS-010"
    assert ev.consumer_id == "get_keywords"
    assert ev.provider == "gemini-direct"
    assert ev.status == "success"
    assert ev.request_type == "seo"
    assert ev.prompt_tokens == 12
    assert ev.completion_tokens == 34
    assert ev.total_tokens == 46
    assert ev.model == "gemini-flash-lite-latest"
    assert ev.latency_ms == 567


def test_record_gemini_call_defaults_tokens_to_zero(tmp_path):
    ledger = _fresh_ledger(tmp_path)
    llm_metrics_adapter.record_gemini_call("CS-010", "get_keywords", "failure", ledger=ledger)
    ev = ledger.read_events()[0]
    assert ev.prompt_tokens == 0
    assert ev.completion_tokens == 0
    assert ev.total_tokens == 0


def test_record_gemini_call_never_raises_on_negative_tokens(tmp_path):
    """A defensive floor at 0 -- MetricsEvent validation requires
    non-negative integers; this function must never hand it something that
    would fail validation and raise MetricsEventLedgerError."""
    ledger = _fresh_ledger(tmp_path)
    ok = llm_metrics_adapter.record_gemini_call(
        "CS-010", "get_keywords", "success", prompt_tokens=-5, completion_tokens=-1, ledger=ledger,
    )
    assert ok is True
    ev = ledger.read_events()[0]
    assert ev.prompt_tokens == 0
    assert ev.completion_tokens == 0


def test_record_gemini_call_redacts_secret_like_error_text(tmp_path):
    ledger = _fresh_ledger(tmp_path)
    llm_metrics_adapter.record_gemini_call(
        "CS-010", "get_keywords", "failure",
        redacted_error_summary="failed with AIzaSyABCDEFGHIJKLMNOPQRSTUVWXYZ123456",
        ledger=ledger,
    )
    ev = ledger.read_events()[0]
    assert "AIzaSy" not in ev.redacted_error_summary
    assert "[REDACTED]" in ev.redacted_error_summary


def test_record_gemini_call_truncates_long_error_text(tmp_path):
    ledger = _fresh_ledger(tmp_path)
    llm_metrics_adapter.record_gemini_call(
        "CS-010", "get_keywords", "failure",
        redacted_error_summary="x" * 500,
        ledger=ledger,
    )
    ev = ledger.read_events()[0]
    assert len(ev.redacted_error_summary) <= 200


def test_record_gemini_call_none_error_summary_stays_none(tmp_path):
    ledger = _fresh_ledger(tmp_path)
    llm_metrics_adapter.record_gemini_call("CS-010", "get_keywords", "success", ledger=ledger)
    ev = ledger.read_events()[0]
    assert ev.redacted_error_summary is None


@pytest.mark.parametrize("status", ["success", "retry", "failure", "timeout"])
def test_record_gemini_call_accepts_every_valid_status(tmp_path, status):
    ledger = _fresh_ledger(tmp_path)
    ok = llm_metrics_adapter.record_gemini_call("CS-010", "get_keywords", status, ledger=ledger)
    assert ok is True


def test_record_gemini_call_returns_false_and_never_raises_on_invalid_status(tmp_path):
    """An invalid status would fail MetricsEvent validation and raise
    MetricsEventLedgerError inside record_event() -- this function's own
    contract is to swallow that, never propagate it (metrics must never
    block keyword generation)."""
    ledger = _fresh_ledger(tmp_path)
    ok = llm_metrics_adapter.record_gemini_call("CS-010", "get_keywords", "not-a-real-status", ledger=ledger)
    assert ok is False
    assert ledger.read_events() == []


def test_record_gemini_call_never_raises_when_ledger_itself_is_broken(tmp_path):
    class _BrokenLedger:
        def record_event(self, event):
            raise RuntimeError("disk full")

    ok = llm_metrics_adapter.record_gemini_call("CS-010", "get_keywords", "success", ledger=_BrokenLedger())
    assert ok is False


def test_record_gemini_call_uses_a_shared_default_run_id_across_calls(tmp_path, monkeypatch):
    """Without an explicit ledger/run_id, repeated calls within one process
    must land in the SAME file (one run_id per process) -- not scatter each
    call into its own file."""
    monkeypatch.setattr(llm_metrics_adapter, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(llm_metrics_adapter, "_PROCESS_RUN_ID", None)
    llm_metrics_adapter.record_gemini_call("CS-010", "get_keywords", "success")
    llm_metrics_adapter.record_gemini_call("CS-010", "get_keywords", "success")
    events_dir = tmp_path / "reports" / "metrics" / "events"
    jsonl_files = list(events_dir.glob("*.jsonl"))
    assert len(jsonl_files) == 1
    lines = jsonl_files[0].read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2


# ---------------------------------------------------------------------------
# extract_gemini_token_usage
# ---------------------------------------------------------------------------

class _FakeUsage:
    def __init__(self, prompt=10, candidates=20):
        self.prompt_token_count = prompt
        self.candidates_token_count = candidates


class _FakeResponseWithUsage:
    def __init__(self, usage):
        self.usage_metadata = usage


def test_extract_gemini_token_usage_reads_real_proto_shape():
    response = _FakeResponseWithUsage(_FakeUsage(prompt=42, candidates=7))
    prompt_tokens, completion_tokens = llm_metrics_adapter.extract_gemini_token_usage(response)
    assert prompt_tokens == 42
    assert completion_tokens == 7


def test_extract_gemini_token_usage_returns_zeros_when_usage_metadata_is_none():
    response = _FakeResponseWithUsage(None)
    assert llm_metrics_adapter.extract_gemini_token_usage(response) == (0, 0)


def test_extract_gemini_token_usage_returns_zeros_when_attribute_missing():
    """The exact shape scripts/seo/tests/test_review_keywords.py's own
    _FakeResponse fixtures use (a class with only .text) -- must never raise."""
    class _BareResponse:
        text = "kw"

    assert llm_metrics_adapter.extract_gemini_token_usage(_BareResponse()) == (0, 0)


def test_extract_gemini_token_usage_returns_zeros_on_none_field_values():
    response = _FakeResponseWithUsage(_FakeUsage(prompt=None, candidates=None))
    assert llm_metrics_adapter.extract_gemini_token_usage(response) == (0, 0)
