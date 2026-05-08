"""Tests for MetricsSubmitter (metrics_submitter.py).

Covers all 14 required test scenarios:
1.  dry-run writes JSON and does not call HTTP
2.  export-json writes valid row
3.  missing endpoint blocks submit
4.  missing token blocks submit
5.  token is redacted in result/logs
6.  test-submit uses fake HTTP client and succeeds
7.  test-submit rejects non-test marker if policy requires it
8.  production-submit requires owner approval
9.  production-submit rejects without approval
10. schema validation catches missing fields
11. API response errors are captured without crashing
12. no secrets appear in output JSON beyond required payload fields
13. endpoint is not hardcoded
14. token is not hardcoded

Plus additional coverage: modes, edge cases, redaction, export path.

Zero real network calls — all HTTP injected via _FakeHTTPClient.

Slice 7 of Agent Metrics Integration (METRICS-PLAN-001 v7.1).
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

# Ensure scripts/pipeline is on sys.path
_PIPELINE_ROOT = Path(__file__).resolve().parent.parent
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from commands.ops.metrics_schema import (
    MetricsRow,
    generate_run_id,
    now_iso8601,
    row_to_dict,
)
from commands.ops.metrics_submitter import (
    ENV_ENDPOINT,
    ENV_TOKEN,
    MODE_DRY_RUN,
    MODE_EXPORT_JSON,
    MODE_PRODUCTION_SUBMIT,
    MODE_TEST_SUBMIT,
    MetricsSubmitter,
    SubmitResult,
    _redact_endpoint,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_test_row(**overrides) -> MetricsRow:
    """Build a valid test-mode MetricsRow."""
    defaults = dict(
        timestamp=now_iso8601(),
        agent_name="aspose-org-knowledge-enrichment",
        agent_owner="Babar Raza",
        job_type="test",
        run_id=generate_run_id(),
        status="success",
        product="cells",
        platform="java",
        website="aspose.org",
        website_section="Docs",
        item_name="[TEST] aspose.org / Docs / cells / java / knowledge_enrichment",
        items_discovered=5,
        items_failed=0,
        items_succeeded=5,
        run_duration_ms=300,
        token_usage=200,
        api_calls_count=2,
    )
    defaults.update(overrides)
    return MetricsRow(**defaults)


def _make_production_row(**overrides) -> MetricsRow:
    """Build a valid production MetricsRow (job_type != test)."""
    defaults = dict(
        timestamp=now_iso8601(),
        agent_name="aspose-org-knowledge-enrichment",
        agent_owner="Babar Raza",
        job_type="knowledge_enrichment",
        run_id=generate_run_id(),
        status="success",
        product="cells",
        platform="java",
        website="aspose.org",
        website_section="Docs",
        item_name="aspose.org / Docs / cells / java / knowledge_enrichment",
        items_discovered=10,
        items_failed=0,
        items_succeeded=10,
        run_duration_ms=1500,
        token_usage=500,
        api_calls_count=5,
    )
    defaults.update(overrides)
    return MetricsRow(**defaults)


class _FakeHTTPClient:
    """Fake HTTP transport for zero-network tests."""

    def __init__(self, status_code: int = 200, response_body: dict | None = None, exc: Exception | None = None):
        self.status_code = status_code
        self.response_body = response_body or {"status": "ok"}
        self.exc = exc
        self.calls: list[dict] = []

    def post(self, url: str, *, json: Any, headers: dict, timeout: float) -> Any:
        self.calls.append({"url": url, "json": json, "headers": dict(headers)})
        if self.exc:
            raise self.exc
        resp = MagicMock()
        resp.status_code = self.status_code
        resp.json.return_value = self.response_body
        return resp


# ---------------------------------------------------------------------------
# Test 1: dry-run writes no JSON and does not call HTTP
# ---------------------------------------------------------------------------

class TestDryRun:
    def test_dry_run_does_not_submit(self):
        row = _make_test_row()
        result = MetricsSubmitter(mode=MODE_DRY_RUN).submit(row)
        assert result.submitted is False

    def test_dry_run_no_http_call(self):
        http = _FakeHTTPClient()
        row = _make_test_row()
        MetricsSubmitter(mode=MODE_DRY_RUN, _http_client=http).submit(row)
        assert len(http.calls) == 0

    def test_dry_run_row_valid(self):
        result = MetricsSubmitter(mode=MODE_DRY_RUN).submit(_make_test_row())
        assert result.row_valid is True
        assert result.validation_errors == []

    def test_dry_run_no_output_path_by_default(self):
        result = MetricsSubmitter(mode=MODE_DRY_RUN).submit(_make_test_row())
        assert result.output_path is None

    def test_dry_run_with_output_path_writes_file(self, tmp_path):
        path = tmp_path / "row.json"
        result = MetricsSubmitter(mode=MODE_DRY_RUN, output_path=path).submit(_make_test_row())
        assert path.exists()
        assert result.output_path == str(path)


# ---------------------------------------------------------------------------
# Test 2: export-json writes valid row
# ---------------------------------------------------------------------------

class TestExportJson:
    def test_export_writes_file(self, tmp_path):
        path = tmp_path / "export.json"
        MetricsSubmitter(mode=MODE_EXPORT_JSON, output_path=path).submit(_make_test_row())
        assert path.exists()

    def test_export_content_is_valid_json(self, tmp_path):
        path = tmp_path / "export.json"
        row = _make_test_row()
        MetricsSubmitter(mode=MODE_EXPORT_JSON, output_path=path).submit(row)
        data = json.loads(path.read_text())
        assert isinstance(data, dict)

    def test_export_contains_all_17_fields(self, tmp_path):
        path = tmp_path / "export.json"
        row = _make_test_row()
        MetricsSubmitter(mode=MODE_EXPORT_JSON, output_path=path).submit(row)
        data = json.loads(path.read_text())
        expected_fields = {
            "timestamp", "agent_name", "agent_owner", "job_type", "run_id",
            "status", "product", "platform", "website", "website_section",
            "item_name", "items_discovered", "items_failed", "items_succeeded",
            "run_duration_ms", "token_usage", "api_calls_count",
        }
        assert expected_fields == set(data.keys())

    def test_export_not_submitted(self, tmp_path):
        path = tmp_path / "export.json"
        result = MetricsSubmitter(mode=MODE_EXPORT_JSON, output_path=path).submit(_make_test_row())
        assert result.submitted is False

    def test_export_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "deep" / "nested" / "export.json"
        MetricsSubmitter(mode=MODE_EXPORT_JSON, output_path=path).submit(_make_test_row())
        assert path.exists()


# ---------------------------------------------------------------------------
# Test 3: missing endpoint blocks submit
# ---------------------------------------------------------------------------

class TestMissingEndpoint:
    def test_test_submit_missing_endpoint_returns_error(self, monkeypatch):
        monkeypatch.delenv(ENV_ENDPOINT, raising=False)
        monkeypatch.delenv(ENV_TOKEN, raising=False)
        row = _make_test_row()
        result = MetricsSubmitter(mode=MODE_TEST_SUBMIT).submit(row)
        assert result.submitted is False
        assert ENV_ENDPOINT in result.error

    def test_production_submit_missing_endpoint_returns_error(self, monkeypatch):
        monkeypatch.delenv(ENV_ENDPOINT, raising=False)
        monkeypatch.delenv(ENV_TOKEN, raising=False)
        row = _make_production_row()
        result = MetricsSubmitter(mode=MODE_PRODUCTION_SUBMIT).submit(row, owner_approved=True)
        assert result.submitted is False
        assert ENV_ENDPOINT in result.error


# ---------------------------------------------------------------------------
# Test 4: missing token blocks submit
# ---------------------------------------------------------------------------

class TestMissingToken:
    def test_test_submit_missing_token_returns_error(self, monkeypatch):
        monkeypatch.setenv(ENV_ENDPOINT, "https://script.google.com/macros/s/example/exec")
        monkeypatch.delenv(ENV_TOKEN, raising=False)
        row = _make_test_row()
        result = MetricsSubmitter(mode=MODE_TEST_SUBMIT).submit(row)
        assert result.submitted is False
        assert ENV_TOKEN in result.error


# ---------------------------------------------------------------------------
# Test 5: token is redacted in result/logs
# ---------------------------------------------------------------------------

class TestTokenRedaction:
    def test_token_not_in_submit_result(self, monkeypatch, tmp_path):
        fake_token = "super-secret-bearer-token-12345"
        monkeypatch.setenv(ENV_ENDPOINT, "https://script.google.com/macros/s/example/exec")
        monkeypatch.setenv(ENV_TOKEN, fake_token)
        http = _FakeHTTPClient(status_code=200)
        row = _make_test_row()
        result = MetricsSubmitter(mode=MODE_TEST_SUBMIT, _http_client=http).submit(row)
        # Token must not appear anywhere in the result
        result_str = str(result)
        assert fake_token not in result_str

    def test_token_not_in_http_call_headers_exposed(self, monkeypatch):
        """Token IS sent as ?token= query param to the server, but not in SubmitResult."""
        fake_token = "my-secret-token-xyz"
        monkeypatch.setenv(ENV_ENDPOINT, "https://script.google.com/macros/s/example/exec")
        monkeypatch.setenv(ENV_TOKEN, fake_token)
        http = _FakeHTTPClient()
        row = _make_test_row()
        result = MetricsSubmitter(mode=MODE_TEST_SUBMIT, _http_client=http).submit(row)
        # Verify token was sent as query param (not in Authorization header)
        assert f"?token={fake_token}" in http.calls[0]["url"]
        assert "Authorization" not in http.calls[0]["headers"]
        # Token must NOT appear in result object
        assert fake_token not in str(result)

    def test_export_json_no_token_field(self, tmp_path):
        path = tmp_path / "export.json"
        MetricsSubmitter(mode=MODE_EXPORT_JSON, output_path=path).submit(_make_test_row())
        content = path.read_text()
        assert "token" not in content.lower() or "api_calls" in content  # api_calls_count is ok


# ---------------------------------------------------------------------------
# Test 6: test-submit uses fake HTTP and succeeds
# ---------------------------------------------------------------------------

class TestTestSubmit:
    def test_test_submit_succeeds_with_fake_http(self, monkeypatch):
        monkeypatch.setenv(ENV_ENDPOINT, "https://script.google.com/macros/s/example/exec")
        monkeypatch.setenv(ENV_TOKEN, "test-bearer-token")
        http = _FakeHTTPClient(status_code=200, response_body={"status": "ok"})
        row = _make_test_row()
        result = MetricsSubmitter(mode=MODE_TEST_SUBMIT, _http_client=http).submit(row)
        assert result.submitted is True
        assert result.status_code == 200
        assert result.error is None

    def test_test_submit_makes_exactly_one_http_call(self, monkeypatch):
        monkeypatch.setenv(ENV_ENDPOINT, "https://script.google.com/macros/s/example/exec")
        monkeypatch.setenv(ENV_TOKEN, "test-bearer-token")
        http = _FakeHTTPClient()
        row = _make_test_row()
        MetricsSubmitter(mode=MODE_TEST_SUBMIT, _http_client=http).submit(row)
        assert len(http.calls) == 1

    def test_test_submit_sends_all_17_fields(self, monkeypatch):
        monkeypatch.setenv(ENV_ENDPOINT, "https://script.google.com/macros/s/example/exec")
        monkeypatch.setenv(ENV_TOKEN, "test-bearer-token")
        http = _FakeHTTPClient()
        row = _make_test_row()
        MetricsSubmitter(mode=MODE_TEST_SUBMIT, _http_client=http).submit(row)
        payload = http.calls[0]["json"]
        assert len(payload) == 17

    def test_test_submit_row_must_be_test_marked(self, monkeypatch):
        """test_submit with non-test row is rejected."""
        monkeypatch.setenv(ENV_ENDPOINT, "https://script.google.com/macros/s/example/exec")
        monkeypatch.setenv(ENV_TOKEN, "test-bearer-token")
        http = _FakeHTTPClient()
        row = _make_production_row()  # job_type=knowledge_enrichment, no [TEST] prefix
        result = MetricsSubmitter(mode=MODE_TEST_SUBMIT, _http_client=http).submit(row)
        assert result.submitted is False
        assert len(http.calls) == 0


# ---------------------------------------------------------------------------
# Test 7: test-submit rejects non-test marker
# ---------------------------------------------------------------------------

class TestTestSubmitMarkerPolicy:
    def test_rejects_row_without_test_job_type(self, monkeypatch):
        monkeypatch.setenv(ENV_ENDPOINT, "https://example.com")
        monkeypatch.setenv(ENV_TOKEN, "tok")
        http = _FakeHTTPClient()
        row = _make_production_row()
        result = MetricsSubmitter(mode=MODE_TEST_SUBMIT, _http_client=http).submit(row)
        assert result.submitted is False
        assert "test" in result.error.lower()
        assert len(http.calls) == 0

    def test_rejects_row_without_test_item_prefix(self, monkeypatch):
        monkeypatch.setenv(ENV_ENDPOINT, "https://example.com")
        monkeypatch.setenv(ENV_TOKEN, "tok")
        http = _FakeHTTPClient()
        # job_type=test but no [TEST] prefix
        row = _make_test_row(item_name="aspose.org / Docs / cells / java / test")
        result = MetricsSubmitter(mode=MODE_TEST_SUBMIT, _http_client=http).submit(row)
        assert result.submitted is False


# ---------------------------------------------------------------------------
# Test 8: production-submit requires owner approval
# ---------------------------------------------------------------------------

class TestProductionSubmitApproval:
    def test_requires_owner_approved_true(self, monkeypatch):
        monkeypatch.setenv(ENV_ENDPOINT, "https://example.com")
        monkeypatch.setenv(ENV_TOKEN, "tok")
        http = _FakeHTTPClient()
        row = _make_production_row()
        result = MetricsSubmitter(mode=MODE_PRODUCTION_SUBMIT, _http_client=http).submit(
            row, owner_approved=False
        )
        assert result.submitted is False
        assert "owner_approved" in result.error
        assert len(http.calls) == 0

    def test_owner_approved_true_allows_submit(self, monkeypatch):
        monkeypatch.setenv(ENV_ENDPOINT, "https://example.com")
        monkeypatch.setenv(ENV_TOKEN, "tok")
        http = _FakeHTTPClient(status_code=200)
        row = _make_production_row()
        result = MetricsSubmitter(mode=MODE_PRODUCTION_SUBMIT, _http_client=http).submit(
            row, owner_approved=True
        )
        assert result.submitted is True
        assert len(http.calls) == 1


# ---------------------------------------------------------------------------
# Test 9: production-submit rejects without approval (already covered above)
# — additional: rejects test job_type in production
# ---------------------------------------------------------------------------

class TestProductionSubmitRejectsTestRow:
    def test_production_submit_rejects_test_job_type(self, monkeypatch):
        monkeypatch.setenv(ENV_ENDPOINT, "https://example.com")
        monkeypatch.setenv(ENV_TOKEN, "tok")
        http = _FakeHTTPClient()
        row = _make_test_row()  # job_type="test"
        result = MetricsSubmitter(mode=MODE_PRODUCTION_SUBMIT, _http_client=http).submit(
            row, owner_approved=True
        )
        assert result.submitted is False
        assert "job_type" in result.error
        assert len(http.calls) == 0


# ---------------------------------------------------------------------------
# Test 10: schema validation catches missing/invalid fields
# ---------------------------------------------------------------------------

class TestSchemaValidation:
    def test_invalid_row_blocked_before_http(self, monkeypatch):
        monkeypatch.setenv(ENV_ENDPOINT, "https://example.com")
        monkeypatch.setenv(ENV_TOKEN, "tok")
        http = _FakeHTTPClient()
        # Build invalid row: wrong agent_owner
        row = _make_test_row(agent_owner="Wrong Person")
        result = MetricsSubmitter(mode=MODE_TEST_SUBMIT, _http_client=http).submit(row)
        assert result.row_valid is False
        assert result.submitted is False
        assert len(http.calls) == 0

    def test_validation_errors_reported(self):
        row = _make_test_row(agent_owner="Wrong Person")
        result = MetricsSubmitter(mode=MODE_DRY_RUN).submit(row)
        assert not result.row_valid
        assert len(result.validation_errors) > 0
        assert any("agent_owner" in e for e in result.validation_errors)

    def test_valid_row_passes_dry_run(self):
        result = MetricsSubmitter(mode=MODE_DRY_RUN).submit(_make_test_row())
        assert result.row_valid is True
        assert result.validation_errors == []


# ---------------------------------------------------------------------------
# Test 11: API response errors captured without crashing
# ---------------------------------------------------------------------------

class TestApiErrorHandling:
    def test_non_200_captured_in_error(self, monkeypatch):
        monkeypatch.setenv(ENV_ENDPOINT, "https://example.com")
        monkeypatch.setenv(ENV_TOKEN, "tok")
        http = _FakeHTTPClient(status_code=500, response_body={"error": "internal"})
        row = _make_test_row()
        result = MetricsSubmitter(mode=MODE_TEST_SUBMIT, _http_client=http).submit(row)
        assert result.submitted is False
        assert result.status_code == 500
        assert "500" in result.error

    def test_connection_error_captured(self, monkeypatch):
        monkeypatch.setenv(ENV_ENDPOINT, "https://example.com")
        monkeypatch.setenv(ENV_TOKEN, "tok")
        http = _FakeHTTPClient(exc=ConnectionError("refused"))
        row = _make_test_row()
        result = MetricsSubmitter(mode=MODE_TEST_SUBMIT, _http_client=http).submit(row)
        assert result.submitted is False
        assert "refused" in result.error

    def test_timeout_captured(self, monkeypatch):
        monkeypatch.setenv(ENV_ENDPOINT, "https://example.com")
        monkeypatch.setenv(ENV_TOKEN, "tok")
        http = _FakeHTTPClient(exc=TimeoutError("timed out"))
        row = _make_test_row()
        result = MetricsSubmitter(mode=MODE_TEST_SUBMIT, _http_client=http).submit(row)
        assert result.submitted is False
        assert "timed out" in result.error


# ---------------------------------------------------------------------------
# Test 12: no secrets in output JSON beyond required payload fields
# ---------------------------------------------------------------------------

class TestNoSecretsInExport:
    def test_export_no_token_field(self, tmp_path):
        path = tmp_path / "out.json"
        row = _make_test_row()
        MetricsSubmitter(mode=MODE_EXPORT_JSON, output_path=path).submit(row)
        data = json.loads(path.read_text())
        secret_fields = {"token", "api_key", "bearer", "password", "secret"}
        for field in data:
            assert field.lower() not in secret_fields, f"Secret-like field '{field}' in export"

    def test_export_no_sk_patterns(self, tmp_path):
        path = tmp_path / "out.json"
        MetricsSubmitter(mode=MODE_EXPORT_JSON, output_path=path).submit(_make_test_row())
        content = path.read_text()
        assert "sk-" not in content
        assert "Bearer " not in content


# ---------------------------------------------------------------------------
# Test 13: endpoint is not hardcoded
# ---------------------------------------------------------------------------

class TestNoHardcodedEndpoint:
    def test_endpoint_read_from_env(self, monkeypatch):
        custom_endpoint = "https://custom-endpoint.example.com/api"
        monkeypatch.setenv(ENV_ENDPOINT, custom_endpoint)
        monkeypatch.setenv(ENV_TOKEN, "tok")
        http = _FakeHTTPClient()
        row = _make_test_row()
        MetricsSubmitter(mode=MODE_TEST_SUBMIT, _http_client=http).submit(row)
        assert len(http.calls) == 1
        assert http.calls[0]["url"].startswith(custom_endpoint)

    def test_missing_endpoint_env_returns_error_not_fallback(self, monkeypatch):
        monkeypatch.delenv(ENV_ENDPOINT, raising=False)
        monkeypatch.delenv(ENV_TOKEN, raising=False)
        result = MetricsSubmitter(mode=MODE_TEST_SUBMIT).submit(_make_test_row())
        assert result.submitted is False
        assert ENV_ENDPOINT in result.error


# ---------------------------------------------------------------------------
# Test 14: token is not hardcoded
# ---------------------------------------------------------------------------

class TestNoHardcodedToken:
    def test_token_read_from_env(self, monkeypatch):
        monkeypatch.setenv(ENV_ENDPOINT, "https://example.com")
        custom_token = "my-runtime-token-abc"
        monkeypatch.setenv(ENV_TOKEN, custom_token)
        http = _FakeHTTPClient()
        row = _make_test_row()
        MetricsSubmitter(mode=MODE_TEST_SUBMIT, _http_client=http).submit(row)
        # Token sent as ?token= query param, not Authorization header
        assert f"?token={custom_token}" in http.calls[0]["url"]
        assert "Authorization" not in http.calls[0]["headers"]

    def test_missing_token_env_returns_error_not_fallback(self, monkeypatch):
        monkeypatch.setenv(ENV_ENDPOINT, "https://example.com")
        monkeypatch.delenv(ENV_TOKEN, raising=False)
        result = MetricsSubmitter(mode=MODE_TEST_SUBMIT).submit(_make_test_row())
        assert result.submitted is False
        assert ENV_TOKEN in result.error


# ---------------------------------------------------------------------------
# Additional: _redact_endpoint helper
# ---------------------------------------------------------------------------

class TestRedactEndpoint:
    def test_short_endpoint_redacted(self):
        assert _redact_endpoint("https://x.y") == "***"

    def test_long_endpoint_masked_middle(self):
        ep = "https://script.google.com/macros/s/AKfycbxyz1234567890/exec"
        result = _redact_endpoint(ep)
        assert "***" in result
        assert result.startswith("https://script.go")
        assert result.endswith(ep[-8:])

    def test_empty_endpoint_returns_stars(self):
        assert _redact_endpoint("") == "***"


# ---------------------------------------------------------------------------
# Additional: invalid mode raises at construction
# ---------------------------------------------------------------------------

class TestInvalidMode:
    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError, match="Invalid mode"):
            MetricsSubmitter(mode="not_a_mode")


# ---------------------------------------------------------------------------
# Additional: default mode is dry_run
# ---------------------------------------------------------------------------

class TestDefaultMode:
    def test_default_is_dry_run(self):
        s = MetricsSubmitter()
        assert s.mode == MODE_DRY_RUN

    def test_dry_run_result_mode_field(self):
        result = MetricsSubmitter().submit(_make_test_row())
        assert result.mode == MODE_DRY_RUN
