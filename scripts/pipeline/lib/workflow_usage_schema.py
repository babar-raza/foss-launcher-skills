"""Workflow usage/cost telemetry schema and validation.

Defines inert data structures (WorkflowUsageEvent) and validation helpers for
the recurring GHA cost-telemetry capability (MT069-2026-09-16-GHA-MINUTES-
REARCHITECTURE, PHB-03; design: reports/plan_state/MT069-2026-09-16-GHA-
MINUTES-REARCHITECTURE/design/cost_telemetry_proposal.md). Mirrors the
mechanics of scripts/pipeline/commands/ops/metrics_schema.py (validated
event -> JSONL ledger -> aggregate) -- deliberately NOT MetricsEvent/MetricsRow
themselves, which are LLM-call-specific (17 fixed fields tied to the
product/platform taxonomy). This is a different taxonomy: one event per
(repo, workflow, runner_os) per collection period.

No HTTP calls, no gh api invocation, no file I/O here -- pure schema and
validation only, exactly matching metrics_schema.py's own division of
responsibility.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

VALID_METHODS = frozenset({"proxy_reconstruction_v1"})
VALID_RUNNER_OS = frozenset({"linux", "windows", "macos", "self-hosted", "mixed"})

_SAFE_WORKFLOW_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,200}$")
_SAFE_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


@dataclass
class ValidationResult:
    valid: bool
    errors: "list[str]"


@dataclass
class WorkflowUsageEvent:
    """One workflow's proxy-reconstructed usage for one collection period,
    for one (repo, workflow_name, runner_os) triple -- matches the shape of
    the real Actions usage export table (TC-04's usage_dataset.json), which
    already splits a workflow into separate rows per runner OS."""

    event_id: str
    repo: str
    workflow_name: str
    runner_os: str
    period_start: str  # ISO-8601 date, e.g. "2026-09-01"
    period_end: str
    total_minutes: float
    run_count: int
    collected_at: str  # ISO-8601 timestamp
    method: str = "proxy_reconstruction_v1"


def generate_event_id() -> str:
    return str(uuid.uuid4())


def now_iso8601() -> str:
    return datetime.now(timezone.utc).isoformat()


def event_to_dict(event: WorkflowUsageEvent) -> dict:
    return asdict(event)


def is_valid_iso8601_date_or_datetime(value: str) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        datetime.fromisoformat(value)
        return True
    except (ValueError, TypeError):
        return False


def validate_event(event: WorkflowUsageEvent) -> ValidationResult:
    """Validate a WorkflowUsageEvent. Returns a ValidationResult."""
    errors: "list[str]" = []

    for name in ("event_id", "repo", "workflow_name", "runner_os", "period_start",
                 "period_end", "collected_at", "method"):
        value = getattr(event, name)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{name} must be a non-empty string")

    if isinstance(event.repo, str) and not _SAFE_REPO_RE.match(event.repo):
        errors.append(f"repo {event.repo!r} must look like 'Owner/name'")

    if isinstance(event.workflow_name, str) and not _SAFE_WORKFLOW_NAME_RE.match(event.workflow_name):
        errors.append(f"workflow_name {event.workflow_name!r} contains unsafe characters")

    if event.runner_os not in VALID_RUNNER_OS:
        errors.append(f"runner_os must be one of {sorted(VALID_RUNNER_OS)}, got {event.runner_os!r}")

    if event.method not in VALID_METHODS:
        errors.append(f"method must be one of {sorted(VALID_METHODS)}, got {event.method!r}")

    for name in ("period_start", "period_end", "collected_at"):
        value = getattr(event, name)
        if isinstance(value, str) and value.strip() and not is_valid_iso8601_date_or_datetime(value):
            errors.append(f"{name} {value!r} is not a valid ISO-8601 date/datetime")

    if not isinstance(event.total_minutes, (int, float)) or event.total_minutes < 0:
        errors.append(f"total_minutes must be a non-negative number, got {event.total_minutes!r}")

    if not isinstance(event.run_count, int) or event.run_count < 0:
        errors.append(f"run_count must be a non-negative int, got {event.run_count!r}")

    if (isinstance(event.period_start, str) and isinstance(event.period_end, str)
            and is_valid_iso8601_date_or_datetime(event.period_start)
            and is_valid_iso8601_date_or_datetime(event.period_end)):
        if event.period_end < event.period_start:
            errors.append(f"period_end {event.period_end!r} is before period_start {event.period_start!r}")

    return ValidationResult(valid=len(errors) == 0, errors=errors)
