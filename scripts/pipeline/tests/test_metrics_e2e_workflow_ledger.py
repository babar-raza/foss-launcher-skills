"""E2E workflow test: multi-callsite events → MetricsEventLedger → aggregate → MetricsRow.

Covers the full pipeline from per-HTTP-call MetricsEvent objects through JSONL
persistence (MetricsEventLedger) and aggregation (aggregate_events) to the final
17-field MetricsRow payload (build_run_row).

Zero real network calls — all events are constructed directly.

Slice 6 of Agent Metrics Integration (METRICS-PLAN-001 v7.1).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Ensure scripts/pipeline is on sys.path
_PIPELINE_ROOT = Path(__file__).resolve().parent.parent
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from commands.ops.metrics_schema import (
    MetricsEvent,
    MetricsRow,
    generate_event_id,
    generate_run_id,
    now_iso8601,
    validate_event,
    validate_row,
)
from commands.ops.metrics_event_ledger import MetricsEventLedger, load_events
from commands.ops.metrics_payload_builder import (
    AggregateResult,
    aggregate_events,
    build_run_row,
)


# ---------------------------------------------------------------------------
# Helpers — fake event factories per call site
# ---------------------------------------------------------------------------

def _make_event(
    call_site_id: str,
    request_type: str,
    total_tokens: int,
    api_calls_count_delta: int = 1,
    status: str = "success",
    run_id: str | None = None,
    endpoint: str = "https://llm.professionalize.com/v1/chat/completions",
) -> MetricsEvent:
    """Build a valid MetricsEvent for a given call site."""
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
        parent_run_id=run_id,
    )


def _make_cs001_event(run_id: str | None = None) -> MetricsEvent:
    return _make_event("CS-001", "chat", total_tokens=200, run_id=run_id)


def _make_cs004_event(run_id: str | None = None) -> MetricsEvent:
    return _make_event(
        "CS-004", "embedding", total_tokens=50, api_calls_count_delta=1,
        endpoint="https://llm.professionalize.com/v1/embeddings", run_id=run_id,
    )


def _make_cs008_event(run_id: str | None = None) -> MetricsEvent:
    return _make_event("CS-008", "translation", total_tokens=150, run_id=run_id)


def _make_cs009_event(run_id: str | None = None) -> MetricsEvent:
    return _make_event("CS-009", "seo", total_tokens=80, run_id=run_id)


# ---------------------------------------------------------------------------
# Tests — aggregate_events
# ---------------------------------------------------------------------------

class TestAggregateEvents:
    def test_empty_list_returns_zeros(self):
        result = aggregate_events([])
        assert result.total_tokens == 0
        assert result.api_calls_count == 0
        assert result.event_count == 0

    def test_single_event_sums_correctly(self):
        ev = _make_cs001_event()
        result = aggregate_events([ev])
        assert result.total_tokens == 200
        assert result.api_calls_count == 1
        assert result.event_count == 1

    def test_multiple_events_sum_tokens(self):
        events = [
            _make_cs001_event(),   # 200 tokens
            _make_cs004_event(),   # 50 tokens
            _make_cs008_event(),   # 150 tokens
            _make_cs009_event(),   # 80 tokens
        ]
        result = aggregate_events(events)
        assert result.total_tokens == 480
        assert result.api_calls_count == 4
        assert result.event_count == 4

    def test_multiple_api_calls_counted(self):
        # CS-008 retry: 3 attempts
        events = [
            _make_event("CS-008", "translation", 100, api_calls_count_delta=1),
            _make_event("CS-008", "translation", 0, api_calls_count_delta=1, status="retry"),
            _make_event("CS-008", "translation", 0, api_calls_count_delta=1, status="failure"),
        ]
        result = aggregate_events(events)
        assert result.api_calls_count == 3
        assert result.event_count == 3

    def test_negative_tokens_treated_as_zero(self):
        # Defensive: malformed event with negative total_tokens
        ev = MetricsEvent(
            event_id=generate_event_id(),
            call_site_id="CS-001",
            endpoint="https://llm.professionalize.com/v1/chat/completions",
            request_type="chat",
            status="success",
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=-1,  # invalid but defensive
            api_calls_count_delta=1,
            timestamp=now_iso8601(),
        )
        result = aggregate_events([ev])
        assert result.total_tokens == 0
        assert result.api_calls_count == 1

    def test_two_batches_separate_and_combined(self):
        batch1 = [_make_cs001_event(), _make_cs004_event()]
        batch2 = [_make_cs008_event(), _make_cs009_event()]
        r1 = aggregate_events(batch1)
        r2 = aggregate_events(batch2)
        combined = aggregate_events(batch1 + batch2)
        assert combined.total_tokens == r1.total_tokens + r2.total_tokens
        assert combined.api_calls_count == r1.api_calls_count + r2.api_calls_count


# ---------------------------------------------------------------------------
# Tests — build_run_row
# ---------------------------------------------------------------------------

class TestBuildRunRow:

    def _valid_kwargs(self, aggregate: AggregateResult) -> dict:
        return dict(
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
            run_duration_ms=1234,
            aggregate=aggregate,
            timestamp=now_iso8601(),
        )

    def test_valid_row_returned(self):
        agg = aggregate_events([_make_cs001_event()])
        row = build_run_row(**self._valid_kwargs(agg))
        assert isinstance(row, MetricsRow)

    def test_token_usage_from_aggregate(self):
        events = [_make_cs001_event(), _make_cs004_event()]
        agg = aggregate_events(events)
        row = build_run_row(**self._valid_kwargs(agg))
        assert row.token_usage == agg.total_tokens

    def test_api_calls_count_from_aggregate(self):
        events = [_make_cs001_event(), _make_cs008_event()]
        agg = aggregate_events(events)
        row = build_run_row(**self._valid_kwargs(agg))
        assert row.api_calls_count == agg.api_calls_count

    def test_validate_row_passes_on_output(self):
        agg = aggregate_events([_make_cs001_event()])
        row = build_run_row(**self._valid_kwargs(agg))
        result = validate_row(row)
        assert result.valid, result.errors

    def test_zero_token_aggregate_valid(self):
        agg = aggregate_events([])
        row = build_run_row(**self._valid_kwargs(agg))
        assert row.token_usage == 0
        assert row.api_calls_count == 0

    def test_invalid_agent_owner_raises(self):
        agg = aggregate_events([])
        kwargs = self._valid_kwargs(agg)
        kwargs["agent_owner"] = "Wrong Person"
        with pytest.raises(ValueError, match="agent_owner"):
            build_run_row(**kwargs)

    def test_invalid_status_raises(self):
        agg = aggregate_events([])
        kwargs = self._valid_kwargs(agg)
        kwargs["status"] = "not_a_status"
        with pytest.raises(ValueError, match="status"):
            build_run_row(**kwargs)

    def test_items_exceeded_raises(self):
        agg = aggregate_events([])
        kwargs = self._valid_kwargs(agg)
        kwargs["items_discovered"] = 5
        kwargs["items_succeeded"] = 4
        kwargs["items_failed"] = 3  # 4+3 > 5
        with pytest.raises(ValueError, match="items_succeeded"):
            build_run_row(**kwargs)

    def test_default_timestamp_is_iso8601(self):
        agg = aggregate_events([])
        kwargs = self._valid_kwargs(agg)
        kwargs.pop("timestamp")
        row = build_run_row(**kwargs)
        from commands.ops.metrics_schema import is_valid_iso8601
        assert is_valid_iso8601(row.timestamp)


# ---------------------------------------------------------------------------
# Tests — full E2E ledger workflow
# ---------------------------------------------------------------------------

class TestE2ELedgerWorkflow:

    def test_multi_callsite_events_round_trip(self, tmp_path):
        """Events from CS-001, CS-004, CS-008, CS-009 → ledger → read back."""
        run_id = generate_run_id()
        events = [
            _make_cs001_event(run_id),
            _make_cs004_event(run_id),
            _make_cs008_event(run_id),
            _make_cs009_event(run_id),
        ]

        ledger = MetricsEventLedger(run_id=run_id, root_dir=tmp_path)
        count = ledger.record_events(events)
        ledger.close()
        assert count == 4

        readback = ledger.read_events()
        assert len(readback) == 4

    def test_jsonl_one_line_per_event(self, tmp_path):
        """JSONL file has exactly one line per event."""
        run_id = generate_run_id()
        events = [_make_cs001_event(), _make_cs004_event(), _make_cs008_event()]

        ledger = MetricsEventLedger(run_id=run_id, root_dir=tmp_path)
        ledger.record_events(events)
        ledger.close()

        jsonl_path = tmp_path / f"{run_id}.jsonl"
        lines = [l for l in jsonl_path.read_text().splitlines() if l.strip()]
        assert len(lines) == 3
        for line in lines:
            obj = json.loads(line)
            assert "call_site_id" in obj
            assert "total_tokens" in obj

    def test_required_fields_preserved(self, tmp_path):
        """call_site_id, total_tokens, api_calls_count_delta preserved through JSONL."""
        run_id = generate_run_id()
        ev = _make_cs001_event(run_id)

        ledger = MetricsEventLedger(run_id=run_id, root_dir=tmp_path)
        ledger.record_event(ev)
        ledger.close()

        readback = ledger.read_events()
        assert len(readback) == 1
        restored = readback[0]
        assert restored.call_site_id == "CS-001"
        assert restored.total_tokens == 200
        assert restored.api_calls_count_delta == 1
        assert restored.parent_run_id == run_id

    def test_all_call_site_ids_preserved(self, tmp_path):
        """call_site_id is correctly round-tripped for all four call sites."""
        run_id = generate_run_id()
        events = [
            _make_cs001_event(run_id),
            _make_cs004_event(run_id),
            _make_cs008_event(run_id),
            _make_cs009_event(run_id),
        ]
        ledger = MetricsEventLedger(run_id=run_id, root_dir=tmp_path)
        ledger.record_events(events)
        ledger.close()

        readback = ledger.read_events()
        ids = {ev.call_site_id for ev in readback}
        assert ids == {"CS-001", "CS-004", "CS-008", "CS-009"}

    def test_token_usage_preserved(self, tmp_path):
        """total_tokens round-trips correctly through JSONL."""
        run_id = generate_run_id()
        events = [
            _make_cs001_event(run_id),  # 200
            _make_cs004_event(run_id),  # 50
        ]
        ledger = MetricsEventLedger(run_id=run_id, root_dir=tmp_path)
        ledger.record_events(events)
        ledger.close()

        readback = ledger.read_events()
        total = sum(ev.total_tokens for ev in readback)
        assert total == 250

    def test_events_validate_after_round_trip(self, tmp_path):
        """All events pass validate_event after JSONL round-trip."""
        run_id = generate_run_id()
        events = [
            _make_cs001_event(run_id),
            _make_cs004_event(run_id),
            _make_cs008_event(run_id),
            _make_cs009_event(run_id),
        ]
        ledger = MetricsEventLedger(run_id=run_id, root_dir=tmp_path)
        ledger.record_events(events)
        ledger.close()

        for ev in ledger.read_events():
            result = validate_event(ev)
            assert result.valid, f"Event {ev.event_id} failed: {result.errors}"

    def test_aggregate_from_ledger_events(self, tmp_path):
        """Aggregate over read-back events sums correctly."""
        run_id = generate_run_id()
        events = [
            _make_cs001_event(run_id),  # 200
            _make_cs004_event(run_id),  # 50
            _make_cs008_event(run_id),  # 150
            _make_cs009_event(run_id),  # 80
        ]
        ledger = MetricsEventLedger(run_id=run_id, root_dir=tmp_path)
        ledger.record_events(events)
        ledger.close()

        readback = ledger.read_events()
        agg = aggregate_events(readback)
        assert agg.total_tokens == 480
        assert agg.api_calls_count == 4
        assert agg.event_count == 4

    def test_build_run_row_from_ledger_events(self, tmp_path):
        """Full pipeline: events → ledger → aggregate → MetricsRow → validate."""
        run_id = generate_run_id()
        events = [
            _make_cs001_event(run_id),
            _make_cs004_event(run_id),
            _make_cs008_event(run_id),
        ]
        ledger = MetricsEventLedger(run_id=run_id, root_dir=tmp_path)
        ledger.record_events(events)
        ledger.close()

        readback = ledger.read_events()
        agg = aggregate_events(readback)

        row = build_run_row(
            agent_name="aspose-org-knowledge-enrichment",
            agent_owner="Babar Raza",
            job_type="knowledge_enrichment",
            run_id=run_id,
            status="success",
            product="cells",
            platform="java",
            website="aspose.org",
            website_section="Docs",
            item_name="aspose.org / Docs / cells / java / knowledge_enrichment",
            items_discovered=3,
            items_failed=0,
            items_succeeded=3,
            run_duration_ms=500,
            aggregate=agg,
        )

        result = validate_row(row)
        assert result.valid, result.errors
        assert row.token_usage == 400  # 200+50+150
        assert row.api_calls_count == 3

    def test_load_events_module_helper(self, tmp_path):
        """load_events() module-level helper reads JSONL correctly."""
        run_id = generate_run_id()
        events = [_make_cs001_event(run_id), _make_cs008_event(run_id)]

        ledger = MetricsEventLedger(run_id=run_id, root_dir=tmp_path)
        ledger.record_events(events)
        ledger.close()

        jsonl_path = tmp_path / f"{run_id}.jsonl"
        loaded = load_events(jsonl_path)
        assert len(loaded) == 2
        assert {ev.call_site_id for ev in loaded} == {"CS-001", "CS-008"}

    def test_no_secrets_in_jsonl(self, tmp_path):
        """JSONL output must not contain secret-like strings."""
        run_id = generate_run_id()
        ev = _make_cs001_event(run_id)

        ledger = MetricsEventLedger(run_id=run_id, root_dir=tmp_path)
        ledger.record_event(ev)
        ledger.close()

        content = (tmp_path / f"{run_id}.jsonl").read_text()
        assert "sk-" not in content
        assert "Bearer " not in content
        assert "api_key=" not in content

    def test_context_manager_usage(self, tmp_path):
        """MetricsEventLedger works as context manager."""
        run_id = generate_run_id()
        events = [_make_cs001_event(), _make_cs004_event()]

        with MetricsEventLedger(run_id=run_id, root_dir=tmp_path) as ledger:
            ledger.record_events(events)

        # After __exit__, file is flushed and closed
        readback = MetricsEventLedger(run_id=run_id, root_dir=tmp_path).read_events()
        assert len(readback) == 2


# ---------------------------------------------------------------------------
# Tests — workflow integration (adapter events → ledger)
# ---------------------------------------------------------------------------

class TestWorkflowIntegration:
    """Verify that events emitted by each adapter can be recorded in the ledger.

    These tests simulate the caller pattern: adapter emits events into a list,
    caller records them to the ledger. This proves the integration contract
    without requiring the adapter's HTTP machinery.
    """

    def test_cs001_events_recordable(self, tmp_path):
        """CS-001 style events (from LLMRouter.call_chat result) persist to ledger."""
        run_id = generate_run_id()
        # Simulate what LLMRouter puts on CallResult.metrics_events
        router_events = [_make_cs001_event(run_id)]
        ledger = MetricsEventLedger(run_id=run_id, root_dir=tmp_path)
        ledger.record_events(router_events)
        ledger.close()
        assert len(ledger.read_events()) == 1

    def test_cs004_events_recordable(self, tmp_path):
        """CS-004 style events (from EmbeddingClient.metrics_events) persist to ledger."""
        run_id = generate_run_id()
        embed_events = [_make_cs004_event(run_id), _make_cs004_event(run_id)]
        ledger = MetricsEventLedger(run_id=run_id, root_dir=tmp_path)
        ledger.record_events(embed_events)
        ledger.close()
        assert len(ledger.read_events()) == 2

    def test_cs008_events_recordable(self, tmp_path):
        """CS-008 style events (from LLMBackend.metrics_events) persist to ledger."""
        run_id = generate_run_id()
        translator_events = [
            _make_cs008_event(run_id),
            _make_event("CS-008", "translation", 0, status="retry", run_id=run_id),
        ]
        ledger = MetricsEventLedger(run_id=run_id, root_dir=tmp_path)
        ledger.record_events(translator_events)
        ledger.close()
        assert len(ledger.read_events()) == 2

    def test_cs009_events_recordable(self, tmp_path):
        """CS-009 style events (from recommend.metrics_events) persist to ledger."""
        run_id = generate_run_id()
        seo_events = [_make_cs009_event(run_id)]
        ledger = MetricsEventLedger(run_id=run_id, root_dir=tmp_path)
        ledger.record_events(seo_events)
        ledger.close()
        assert len(ledger.read_events()) == 1

    def test_mixed_callsite_events_aggregate_correctly(self, tmp_path):
        """Mixed CS-001/004/008/009 events from one run aggregate to correct totals."""
        run_id = generate_run_id()
        # Simulated: one LLMRouter call + two embed batches + one translation
        all_events = [
            _make_cs001_event(run_id),  # 200 tokens
            _make_cs004_event(run_id),  # 50 tokens, batch 1
            _make_cs004_event(run_id),  # 50 tokens, batch 2
            _make_cs008_event(run_id),  # 150 tokens
        ]
        ledger = MetricsEventLedger(run_id=run_id, root_dir=tmp_path)
        ledger.record_events(all_events)
        ledger.close()

        readback = ledger.read_events()
        agg = aggregate_events(readback)
        assert agg.total_tokens == 450  # 200+50+50+150
        assert agg.api_calls_count == 4
        assert agg.event_count == 4
