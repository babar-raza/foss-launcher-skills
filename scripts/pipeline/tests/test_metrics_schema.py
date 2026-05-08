"""Tests for metrics_schema.py — Slice 1 of Agent Metrics Integration.

Validates MetricsEvent, MetricsRow, and all helper functions.
No network calls. No posting. No secrets.
"""

import pytest

from commands.ops.metrics_schema import (
    METRICS_ROW_FIELD_COUNT,
    REQUIRED_AGENT_OWNER,
    VALID_EVENT_STATUSES,
    VALID_REQUEST_TYPES,
    VALID_ROW_STATUSES,
    MetricsEvent,
    MetricsRow,
    ValidationResult,
    event_to_dict,
    generate_event_id,
    generate_run_id,
    is_valid_iso8601,
    now_iso8601,
    redact_secret_like_values,
    row_to_dict,
    validate_event,
    validate_row,
    validate_test_row,
)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


def _valid_event(**overrides) -> MetricsEvent:
    defaults = dict(
        event_id="550e8400-e29b-41d4-a716-446655440000",
        call_site_id="CS-001",
        endpoint="/chat/completions",
        request_type="chat",
        status="success",
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        api_calls_count_delta=1,
        timestamp="2026-05-06T12:00:00+00:00",
        parent_run_id="run-001",
        work_slice_id="ws-001",
        agent_name="aspose-org-knowledge-enrichment",
        job_type="knowledge_enrichment",
        model="gpt-oss",
        http_status=200,
        latency_ms=1200,
        redacted_error_summary=None,
    )
    defaults.update(overrides)
    return MetricsEvent(**defaults)


def _valid_row(**overrides) -> MetricsRow:
    defaults = dict(
        timestamp="2026-05-06T12:00:00+00:00",
        agent_name="aspose-org-knowledge-enrichment",
        agent_owner="Babar Raza",
        job_type="knowledge_enrichment",
        run_id="550e8400-e29b-41d4-a716-446655440000",
        status="success",
        product="words",
        platform="python",
        website="aspose.org",
        website_section="Docs",
        item_name="aspose.org / Docs / words / python / knowledge_enrichment",
        items_discovered=10,
        items_failed=1,
        items_succeeded=9,
        run_duration_ms=5000,
        token_usage=1500,
        api_calls_count=3,
    )
    defaults.update(overrides)
    return MetricsRow(**defaults)


# --------------------------------------------------------------------------- #
# MetricsEvent Validation
# --------------------------------------------------------------------------- #


class TestValidateEvent:
    def test_valid_event_passes(self):
        result = validate_event(_valid_event())
        assert result.valid is True
        assert result.errors == []

    def test_negative_prompt_tokens_fails(self):
        result = validate_event(_valid_event(prompt_tokens=-1))
        assert result.valid is False
        assert any("prompt_tokens" in e for e in result.errors)

    def test_negative_completion_tokens_fails(self):
        result = validate_event(_valid_event(completion_tokens=-5))
        assert result.valid is False
        assert any("completion_tokens" in e for e in result.errors)

    def test_negative_total_tokens_fails(self):
        result = validate_event(_valid_event(total_tokens=-1))
        assert result.valid is False
        assert any("total_tokens" in e for e in result.errors)

    def test_negative_api_calls_count_delta_fails(self):
        result = validate_event(_valid_event(api_calls_count_delta=-1))
        assert result.valid is False
        assert any("api_calls_count_delta" in e for e in result.errors)

    def test_invalid_status_fails(self):
        result = validate_event(_valid_event(status="unknown"))
        assert result.valid is False
        assert any("status" in e for e in result.errors)

    def test_invalid_request_type_fails(self):
        result = validate_event(_valid_event(request_type="magic"))
        assert result.valid is False
        assert any("request_type" in e for e in result.errors)

    def test_blank_call_site_id_fails(self):
        result = validate_event(_valid_event(call_site_id=""))
        assert result.valid is False
        assert any("call_site_id" in e for e in result.errors)

    def test_blank_endpoint_fails(self):
        result = validate_event(_valid_event(endpoint=""))
        assert result.valid is False
        assert any("endpoint" in e for e in result.errors)

    def test_endpoint_with_api_key_param_fails(self):
        result = validate_event(
            _valid_event(endpoint="/chat/completions?api_key=sk-abc123def456")
        )
        assert result.valid is False
        assert any("endpoint" in e and "API key" in e for e in result.errors)

    def test_invalid_timestamp_fails(self):
        result = validate_event(_valid_event(timestamp="not-a-date"))
        assert result.valid is False
        assert any("timestamp" in e for e in result.errors)

    def test_negative_latency_fails(self):
        result = validate_event(_valid_event(latency_ms=-100))
        assert result.valid is False
        assert any("latency_ms" in e for e in result.errors)

    def test_none_latency_passes(self):
        result = validate_event(_valid_event(latency_ms=None))
        assert result.valid is True

    def test_zero_tokens_passes(self):
        result = validate_event(
            _valid_event(prompt_tokens=0, completion_tokens=0, total_tokens=0)
        )
        assert result.valid is True

    def test_all_valid_statuses(self):
        for s in VALID_EVENT_STATUSES:
            result = validate_event(_valid_event(status=s))
            assert result.valid is True, f"Status '{s}' should be valid"

    def test_all_valid_request_types(self):
        for rt in VALID_REQUEST_TYPES:
            result = validate_event(_valid_event(request_type=rt))
            assert result.valid is True, f"Request type '{rt}' should be valid"


# --------------------------------------------------------------------------- #
# MetricsRow Validation
# --------------------------------------------------------------------------- #


class TestValidateRow:
    def test_valid_row_passes(self):
        result = validate_row(_valid_row())
        assert result.valid is True
        assert result.errors == []

    def test_row_has_17_fields(self):
        assert METRICS_ROW_FIELD_COUNT == 17

    def test_blank_website_section_fails(self):
        result = validate_row(_valid_row(website_section=""))
        assert result.valid is False
        assert any("website_section" in e for e in result.errors)

    def test_bad_status_fails(self):
        result = validate_row(_valid_row(status="unknown"))
        assert result.valid is False
        assert any("status" in e for e in result.errors)

    def test_negative_items_discovered_fails(self):
        result = validate_row(_valid_row(items_discovered=-1))
        assert result.valid is False
        assert any("items_discovered" in e for e in result.errors)

    def test_negative_token_usage_fails(self):
        result = validate_row(_valid_row(token_usage=-1))
        assert result.valid is False
        assert any("token_usage" in e for e in result.errors)

    def test_negative_api_calls_count_fails(self):
        result = validate_row(_valid_row(api_calls_count=-1))
        assert result.valid is False
        assert any("api_calls_count" in e for e in result.errors)

    def test_agent_owner_not_babar_fails(self):
        result = validate_row(_valid_row(agent_owner="Someone Else"))
        assert result.valid is False
        assert any("agent_owner" in e for e in result.errors)

    def test_items_exceed_discovered_fails(self):
        result = validate_row(
            _valid_row(items_discovered=5, items_succeeded=4, items_failed=3)
        )
        assert result.valid is False
        assert any("items_succeeded + items_failed" in e for e in result.errors)

    def test_blank_agent_name_fails(self):
        result = validate_row(_valid_row(agent_name=""))
        assert result.valid is False
        assert any("agent_name" in e for e in result.errors)

    def test_all_valid_row_statuses(self):
        for s in VALID_ROW_STATUSES:
            result = validate_row(_valid_row(status=s))
            assert result.valid is True, f"Row status '{s}' should be valid"

    def test_negative_run_duration_fails(self):
        result = validate_row(_valid_row(run_duration_ms=-1))
        assert result.valid is False
        assert any("run_duration_ms" in e for e in result.errors)


# --------------------------------------------------------------------------- #
# Test-Mode Row Validation
# --------------------------------------------------------------------------- #


class TestValidateTestRow:
    def test_valid_test_row_passes(self):
        result = validate_test_row(
            _valid_row(job_type="test", item_name="[TEST] validation check")
        )
        assert result.valid is True

    def test_test_row_without_test_prefix_fails(self):
        result = validate_test_row(
            _valid_row(job_type="test", item_name="no prefix here")
        )
        assert result.valid is False
        assert any("[TEST]" in e for e in result.errors)

    def test_test_row_wrong_job_type_fails(self):
        result = validate_test_row(
            _valid_row(job_type="knowledge_enrichment", item_name="[TEST] check")
        )
        assert result.valid is False
        assert any("job_type" in e for e in result.errors)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


class TestHelpers:
    def test_is_valid_iso8601_good(self):
        assert is_valid_iso8601("2026-05-06T12:00:00+00:00") is True
        assert is_valid_iso8601("2026-05-06T12:00:00") is True
        assert is_valid_iso8601("2026-05-06T12:00:00.123456+00:00") is True

    def test_is_valid_iso8601_bad(self):
        assert is_valid_iso8601("not-a-date") is False
        assert is_valid_iso8601("") is False

    def test_redact_secret_like_values(self):
        assert "[REDACTED]" in redact_secret_like_values("sk-abc123def456ghi")
        assert "[REDACTED]" in redact_secret_like_values("ghp_abcdefghij1234")
        assert "[REDACTED]" in redact_secret_like_values("Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6")  # SECRETS_TEST_FIXTURE
        assert "[REDACTED]" in redact_secret_like_values(
            "/v1/chat?api_key=mysecretvalue123"  # SECRETS_TEST_FIXTURE
        )

    def test_redact_clean_value_unchanged(self):
        clean = "/chat/completions"
        assert redact_secret_like_values(clean) == clean

    def test_generate_event_id_is_uuid(self):
        eid = generate_event_id()
        assert len(eid) == 36 and eid.count("-") == 4

    def test_generate_run_id_is_uuid(self):
        rid = generate_run_id()
        assert len(rid) == 36 and rid.count("-") == 4

    def test_now_iso8601_is_parseable(self):
        ts = now_iso8601()
        assert is_valid_iso8601(ts) is True

    def test_event_to_dict_roundtrip(self):
        event = _valid_event()
        d = event_to_dict(event)
        assert isinstance(d, dict)
        assert d["call_site_id"] == "CS-001"
        assert d["prompt_tokens"] == 100

    def test_row_to_dict_roundtrip(self):
        row = _valid_row()
        d = row_to_dict(row)
        assert isinstance(d, dict)
        assert len(d) == 17
        assert d["agent_owner"] == "Babar Raza"
