# Adapted from aspose.org
"""RunMetrics: context-manager for aggregating per-call MetricsEvents into a MetricsRow.

Wraps MetricsEventLedger (persistence) and metrics_payload_builder (aggregation)
to provide a single context-manager that:

  1. Accepts MetricsEvent objects during a run via record_event() / record_events().
  2. Persists them to a JSONL ledger file via MetricsEventLedger.
  3. Aggregates them into a validated 17-field MetricsRow on demand via to_row().

No HTTP calls. No posting. No MetricsPoster. No entry point integration.

Public API
----------
    RunMetrics          — context-manager class
    RunMetricsError     — exception for RunMetrics-level failures
    _derive_status()    — module-level helper (exposed for testing)
    _build_item_name()  — module-level helper (exposed for testing)

Design invariants
-----------------
- Inert on import: importing this module writes no files.
- record_events() is all-or-nothing (delegates to MetricsEventLedger atomicity).
- to_row() calls aggregate_events() and build_run_row() from metrics_payload_builder.
- Status derived from item counts; never hard-coded by caller.
- agent_owner defaults to REQUIRED_AGENT_OWNER ("Babar Raza").
- No prompts, completions, API keys, or tokens stored or returned.
- close() is idempotent.
- to_row() is callable after close() (reads from in-memory event list).

Slice 6 of Agent Metrics Integration (METRICS-PLAN-001 v7.3).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Iterable

from commands.ops.metrics_schema import (
    REQUIRED_AGENT_OWNER,
    MetricsEvent,
    MetricsRow,
)
from commands.ops.metrics_event_ledger import (
    MetricsEventLedger,
    MetricsEventLedgerError,
)
from commands.ops.metrics_payload_builder import (
    aggregate_events,
    build_run_row,
)
from commands.ops.metrics_taxonomy_loader import (
    build_item_name as _build_item_name_from_display,
    resolve_agent_name,
    resolve_job_type,
    resolve_platform,
    resolve_product,
)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class RunMetricsError(Exception):
    """Raised for RunMetrics-level failures (invalid events, row validation, etc.)."""


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _derive_status(
    items_discovered: int,
    items_succeeded: int,
    items_failed: int,
) -> str:
    """Derive row status from item counts.

    Rules (in priority order):
    - ``"failure"``         if items_failed > 0 and items_succeeded == 0
    - ``"partial_success"`` if items_failed > 0 and items_succeeded > 0
    - ``"success"``         otherwise (items_failed == 0, including all-zero)
    """
    if items_failed > 0 and items_succeeded == 0:
        return "failure"
    if items_failed > 0 and items_succeeded > 0:
        return "partial_success"
    return "success"


def _build_item_name(product: str, platform: str) -> str:
    """Build the short item_name string from resolved display names.

    Delegates to ``metrics_taxonomy_loader.build_item_name``.
    Format: ``"{ProductShort} {Platform} Run"`` (target 10–14 chars)
    """
    return _build_item_name_from_display(product, platform)


# ---------------------------------------------------------------------------
# RunMetrics
# ---------------------------------------------------------------------------


class RunMetrics:
    """Context-manager that records MetricsEvents and produces a validated MetricsRow.

    Parameters
    ----------
    run_id:
        Unique identifier for this run (UUID string recommended).
    agent_name:
        Agent name for the MetricsRow (from taxonomy).
    job_type:
        Job type for the MetricsRow (from taxonomy).
    product:
        Product family token (e.g. ``"cells"``).
    platform:
        Platform token (e.g. ``"java"``).
    website:
        Website identifier (e.g. ``"aspose.org"``).
    website_section:
        Section within the website (``"Docs"``, ``"KB"``, ``"Blog"``, etc.).
    agent_owner:
        Agent owner string. Defaults to ``REQUIRED_AGENT_OWNER`` (``"Babar Raza"``).
    item_name:
        Explicit item_name for the row. If ``None``, derived automatically from
        website / section / product / platform / job_type.
    items_discovered:
        Total items scheduled for this run. May be overridden in ``to_row()``.
    items_failed:
        Items that errored. May be overridden in ``to_row()``.
    items_succeeded:
        Items completed successfully. May be overridden in ``to_row()``.
    ledger:
        Existing ``MetricsEventLedger`` to use. If ``None``, a new one is
        created using ``ledger_root`` and ``run_id``.
    ledger_root:
        Root directory for the JSONL ledger file. Ignored if ``ledger`` is
        provided. If ``None``, ``MetricsEventLedger`` uses its own default
        (``reports/metrics/events/``).
    work_slice_id:
        Optional work-slice identifier stored for context only.
    taxonomy_path:
        Reserved for future taxonomy lookup; not used in current slice.
    auto_flush:
        Retained for API compatibility; currently no-op (ledger flushes on
        each write by default).
    validate_rows:
        If ``True`` (default), ``to_row()`` validates the MetricsRow before
        returning it and raises ``RunMetricsError`` on failure.
    """

    def __init__(
        self,
        run_id: str,
        agent_name: str,
        job_type: str,
        product: str,
        platform: str,
        website: str,
        website_section: str,
        *,
        agent_owner: str = REQUIRED_AGENT_OWNER,
        item_name: str | None = None,
        items_discovered: int = 0,
        items_failed: int = 0,
        items_succeeded: int = 0,
        ledger: MetricsEventLedger | None = None,
        ledger_root: str | Path | None = None,
        work_slice_id: str | None = None,
        taxonomy_path: str | Path | None = None,
        auto_flush: bool = True,
        validate_rows: bool = True,
    ) -> None:
        self._run_id = run_id
        self._agent_name = resolve_agent_name(agent_name, taxonomy_path=taxonomy_path)
        self._agent_owner = agent_owner
        self._job_type = resolve_job_type(job_type, taxonomy_path=taxonomy_path)
        self._product = resolve_product(product, taxonomy_path=taxonomy_path)
        self._platform = resolve_platform(platform, taxonomy_path=taxonomy_path)
        self._website = website
        self._website_section = website_section
        self._item_name = item_name
        self._items_discovered = items_discovered
        self._items_failed = items_failed
        self._items_succeeded = items_succeeded
        self._work_slice_id = work_slice_id
        self._validate_rows = validate_rows

        if ledger is not None:
            self._ledger = ledger
            self._owns_ledger = False
        else:
            self._ledger = MetricsEventLedger(
                run_id=run_id,
                root_dir=ledger_root,
            )
            self._owns_ledger = True

        self._events: list[MetricsEvent] = []
        self._start_time: float | None = None
        self._closed = False

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def run_id(self) -> str:
        """The run identifier."""
        return self._run_id

    @property
    def event_count(self) -> int:
        """Number of events recorded so far (in-memory count)."""
        return len(self._events)

    @property
    def token_usage(self) -> int:
        """Sum of total_tokens across all in-memory events."""
        return aggregate_events(self._events).total_tokens

    @property
    def api_calls_count(self) -> int:
        """Sum of api_calls_count_delta across all in-memory events."""
        return aggregate_events(self._events).api_calls_count

    @property
    def run_duration_ms(self) -> int:
        """Wall-clock milliseconds since ``__enter__`` was called (0 if not entered)."""
        if self._start_time is None:
            return 0
        return max(0, int((time.monotonic() - self._start_time) * 1000))

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "RunMetrics":
        self._start_time = time.monotonic()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
        return None  # Never suppress exceptions

    # ------------------------------------------------------------------
    # Public write methods
    # ------------------------------------------------------------------

    def record_event(self, event: MetricsEvent) -> None:
        """Persist one MetricsEvent to the ledger and in-memory list.

        Raises
        ------
        RunMetricsError
            If closed, or if the ledger rejects the event.
        """
        if self._closed:
            raise RunMetricsError("RunMetrics is closed; cannot record events.")
        try:
            self._ledger.record_event(event)
        except MetricsEventLedgerError as exc:
            raise RunMetricsError(f"Ledger rejected event: {exc}") from exc
        self._events.append(event)

    def record_events(self, events: Iterable[MetricsEvent]) -> int:
        """Persist multiple MetricsEvents atomically (all-or-nothing).

        Validates all events first; if any is invalid, none are written.

        Returns
        -------
        int
            Number of events recorded.

        Raises
        ------
        RunMetricsError
            If closed, or if any event is invalid.
        """
        if self._closed:
            raise RunMetricsError("RunMetrics is closed; cannot record events.")
        event_list = list(events)
        try:
            count = self._ledger.record_events(event_list)
        except MetricsEventLedgerError as exc:
            raise RunMetricsError(f"Ledger rejected events: {exc}") from exc
        self._events.extend(event_list)
        return count

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    def to_row(
        self,
        *,
        items_discovered: int | None = None,
        items_failed: int | None = None,
        items_succeeded: int | None = None,
        run_duration_ms: int | None = None,
        timestamp: str | None = None,
    ) -> MetricsRow:
        """Aggregate in-memory events and return a validated MetricsRow.

        Uses ``aggregate_events()`` and ``build_run_row()`` from
        ``metrics_payload_builder``. Status is derived from item counts.

        Parameters override constructor values when provided.

        Does **not** post the row. Does **not** write the row to disk.

        Raises
        ------
        RunMetricsError
            If ``validate_rows=True`` and the constructed row fails
            ``validate_row()``.
        """
        disc = items_discovered if items_discovered is not None else self._items_discovered
        fail = items_failed if items_failed is not None else self._items_failed
        succ = items_succeeded if items_succeeded is not None else self._items_succeeded
        dur = run_duration_ms if run_duration_ms is not None else self.run_duration_ms

        status = _derive_status(disc, succ, fail)
        item_name = self._item_name or _build_item_name(self._product, self._platform)

        agg = aggregate_events(self._events)

        try:
            row = build_run_row(
                agent_name=self._agent_name,
                agent_owner=self._agent_owner,
                job_type=self._job_type,
                run_id=self._run_id,
                status=status,
                product=self._product,
                platform=self._platform,
                website=self._website,
                website_section=self._website_section,
                item_name=item_name,
                items_discovered=disc,
                items_failed=fail,
                items_succeeded=succ,
                run_duration_ms=dur,
                aggregate=agg,
                timestamp=timestamp,
            )
        except ValueError as exc:
            raise RunMetricsError(f"MetricsRow validation failed: {exc}") from exc

        return row

    def events_from_ledger(self) -> list[MetricsEvent]:
        """Read all persisted events from the JSONL ledger file.

        Flushes before reading. Returns ``[]`` if the file does not exist.

        Raises
        ------
        RunMetricsError
            If the ledger file is malformed or unreadable.
        """
        try:
            return self._ledger.read_events()
        except MetricsEventLedgerError as exc:
            raise RunMetricsError(f"Cannot read events from ledger: {exc}") from exc

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def flush(self) -> None:
        """Flush the ledger without closing. No-op if not yet opened."""
        self._ledger.flush()

    def close(self) -> None:
        """Flush and close the ledger. Safe to call multiple times.

        If the ledger was created internally (``_owns_ledger=True``), it is
        fully closed. If it was provided externally, only a flush is performed.
        """
        if self._owns_ledger:
            self._ledger.close()
        else:
            self._ledger.flush()
        self._closed = True
