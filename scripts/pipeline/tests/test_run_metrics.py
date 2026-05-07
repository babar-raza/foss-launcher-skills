"""Tests for RunMetrics context-manager (Slice 6).

Covers all 50 required scenarios:
  - Import safety (no file writes on import)
  - Context-manager protocol (__enter__, __exit__, exception propagation)
  - record_event / record_events (single, batch, all-or-nothing, closed guard)
  - to_row (aggregation, token/api counts, status derivation, validation)
  - agent_owner defaults
  - item_name explicit vs derived
  - run_duration_ms
  - Error handling (invalid events, corrupt ledger, row validation failure)
  - Safety (no forbidden imports, no secrets, no posting)
  - Event acceptance (CS-001, CS-004, parent_run_id)
  - Lifecycle (close idempotent, to_row after close, deterministic calls)
  - No required env vars (no AGENT_METRICS_ENDPOINT/TOKEN)

Zero real network calls. All ledger writes go to pytest tmp_path.

Slice 6 of Agent Metrics Integration (METRICS-PLAN-001 v7.3).
"""
from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

import pytest

_PIPELINE_ROOT = Path(__file__).resolve().parent.parent
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from commands.ops.metrics_schema import (
    MetricsEvent,
    MetricsRow,
    generate_event_id,
    generate_run_id,
    now_iso8601,
    validate_row,
    REQUIRED_AGENT_OWNER,
)
from commands.ops.metrics_event_ledger import MetricsEventLedger, validate_event_file
from commands.ops.run_metrics import RunMetrics, RunMetricsError, _derive_status, _build_item_name


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ENDPOINT_CHAT = "https://llm.professionalize.com/v1/chat/completions"
_ENDPOINT_EMBED = "https://llm.professionalize.com/v1/embeddings"


def _event(
    call_site_id: str = "CS-001",
    total_tokens: int = 100,
    api_calls_count_delta: int = 1,
    request_type: str = "chat",
    status: str = "success",
    endpoint: str = _ENDPOINT_CHAT,
    parent_run_id: str | None = None,
    work_slice_id: str | None = None,
) -> MetricsEvent:
    return MetricsEvent(
        event_id=generate_event_id(),
        call_site_id=call_site_id,
        endpoint=endpoint,
        request_type=request_type,
        status=status,
        prompt_tokens=total_tokens // 2,
        completion_tokens=total_tokens - total_tokens // 2,
        total_tokens=total_tokens,
        api_calls_count_delta=api_calls_count_delta,
        timestamp=now_iso8601(),
        parent_run_id=parent_run_id,
        work_slice_id=work_slice_id,
    )


def _invalid_event() -> MetricsEvent:
    """Returns an event that fails validate_event() — blank call_site_id."""
    return MetricsEvent(
        event_id=generate_event_id(),
        call_site_id="",  # invalid
        endpoint=_ENDPOINT_CHAT,
        request_type="chat",
        status="success",
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
        api_calls_count_delta=1,
        timestamp=now_iso8601(),
    )


def _make_run_metrics(tmp_path: Path, **kwargs) -> RunMetrics:
    defaults = dict(
        run_id=generate_run_id(),
        agent_name="aspose-org-knowledge-enrichment",
        job_type="knowledge_enrichment",
        product="cells",
        platform="java",
        website="aspose.org",
        website_section="Docs",
        ledger_root=tmp_path,
    )
    defaults.update(kwargs)
    return RunMetrics(**defaults)


# ---------------------------------------------------------------------------
# TC-S6-R001–R004: Import safety
# ---------------------------------------------------------------------------

class TestRunMetricsImport:
    def test_import_produces_no_file_writes(self, tmp_path):
        """Importing the module must not create any files."""
        before = set(tmp_path.iterdir())
        import commands.ops.run_metrics  # noqa: F401
        assert set(tmp_path.iterdir()) == before

    def test_run_metrics_error_importable(self):
        assert RunMetricsError is not None

    def test_run_metrics_class_importable(self):
        assert RunMetrics is not None

    def test_run_metrics_no_files_on_construction(self, tmp_path):
        """Constructing RunMetrics must not write any files."""
        rm = _make_run_metrics(tmp_path)
        assert not (tmp_path / f"{rm.run_id}.jsonl").exists()


# ---------------------------------------------------------------------------
# TC-S6-R005–R011: Context manager
# ---------------------------------------------------------------------------

class TestRunMetricsContextManager:
    def test_used_as_context_manager(self, tmp_path):
        with _make_run_metrics(tmp_path) as rm:
            assert isinstance(rm, RunMetrics)

    def test_enter_returns_self(self, tmp_path):
        rm = _make_run_metrics(tmp_path)
        result = rm.__enter__()
        rm.close()
        assert result is rm

    def test_exit_closes_owned_ledger(self, tmp_path):
        rm = _make_run_metrics(tmp_path)
        with rm:
            rm.record_event(_event())
        # After __exit__, owned ledger should be closed; record_event should fail.
        with pytest.raises(RunMetricsError):
            rm.record_event(_event())

    def test_exit_does_not_suppress_exceptions(self, tmp_path):
        with pytest.raises(ValueError, match="sentinel"):
            with _make_run_metrics(tmp_path) as rm:
                rm.record_event(_event())
                raise ValueError("sentinel")

    def test_enter_starts_wall_clock_timer(self, tmp_path):
        rm = _make_run_metrics(tmp_path)
        assert rm.run_duration_ms == 0  # Not entered yet
        with rm:
            assert rm.run_duration_ms >= 0

    def test_exception_still_flushes_events(self, tmp_path):
        """Events recorded before an exception are still persisted."""
        run_id = generate_run_id()
        rm = RunMetrics(
            run_id=run_id,
            agent_name="aspose-org-knowledge-enrichment",
            job_type="knowledge_enrichment",
            product="cells",
            platform="java",
            website="aspose.org",
            website_section="Docs",
            ledger_root=tmp_path,
        )
        try:
            with rm:
                rm.record_event(_event())
                raise RuntimeError("crash")
        except RuntimeError:
            pass
        # Events should be on disk
        jsonl = tmp_path / f"{run_id}.jsonl"
        assert jsonl.exists()
        lines = [l for l in jsonl.read_text().splitlines() if l.strip()]
        assert len(lines) == 1

    def test_close_is_idempotent(self, tmp_path):
        rm = _make_run_metrics(tmp_path)
        rm.record_event(_event())
        rm.close()
        rm.close()  # Must not raise


# ---------------------------------------------------------------------------
# TC-S6-R012–R019: record_event / record_events
# ---------------------------------------------------------------------------

class TestRunMetricsRecordEvent:
    def test_record_event_writes_to_ledger(self, tmp_path):
        run_id = generate_run_id()
        rm = RunMetrics(
            run_id=run_id,
            agent_name="aspose-org-knowledge-enrichment",
            job_type="knowledge_enrichment",
            product="cells",
            platform="java",
            website="aspose.org",
            website_section="Docs",
            ledger_root=tmp_path,
        )
        rm.record_event(_event())
        rm.close()
        lines = [l for l in (tmp_path / f"{run_id}.jsonl").read_text().splitlines() if l.strip()]
        assert len(lines) == 1

    def test_record_events_writes_multiple_to_ledger(self, tmp_path):
        run_id = generate_run_id()
        rm = RunMetrics(
            run_id=run_id,
            agent_name="aspose-org-knowledge-enrichment",
            job_type="knowledge_enrichment",
            product="cells",
            platform="java",
            website="aspose.org",
            website_section="Docs",
            ledger_root=tmp_path,
        )
        rm.record_events([_event(), _event("CS-004", endpoint=_ENDPOINT_EMBED)])
        rm.close()
        lines = [l for l in (tmp_path / f"{run_id}.jsonl").read_text().splitlines() if l.strip()]
        assert len(lines) == 2

    def test_record_events_returns_count(self, tmp_path):
        rm = _make_run_metrics(tmp_path)
        count = rm.record_events([_event(), _event(), _event()])
        rm.close()
        assert count == 3

    def test_record_events_all_or_nothing_invalid_batch(self, tmp_path):
        """Mixed valid+invalid batch must not write any events."""
        run_id = generate_run_id()
        rm = RunMetrics(
            run_id=run_id,
            agent_name="aspose-org-knowledge-enrichment",
            job_type="knowledge_enrichment",
            product="cells",
            platform="java",
            website="aspose.org",
            website_section="Docs",
            ledger_root=tmp_path,
        )
        with pytest.raises(RunMetricsError):
            rm.record_events([_event(), _invalid_event()])
        # No file should have been created
        assert not (tmp_path / f"{run_id}.jsonl").exists()
        rm.close()

    def test_record_event_after_close_raises(self, tmp_path):
        rm = _make_run_metrics(tmp_path)
        rm.close()
        with pytest.raises(RunMetricsError, match="closed"):
            rm.record_event(_event())

    def test_record_events_after_close_raises(self, tmp_path):
        rm = _make_run_metrics(tmp_path)
        rm.close()
        with pytest.raises(RunMetricsError, match="closed"):
            rm.record_events([_event()])

    def test_invalid_single_event_raises(self, tmp_path):
        rm = _make_run_metrics(tmp_path)
        with pytest.raises(RunMetricsError):
            rm.record_event(_invalid_event())
        rm.close()

    def test_events_from_ledger_returns_persisted_events(self, tmp_path):
        rm = _make_run_metrics(tmp_path)
        ev = _event("CS-001", total_tokens=200)
        rm.record_event(ev)
        events = rm.events_from_ledger()
        assert len(events) == 1
        assert events[0].call_site_id == "CS-001"
        assert events[0].total_tokens == 200
        rm.close()


# ---------------------------------------------------------------------------
# TC-S6-R020–R031: to_row aggregation and validation
# ---------------------------------------------------------------------------

class TestRunMetricsToRow:
    def _rm(self, tmp_path, **kwargs):
        return _make_run_metrics(
            tmp_path,
            items_discovered=10,
            items_succeeded=10,
            items_failed=0,
            **kwargs,
        )

    def test_to_row_returns_metrics_row(self, tmp_path):
        rm = self._rm(tmp_path)
        rm.record_event(_event())
        row = rm.to_row(run_duration_ms=500)
        assert isinstance(row, MetricsRow)
        rm.close()

    def test_to_row_uses_aggregate_events_for_tokens(self, tmp_path):
        rm = self._rm(tmp_path)
        rm.record_events([_event(total_tokens=100), _event(total_tokens=200)])
        row = rm.to_row(run_duration_ms=500)
        assert row.token_usage == 300
        rm.close()

    def test_to_row_uses_aggregate_events_for_api_calls(self, tmp_path):
        rm = self._rm(tmp_path)
        rm.record_events([
            _event(api_calls_count_delta=1),
            _event(api_calls_count_delta=2),
        ])
        row = rm.to_row(run_duration_ms=500)
        assert row.api_calls_count == 3
        rm.close()

    def test_to_row_passes_validate_row(self, tmp_path):
        rm = self._rm(tmp_path)
        rm.record_event(_event())
        row = rm.to_row(run_duration_ms=500)
        result = validate_row(row)
        assert result.valid, result.errors
        rm.close()

    def test_to_row_empty_events_zero_tokens(self, tmp_path):
        rm = self._rm(tmp_path)
        row = rm.to_row(run_duration_ms=0)
        assert row.token_usage == 0
        assert row.api_calls_count == 0
        rm.close()

    def test_token_usage_property(self, tmp_path):
        rm = _make_run_metrics(tmp_path)
        rm.record_events([_event(total_tokens=50), _event(total_tokens=75)])
        assert rm.token_usage == 125
        rm.close()

    def test_api_calls_count_property(self, tmp_path):
        rm = _make_run_metrics(tmp_path)
        rm.record_events([_event(api_calls_count_delta=1), _event(api_calls_count_delta=3)])
        assert rm.api_calls_count == 4
        rm.close()

    def test_run_duration_ms_non_negative(self, tmp_path):
        with _make_run_metrics(tmp_path) as rm:
            assert rm.run_duration_ms >= 0

    def test_to_row_override_items_at_call_time(self, tmp_path):
        rm = _make_run_metrics(tmp_path)
        rm.record_event(_event())
        row = rm.to_row(
            items_discovered=5,
            items_succeeded=3,
            items_failed=2,
            run_duration_ms=100,
        )
        assert row.items_discovered == 5
        assert row.items_succeeded == 3
        assert row.items_failed == 2
        rm.close()

    def test_to_row_after_close_still_works(self, tmp_path):
        """to_row works on in-memory events even after ledger is closed."""
        rm = _make_run_metrics(tmp_path, items_discovered=5, items_succeeded=5)
        rm.record_event(_event(total_tokens=100))
        rm.close()
        # Should still produce a row from in-memory events
        row = rm.to_row(run_duration_ms=0)
        assert row.token_usage == 100

    def test_to_row_deterministic_with_explicit_args(self, tmp_path):
        rm = _make_run_metrics(tmp_path, items_discovered=5, items_succeeded=5)
        rm.record_event(_event(total_tokens=200))
        ts = now_iso8601()
        row1 = rm.to_row(run_duration_ms=100, timestamp=ts)
        row2 = rm.to_row(run_duration_ms=100, timestamp=ts)
        assert row1 == row2
        rm.close()

    def test_event_count_property(self, tmp_path):
        rm = _make_run_metrics(tmp_path)
        rm.record_events([_event(), _event(), _event()])
        assert rm.event_count == 3
        rm.close()


# ---------------------------------------------------------------------------
# TC-S6-R032–R037: Status derivation and agent_owner
# ---------------------------------------------------------------------------

class TestRunMetricsStatusAndOwner:
    def test_status_success_when_no_failures(self, tmp_path):
        rm = _make_run_metrics(tmp_path, items_discovered=5, items_succeeded=5, items_failed=0)
        rm.record_event(_event())
        row = rm.to_row(run_duration_ms=0)
        assert row.status == "success"
        rm.close()

    def test_status_failure_when_all_fail(self, tmp_path):
        rm = _make_run_metrics(tmp_path, items_discovered=5, items_succeeded=0, items_failed=5)
        rm.record_event(_event())
        row = rm.to_row(run_duration_ms=0)
        assert row.status == "failure"
        rm.close()

    def test_status_partial_success(self, tmp_path):
        rm = _make_run_metrics(tmp_path, items_discovered=5, items_succeeded=3, items_failed=2)
        rm.record_event(_event())
        row = rm.to_row(run_duration_ms=0)
        assert row.status == "partial_success"
        rm.close()

    def test_agent_owner_defaults_to_required(self, tmp_path):
        rm = _make_run_metrics(tmp_path, items_discovered=1, items_succeeded=1)
        rm.record_event(_event())
        row = rm.to_row(run_duration_ms=0)
        assert row.agent_owner == REQUIRED_AGENT_OWNER
        rm.close()

    def test_agent_owner_in_row(self, tmp_path):
        rm = RunMetrics(
            run_id=generate_run_id(),
            agent_name="aspose-org-knowledge-enrichment",
            job_type="knowledge_enrichment",
            product="cells",
            platform="java",
            website="aspose.org",
            website_section="Docs",
            agent_owner="Babar Raza",
            items_discovered=1,
            items_succeeded=1,
            ledger_root=tmp_path,
        )
        rm.record_event(_event())
        row = rm.to_row(run_duration_ms=0)
        assert row.agent_owner == "Babar Raza"
        rm.close()

    def test_item_name_explicit(self, tmp_path):
        rm = RunMetrics(
            run_id=generate_run_id(),
            agent_name="aspose-org-knowledge-enrichment",
            job_type="knowledge_enrichment",
            product="cells",
            platform="java",
            website="aspose.org",
            website_section="Docs",
            item_name="My explicit item name",
            items_discovered=1,
            items_succeeded=1,
            ledger_root=tmp_path,
        )
        rm.record_event(_event())
        row = rm.to_row(run_duration_ms=0)
        assert row.item_name == "My explicit item name"
        rm.close()

    def test_item_name_derived(self, tmp_path):
        rm = RunMetrics(
            run_id=generate_run_id(),
            agent_name="aspose-org-knowledge-enrichment",
            job_type="knowledge_enrichment",
            product="cells",
            platform="java",
            website="aspose.org",
            website_section="Docs",
            item_name=None,
            items_discovered=1,
            items_succeeded=1,
            ledger_root=tmp_path,
        )
        rm.record_event(_event())
        row = rm.to_row(run_duration_ms=0)
        expected = "aspose.org / Docs / cells / java / knowledge_enrichment"
        assert row.item_name == expected
        rm.close()


# ---------------------------------------------------------------------------
# TC-S6-R038–R041: Validation failures
# ---------------------------------------------------------------------------

class TestRunMetricsValidationFailures:
    def test_missing_website_section_raises(self, tmp_path):
        rm = RunMetrics(
            run_id=generate_run_id(),
            agent_name="aspose-org-knowledge-enrichment",
            job_type="knowledge_enrichment",
            product="cells",
            platform="java",
            website="aspose.org",
            website_section="",  # invalid — blank
            items_discovered=1,
            items_succeeded=1,
            ledger_root=tmp_path,
        )
        rm.record_event(_event())
        with pytest.raises(RunMetricsError):
            rm.to_row(run_duration_ms=0)
        rm.close()

    def test_missing_agent_name_raises(self, tmp_path):
        rm = RunMetrics(
            run_id=generate_run_id(),
            agent_name="",  # invalid — blank
            job_type="knowledge_enrichment",
            product="cells",
            platform="java",
            website="aspose.org",
            website_section="Docs",
            items_discovered=1,
            items_succeeded=1,
            ledger_root=tmp_path,
        )
        rm.record_event(_event())
        with pytest.raises(RunMetricsError):
            rm.to_row(run_duration_ms=0)
        rm.close()

    def test_items_exceeded_raises(self, tmp_path):
        """items_succeeded + items_failed > items_discovered should raise."""
        rm = _make_run_metrics(tmp_path, items_discovered=3, items_succeeded=3, items_failed=3)
        rm.record_event(_event())
        with pytest.raises(RunMetricsError):
            rm.to_row(run_duration_ms=0)
        rm.close()

    def test_corrupt_ledger_raises_from_events_from_ledger(self, tmp_path):
        """Corrupt JSONL file raises RunMetricsError via events_from_ledger."""
        run_id = generate_run_id()
        jsonl_path = tmp_path / f"{run_id}.jsonl"
        jsonl_path.write_text("not valid json\n")
        rm = RunMetrics(
            run_id=run_id,
            agent_name="aspose-org-knowledge-enrichment",
            job_type="knowledge_enrichment",
            product="cells",
            platform="java",
            website="aspose.org",
            website_section="Docs",
            ledger_root=tmp_path,
        )
        with pytest.raises(RunMetricsError):
            rm.events_from_ledger()
        rm.close()


# ---------------------------------------------------------------------------
# TC-S6-R042–R047: Safety — no forbidden imports, no secrets
# ---------------------------------------------------------------------------

class TestRunMetricsSafety:
    def _source(self) -> str:
        import commands.ops.run_metrics as mod
        return inspect.getsource(mod)

    def test_no_metrics_poster_import(self):
        src = self._source()
        # Must not import MetricsPoster — mention in docstrings is OK
        assert "import MetricsPoster" not in src
        assert "from commands.ops.metrics_poster" not in src
        assert "import metrics_poster" not in src

    def test_no_requests_import(self):
        assert "import requests" not in self._source()

    def test_no_httpx_import(self):
        assert "import httpx" not in self._source()

    def test_no_openai_import(self):
        assert "import openai" not in self._source()

    def test_no_secret_in_row(self, tmp_path):
        rm = _make_run_metrics(tmp_path, items_discovered=1, items_succeeded=1)
        rm.record_event(_event())
        row = rm.to_row(run_duration_ms=0)
        row_str = str(row)
        assert "sk-" not in row_str
        assert "Bearer " not in row_str
        rm.close()

    def test_no_secret_in_jsonl(self, tmp_path):
        run_id = generate_run_id()
        rm = RunMetrics(
            run_id=run_id,
            agent_name="aspose-org-knowledge-enrichment",
            job_type="knowledge_enrichment",
            product="cells",
            platform="java",
            website="aspose.org",
            website_section="Docs",
            items_discovered=1,
            items_succeeded=1,
            ledger_root=tmp_path,
        )
        rm.record_event(_event())
        rm.close()
        content = (tmp_path / f"{run_id}.jsonl").read_text()
        assert "sk-" not in content
        assert "Bearer " not in content

    def test_no_prompt_or_completion_field_in_row(self, tmp_path):
        rm = _make_run_metrics(tmp_path, items_discovered=1, items_succeeded=1)
        rm.record_event(_event())
        row = rm.to_row(run_duration_ms=0)
        # MetricsRow does not have prompt/completion fields
        assert not hasattr(row, "prompt")
        assert not hasattr(row, "completion")
        rm.close()

    def test_no_agent_metrics_endpoint_required(self, tmp_path):
        """RunMetrics works without AGENT_METRICS_ENDPOINT in env."""
        import os
        os.environ.pop("AGENT_METRICS_ENDPOINT", None)
        rm = _make_run_metrics(tmp_path, items_discovered=1, items_succeeded=1)
        rm.record_event(_event())
        row = rm.to_row(run_duration_ms=0)
        assert isinstance(row, MetricsRow)
        rm.close()

    def test_no_agent_metrics_token_required(self, tmp_path):
        """RunMetrics works without AGENT_METRICS_TOKEN in env."""
        import os
        os.environ.pop("AGENT_METRICS_TOKEN", None)
        rm = _make_run_metrics(tmp_path, items_discovered=1, items_succeeded=1)
        rm.record_event(_event())
        row = rm.to_row(run_duration_ms=0)
        assert isinstance(row, MetricsRow)
        rm.close()


# ---------------------------------------------------------------------------
# TC-S6-R048–R050: Event acceptance and ledger validation
# ---------------------------------------------------------------------------

class TestRunMetricsEventAcceptance:
    def test_accepts_cs001_events(self, tmp_path):
        rm = _make_run_metrics(tmp_path, items_discovered=1, items_succeeded=1)
        ev = _event("CS-001", total_tokens=200)
        rm.record_event(ev)
        assert rm.token_usage == 200
        rm.close()

    def test_accepts_cs004_events(self, tmp_path):
        rm = _make_run_metrics(tmp_path, items_discovered=1, items_succeeded=1)
        ev = _event("CS-004", total_tokens=50, endpoint=_ENDPOINT_EMBED,
                    request_type="embedding")
        rm.record_event(ev)
        assert rm.token_usage == 50
        rm.close()

    def test_preserves_parent_run_id_in_ledger(self, tmp_path):
        run_id = generate_run_id()
        ev = _event("CS-001", parent_run_id=run_id)
        rm = RunMetrics(
            run_id=run_id,
            agent_name="aspose-org-knowledge-enrichment",
            job_type="knowledge_enrichment",
            product="cells",
            platform="java",
            website="aspose.org",
            website_section="Docs",
            items_discovered=1,
            items_succeeded=1,
            ledger_root=tmp_path,
        )
        rm.record_event(ev)
        events = rm.events_from_ledger()
        assert events[0].parent_run_id == run_id
        rm.close()

    def test_preserves_work_slice_id_in_ledger(self, tmp_path):
        run_id = generate_run_id()
        work_slice_id = "abc123"
        ev = _event("CS-001", work_slice_id=work_slice_id)
        rm = RunMetrics(
            run_id=run_id,
            agent_name="aspose-org-knowledge-enrichment",
            job_type="knowledge_enrichment",
            product="cells",
            platform="java",
            website="aspose.org",
            website_section="Docs",
            items_discovered=1,
            items_succeeded=1,
            ledger_root=tmp_path,
        )
        rm.record_event(ev)
        events = rm.events_from_ledger()
        assert events[0].work_slice_id == work_slice_id
        rm.close()

    def test_events_from_ledger_for_aggregation(self, tmp_path):
        """Can read events back from ledger and aggregate independently."""
        from commands.ops.metrics_payload_builder import aggregate_events
        run_id = generate_run_id()
        rm = RunMetrics(
            run_id=run_id,
            agent_name="aspose-org-knowledge-enrichment",
            job_type="knowledge_enrichment",
            product="cells",
            platform="java",
            website="aspose.org",
            website_section="Docs",
            items_discovered=2,
            items_succeeded=2,
            ledger_root=tmp_path,
        )
        rm.record_events([_event(total_tokens=100), _event(total_tokens=150)])
        rm.close()
        events = rm.events_from_ledger()
        agg = aggregate_events(events)
        assert agg.total_tokens == 250
        assert agg.api_calls_count == 2

    def test_ledger_file_validates_via_validate_event_file(self, tmp_path):
        """JSONL file produced by RunMetrics passes validate_event_file()."""
        run_id = generate_run_id()
        rm = RunMetrics(
            run_id=run_id,
            agent_name="aspose-org-knowledge-enrichment",
            job_type="knowledge_enrichment",
            product="cells",
            platform="java",
            website="aspose.org",
            website_section="Docs",
            items_discovered=2,
            items_succeeded=2,
            ledger_root=tmp_path,
        )
        rm.record_events([_event("CS-001"), _event("CS-004")])
        rm.close()
        result = validate_event_file(tmp_path / f"{run_id}.jsonl")
        assert result.valid, result.errors

    def test_no_files_written_outside_tmp_path(self, tmp_path):
        """No production reports/ directory should be touched by tests."""
        default_reports = Path("reports/metrics/events")
        rm = _make_run_metrics(tmp_path, items_discovered=1, items_succeeded=1)
        rm.record_event(_event())
        rm.close()
        # The default reports path must not have been created by this test
        # (we passed ledger_root=tmp_path, so it goes to tmp_path only)
        run_id_file = default_reports / f"{rm.run_id}.jsonl"
        assert not run_id_file.exists()


# ---------------------------------------------------------------------------
# TC-S6-R051: _derive_status and _build_item_name helpers
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_derive_status_all_fail(self):
        assert _derive_status(5, 0, 5) == "failure"

    def test_derive_status_all_succeed(self):
        assert _derive_status(5, 5, 0) == "success"

    def test_derive_status_partial(self):
        assert _derive_status(5, 3, 2) == "partial_success"

    def test_derive_status_zero_items(self):
        assert _derive_status(0, 0, 0) == "success"

    def test_build_item_name(self):
        name = _build_item_name("aspose.org", "Docs", "cells", "java", "knowledge_enrichment")
        assert name == "aspose.org / Docs / cells / java / knowledge_enrichment"

    def test_run_id_property(self, tmp_path):
        run_id = generate_run_id()
        rm = RunMetrics(
            run_id=run_id,
            agent_name="aspose-org-knowledge-enrichment",
            job_type="knowledge_enrichment",
            product="cells",
            platform="java",
            website="aspose.org",
            website_section="Docs",
            ledger_root=tmp_path,
        )
        assert rm.run_id == run_id
        rm.close()

    def test_external_ledger_not_closed_by_run_metrics(self, tmp_path):
        """If ledger is provided externally, RunMetrics.close() must not close it."""
        run_id = generate_run_id()
        ledger = MetricsEventLedger(run_id=run_id, root_dir=tmp_path)
        rm = RunMetrics(
            run_id=run_id,
            agent_name="aspose-org-knowledge-enrichment",
            job_type="knowledge_enrichment",
            product="cells",
            platform="java",
            website="aspose.org",
            website_section="Docs",
            ledger=ledger,
        )
        rm.record_event(_event())
        rm.close()
        # Ledger was external, so it should NOT be closed by RunMetrics.close()
        assert not ledger._closed
        ledger.close()
