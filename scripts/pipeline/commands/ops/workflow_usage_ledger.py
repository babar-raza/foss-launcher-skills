"""Local durable ledger for WorkflowUsageEvent records.

Writes WorkflowUsageEvent objects as JSONL to
reports/gha-cost-telemetry/usage_events.jsonl (one file, append-only, unlike
the per-run metrics event ledger this mirrors -- cost telemetry is a single
ongoing time series, not per-agent-run). Mirrors
scripts/pipeline/commands/ops/metrics_event_ledger.py's mechanics
(validate-before-write, all-or-nothing batch append, path-traversal guard)
without reusing its run_id-per-file model, which doesn't fit a recurring
weekly collector.

MT069-2026-09-16-GHA-MINUTES-REARCHITECTURE, PHB-03.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from lib.workflow_usage_schema import (
    ValidationResult,
    WorkflowUsageEvent,
    validate_event,
)

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_LEDGER_PATH = _DEFAULT_REPO_ROOT / "reports" / "gha-cost-telemetry" / "usage_events.jsonl"
LEDGER_PATH = _DEFAULT_LEDGER_PATH


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override LEDGER_PATH for testing -- the DI seam convention this repo
    uses in place of monkeypatching internals directly (AGENTS.md 16)."""
    global LEDGER_PATH
    LEDGER_PATH = (
        Path(repo_root) / "reports" / "gha-cost-telemetry" / "usage_events.jsonl"
        if repo_root is not None else _DEFAULT_LEDGER_PATH
    )


class WorkflowUsageLedgerError(Exception):
    """Raised for ledger-level failures (validation, path traversal)."""


def record_events(events: Iterable[WorkflowUsageEvent], *, path: "Path | None" = None) -> int:
    """Validate all events, then append them atomically (all-or-nothing).

    Returns the number of events written. Raises WorkflowUsageLedgerError if
    any event is invalid -- none are written in that case."""
    target = path if path is not None else LEDGER_PATH
    event_list = list(events)

    errors_found: "list[str]" = []
    for i, ev in enumerate(event_list):
        result = validate_event(ev)
        if not result.valid:
            errors_found.append(f"Event[{i}]: {result.errors}")
    if errors_found:
        raise WorkflowUsageLedgerError(
            f"record_events() aborted -- invalid events detected (none written): {errors_found}"
        )
    if not event_list:
        return 0

    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        for ev in event_list:
            fh.write(json.dumps(_event_to_plain_dict(ev), separators=(",", ":")) + "\n")
    return len(event_list)


def _event_to_plain_dict(event: WorkflowUsageEvent) -> dict:
    return asdict(event)


def load_events(path: "Path | None" = None) -> "list[WorkflowUsageEvent]":
    """Read all events from the ledger. Returns [] if the file does not exist."""
    target = path if path is not None else LEDGER_PATH
    if not target.exists():
        return []

    events: "list[WorkflowUsageEvent]" = []
    with target.open(encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:
                raise WorkflowUsageLedgerError(f"Malformed JSON on line {lineno} of {target}: {exc}") from exc
            if not isinstance(data, dict):
                raise WorkflowUsageLedgerError(
                    f"Expected JSON object on line {lineno} of {target}, got {type(data).__name__}"
                )
            try:
                events.append(WorkflowUsageEvent(**data))
            except TypeError as exc:
                raise WorkflowUsageLedgerError(f"Cannot reconstruct WorkflowUsageEvent from line {lineno}: {exc}") from exc
    return events


def validate_ledger_file(path: "Path | None" = None) -> ValidationResult:
    """Validate every event currently in the ledger file."""
    target = path if path is not None else LEDGER_PATH
    if not target.exists():
        return ValidationResult(valid=True, errors=[])
    try:
        events = load_events(target)
    except WorkflowUsageLedgerError as exc:
        return ValidationResult(valid=False, errors=[str(exc)])
    errors: "list[str]" = []
    for i, ev in enumerate(events):
        result = validate_event(ev)
        if not result.valid:
            errors.extend(f"Event[{i}]: {e}" for e in result.errors)
    return ValidationResult(valid=len(errors) == 0, errors=errors)


def aggregate_by_workflow(
    events: "list[WorkflowUsageEvent]", *, period_start: "str | None" = None, period_end: "str | None" = None,
) -> "dict[str, dict]":
    """Sum total_minutes/run_count per (repo, workflow_name, runner_os) key,
    optionally filtered to events whose period_start/period_end fall exactly
    within [period_start, period_end] (inclusive) when both are given.

    Returns {f"{repo}::{workflow_name}::{runner_os}": {"total_minutes": ...,
    "run_count": ..., "repo": ..., "workflow_name": ..., "runner_os": ...}}."""
    filtered = events
    if period_start is not None and period_end is not None:
        filtered = [e for e in events if e.period_start >= period_start and e.period_end <= period_end]

    out: "dict[str, dict]" = {}
    for e in filtered:
        key = f"{e.repo}::{e.workflow_name}::{e.runner_os}"
        row = out.setdefault(key, {
            "repo": e.repo, "workflow_name": e.workflow_name, "runner_os": e.runner_os,
            "total_minutes": 0.0, "run_count": 0,
        })
        row["total_minutes"] += e.total_minutes
        row["run_count"] += e.run_count
    return out
