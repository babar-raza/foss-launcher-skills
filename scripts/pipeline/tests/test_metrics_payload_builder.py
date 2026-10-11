"""Standalone tests for metrics_payload_builder: aggregate_events and build_run_row.

Proves that token_usage and api_calls_count in MetricsRow are derived by
aggregating MetricsEvent records — never hardcoded.

Slice 12 of Agent Metrics Integration (METRICS-PLAN-001 v8.0).
"""

from __future__ import annotations

import pytest

from commands.ops.metrics_payload_builder import (
    AggregateResult,
    aggregate_events,
    build_run_row,
)
from commands.ops.metrics_schema import MetricsEvent, MetricsRow, now_iso8601


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(
    call_site_id: str = "CS-001",
    request_type: str = "chat",
    total_tokens: int = 100,
    api_calls_count_delta: int = 1,
    status: str = "success",
) -> MetricsEvent:
    return MetricsEvent(
        event_id="test-event-id",
        call_site_id=call_site_id,
        endpoint="/chat/completions",
        request_type=request_type,
        status=status,
        prompt_tokens=total_tokens // 2,
        completion_tokens=total_tokens - total_tokens // 2,
        total_tokens=total_tokens,
        api_calls_count_delta=api_calls_count_delta,
        timestamp=now_iso8601(),
    )


def _valid_row_kwargs(aggregate: AggregateResult) -> dict:
    return dict(
        agent_name="FOSS Launcher",
        agent_owner="Babar Raza",
        job_type="Knowledge Enrichment",
        run_id="test-run-id",
        status="success",
        product="Aspose.Cells",
        platform="Java",
        website="aspose.org",
        website_section="Docs",
        item_name="Cells Java Run",
        items_discovered=5,
        items_failed=0,
        items_succeeded=5,
        run_duration_ms=1234,
        aggregate=aggregate,
    )


# ---------------------------------------------------------------------------
# TestAggregateEvents
# ---------------------------------------------------------------------------


class TestAggregateEvents:
    def test_empty_list_returns_zeros(self):
        result = aggregate_events([])
        assert result.total_tokens == 0
        assert result.api_calls_count == 0
        assert result.event_count == 0

    def test_single_event_tokens_counted(self):
        result = aggregate_events([_make_event(total_tokens=230)])
        assert result.total_tokens == 230
        assert result.api_calls_count == 1
        assert result.event_count == 1

    def test_multiple_events_tokens_summed(self):
        events = [
            _make_event("CS-001", total_tokens=100),
            _make_event("CS-001", total_tokens=200),
            _make_event("CS-001", total_tokens=150),
        ]
        result = aggregate_events(events)
        assert result.total_tokens == 450
        assert result.api_calls_count == 3

    def test_api_calls_count_counts_each_attempt(self):
        events = [
            _make_event(total_tokens=100, api_calls_count_delta=1, status="success"),
            _make_event(total_tokens=0, api_calls_count_delta=1, status="retry"),
            _make_event(total_tokens=0, api_calls_count_delta=1, status="failure"),
        ]
        result = aggregate_events(events)
        assert result.api_calls_count == 3

    def test_tokens_zero_on_failed_call(self):
        """Failed API call contributes 0 tokens but 1 api_count."""
        events = [
            _make_event(total_tokens=0, api_calls_count_delta=1, status="failure"),
        ]
        result = aggregate_events(events)
        assert result.total_tokens == 0
        assert result.api_calls_count == 1

    def test_cross_callsite_aggregation(self):
        """Events from CS-001 and CS-008 are summed together."""
        events = [
            _make_event("CS-001", "chat", total_tokens=150),
            _make_event("CS-008", "translation", total_tokens=80),
        ]
        result = aggregate_events(events)
        assert result.total_tokens == 230
        assert result.api_calls_count == 2

    def test_embedding_tokens_counted(self):
        events = [
            _make_event("CS-004", "embedding", total_tokens=50),
            _make_event("CS-004", "embedding", total_tokens=50),
        ]
        result = aggregate_events(events)
        assert result.total_tokens == 100
        assert result.api_calls_count == 2

    def test_batch_results_are_additive(self):
        batch1 = [_make_event(total_tokens=100), _make_event(total_tokens=200)]
        batch2 = [_make_event(total_tokens=50)]
        r1 = aggregate_events(batch1)
        r2 = aggregate_events(batch2)
        combined = aggregate_events(batch1 + batch2)
        assert combined.total_tokens == r1.total_tokens + r2.total_tokens
        assert combined.api_calls_count == r1.api_calls_count + r2.api_calls_count


# ---------------------------------------------------------------------------
# TestBuildRunRow
# ---------------------------------------------------------------------------


class TestBuildRunRow:
    def test_valid_row_constructed_from_aggregate(self):
        agg = aggregate_events([_make_event(total_tokens=300)])
        row = build_run_row(**_valid_row_kwargs(agg))
        assert isinstance(row, MetricsRow)
        assert row.token_usage == 300
        assert row.api_calls_count == 1

    def test_token_usage_equals_aggregate_total_tokens(self):
        """token_usage is taken from aggregate.total_tokens — not hardcoded."""
        for total in [0, 100, 5000, 99999]:
            agg = AggregateResult(total_tokens=total, api_calls_count=1, event_count=1)
            row = build_run_row(**_valid_row_kwargs(agg))
            assert row.token_usage == total

    def test_api_calls_count_equals_aggregate_api_count(self):
        """api_calls_count is taken from aggregate.api_calls_count — not hardcoded."""
        for count in [0, 1, 10, 100]:
            agg = AggregateResult(total_tokens=0, api_calls_count=count, event_count=count)
            row = build_run_row(**_valid_row_kwargs(agg))
            assert row.api_calls_count == count

    def test_zero_events_produces_zero_token_usage(self):
        agg = aggregate_events([])
        row = build_run_row(**_valid_row_kwargs(agg))
        assert row.token_usage == 0
        assert row.api_calls_count == 0

    def test_invalid_agent_owner_raises_value_error(self):
        agg = aggregate_events([])
        kwargs = _valid_row_kwargs(agg)
        kwargs["agent_owner"] = "Wrong Person"
        with pytest.raises(ValueError, match="agent_owner"):
            build_run_row(**kwargs)

    def test_items_exceeded_discovered_raises_value_error(self):
        agg = aggregate_events([])
        kwargs = _valid_row_kwargs(agg)
        kwargs["items_discovered"] = 1
        kwargs["items_succeeded"] = 2
        kwargs["items_failed"] = 0
        with pytest.raises(ValueError):
            build_run_row(**kwargs)


# ---------------------------------------------------------------------------
# TestProductionStyleRows
# ---------------------------------------------------------------------------


class TestProductionStyleRows:
    """Tests with realistic production-style display names."""

    def test_cells_java_enrichment_row(self):
        events = [_make_event("CS-001", "chat", total_tokens=1500)]
        agg = aggregate_events(events)
        row = build_run_row(
            agent_name="FOSS Launcher",
            agent_owner="Babar Raza",
            job_type="Knowledge Enrichment",
            run_id="prod-run-id-001",
            status="success",
            product="Aspose.Cells",
            platform="Java",
            website="aspose.org",
            website_section="Docs",
            item_name="Cells Java Run",
            items_discovered=10,
            items_failed=0,
            items_succeeded=10,
            run_duration_ms=5000,
            aggregate=agg,
        )
        assert row.token_usage == 1500
        assert row.api_calls_count == 1
        assert row.agent_name == "FOSS Launcher"
        assert row.product == "Aspose.Cells"
        assert row.item_name == "Cells Java Run"

    def test_words_net_gap_evaluation_row(self):
        events = [
            _make_event("CS-001", "chat", total_tokens=800),
            _make_event("CS-001", "chat", total_tokens=600),
        ]
        agg = aggregate_events(events)
        row = build_run_row(
            agent_name="FOSS Launcher",
            agent_owner="Babar Raza",
            job_type="Gap Evaluation",
            run_id="prod-run-id-002",
            status="success",
            product="Aspose.Words",
            platform=".NET",
            website="aspose.org",
            website_section="Docs",
            item_name="Words .NET Run",
            items_discovered=1,
            items_failed=0,
            items_succeeded=1,
            run_duration_ms=3200,
            aggregate=agg,
        )
        assert row.token_usage == 1400
        assert row.api_calls_count == 2

    def test_pdf_python_translation_row(self):
        events = [
            _make_event("CS-008", "translation", total_tokens=200, api_calls_count_delta=1),
            _make_event("CS-008", "translation", total_tokens=180, api_calls_count_delta=1),
            _make_event("CS-008", "translation", total_tokens=0, api_calls_count_delta=1, status="failure"),
        ]
        agg = aggregate_events(events)
        row = build_run_row(
            agent_name="FOSS Launcher",
            agent_owner="Babar Raza",
            job_type="Content Translation",
            run_id="prod-run-id-003",
            status="partial_success",
            product="Aspose.PDF",
            platform="Python",
            website="aspose.org",
            website_section="Docs",
            item_name="PDF Python Run",
            items_discovered=3,
            items_failed=1,
            items_succeeded=2,
            run_duration_ms=8000,
            aggregate=agg,
        )
        assert row.token_usage == 380
        assert row.api_calls_count == 3
        assert row.status == "partial_success"

    def test_seo_disabled_row_with_zero_events(self):
        """SEO scope (LITELLM_KEY NOT_SET) — zero events, zero token counts."""
        agg = aggregate_events([])
        row = build_run_row(
            agent_name="FOSS Launcher",
            agent_owner="Babar Raza",
            job_type="SEO",
            run_id="prod-run-id-004",
            status="success",
            product="Aspose.Imaging",
            platform="Java",
            website="aspose.org",
            website_section="Docs",
            item_name="Imaging Java Run",
            items_discovered=1,
            items_failed=0,
            items_succeeded=1,
            run_duration_ms=500,
            aggregate=agg,
        )
        assert row.token_usage == 0
        assert row.api_calls_count == 0


# ---------------------------------------------------------------------------
# TestTokenUsageNotHardcoded
# ---------------------------------------------------------------------------


class TestTokenUsageNotHardcoded:
    """Explicitly prove token_usage and api_calls_count are NOT hardcoded."""

    def test_different_token_counts_produce_different_rows(self):
        """Two runs with different token counts must produce different token_usage."""
        agg_small = AggregateResult(total_tokens=100, api_calls_count=1, event_count=1)
        agg_large = AggregateResult(total_tokens=9999, api_calls_count=5, event_count=5)
        row_small = build_run_row(**_valid_row_kwargs(agg_small))
        row_large = build_run_row(**_valid_row_kwargs(agg_large))
        assert row_small.token_usage == 100
        assert row_large.token_usage == 9999
        assert row_small.token_usage != row_large.token_usage

    def test_token_usage_grows_with_each_event(self):
        """Adding events increases token_usage proportionally."""
        events = []
        for i in range(1, 6):
            events.append(_make_event(total_tokens=100))
            agg = aggregate_events(events)
            row = build_run_row(**_valid_row_kwargs(agg))
            assert row.token_usage == i * 100

    def test_api_calls_count_grows_with_each_event(self):
        """Adding events increases api_calls_count by 1 per event."""
        events = []
        for i in range(1, 6):
            events.append(_make_event(api_calls_count_delta=1))
            agg = aggregate_events(events)
            row = build_run_row(**_valid_row_kwargs(agg))
            assert row.api_calls_count == i
