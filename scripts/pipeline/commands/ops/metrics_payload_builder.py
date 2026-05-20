# Adapted from aspose.org
"""Payload builder for agent metrics: aggregation and MetricsRow construction.

Provides two helpers on top of metrics_schema.py:

    aggregate_events(events) -> AggregateResult
        Sum total_tokens and api_calls_count_delta across a list of MetricsEvents.
        Only events for the professionalize transport are included (all events that
        reach this function are assumed to be professionalize events; callers are
        responsible for filtering non-professionalize events before passing them in).

    build_run_row(**kwargs) -> MetricsRow
        Construct a MetricsRow from caller-supplied fields plus AggregateResult.
        Validates the row before returning; raises ValueError on invalid row.

No HTTP calls. No posting. No ledger writes. No secrets.

Slice 6 of Agent Metrics Integration (METRICS-PLAN-001 v7.1).
"""

from __future__ import annotations

from dataclasses import dataclass

from commands.ops.metrics_schema import (
    MetricsEvent,
    MetricsRow,
    ValidationResult,
    now_iso8601,
    validate_row,
)


# --------------------------------------------------------------------------- #
# AggregateResult
# --------------------------------------------------------------------------- #


@dataclass
class AggregateResult:
    """Aggregated metrics across a batch of MetricsEvents."""

    total_tokens: int
    api_calls_count: int
    event_count: int


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def aggregate_events(events: list[MetricsEvent]) -> AggregateResult:
    """Sum token usage and API call counts across *events*.

    Parameters
    ----------
    events:
        List of MetricsEvent objects from one or more call sites. May be empty.
        Caller is responsible for passing only professionalize-transport events
        (non-professionalize events like Gemini, Ollama, M2M should be excluded
        before calling this function).

    Returns
    -------
    AggregateResult
        Summed token_usage (from total_tokens), api_calls_count (from
        api_calls_count_delta), and event_count.

    Design invariants
    -----------------
    - Negative values are treated as zero (defensive; schema validation should
      have already rejected them, but this function is purely additive).
    - Empty list returns AggregateResult(0, 0, 0).
    - Never raises; always returns a valid AggregateResult.
    """
    total_tokens = 0
    api_calls_count = 0
    for ev in events:
        tokens = ev.total_tokens if isinstance(ev.total_tokens, int) and ev.total_tokens >= 0 else 0
        calls = ev.api_calls_count_delta if isinstance(ev.api_calls_count_delta, int) and ev.api_calls_count_delta >= 0 else 0
        total_tokens += tokens
        api_calls_count += calls
    return AggregateResult(
        total_tokens=total_tokens,
        api_calls_count=api_calls_count,
        event_count=len(events),
    )


def build_run_row(
    *,
    agent_name: str,
    agent_owner: str,
    job_type: str,
    run_id: str,
    status: str,
    product: str,
    platform: str,
    website: str,
    website_section: str,
    item_name: str,
    items_discovered: int,
    items_failed: int,
    items_succeeded: int,
    run_duration_ms: int,
    aggregate: AggregateResult,
    timestamp: str | None = None,
) -> MetricsRow:
    """Build and validate a MetricsRow from caller-supplied fields.

    Parameters
    ----------
    aggregate:
        AggregateResult from aggregate_events(). token_usage and api_calls_count
        are taken from this object.
    timestamp:
        ISO-8601 string. If None (default), now_iso8601() is used.

    Returns
    -------
    MetricsRow
        A fully-populated, validated MetricsRow ready for posting.

    Raises
    ------
    ValueError
        If the constructed row fails validate_row(). The error message includes
        all validation errors.
    """
    ts = timestamp if timestamp is not None else now_iso8601()
    row = MetricsRow(
        timestamp=ts,
        agent_name=agent_name,
        agent_owner=agent_owner,
        job_type=job_type,
        run_id=run_id,
        status=status,
        product=product,
        platform=platform,
        website=website,
        website_section=website_section,
        item_name=item_name,
        items_discovered=items_discovered,
        items_failed=items_failed,
        items_succeeded=items_succeeded,
        run_duration_ms=run_duration_ms,
        token_usage=aggregate.total_tokens,
        api_calls_count=aggregate.api_calls_count,
    )
    result: ValidationResult = validate_row(row)
    if not result.valid:
        raise ValueError(
            f"build_run_row: invalid MetricsRow — {'; '.join(result.errors)}"
        )
    return row
