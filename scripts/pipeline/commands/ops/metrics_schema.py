# Adapted from aspose.org
"""Metrics schema definitions and validation for agent metrics capture.

Defines inert data structures (MetricsEvent, MetricsRow) and validation
helpers for the aspose.org agent metrics system. No HTTP calls, no posting,
no event writing — pure schema and validation only.

Slice 1 of Agent Metrics Integration (METRICS-PLAN-001).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone


# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

VALID_EVENT_STATUSES = frozenset({"success", "failure", "timeout", "retry"})

VALID_REQUEST_TYPES = frozenset(
    {"chat", "embedding", "translation", "seo", "structured_json", "other"}
)

VALID_ROW_STATUSES = frozenset({"success", "partial_success", "failure"})

REQUIRED_AGENT_OWNER = "Babar Raza"

_SECRET_LIKE_PATTERN = re.compile(
    r"(sk-[A-Za-z0-9]{10,})"
    r"|(ghp_[A-Za-z0-9]{10,})"
    r"|(ghu_[A-Za-z0-9]{10,})"
    r"|(AIzaSy[A-Za-z0-9_-]{10,})"
    r"|(Bearer\s+[A-Za-z0-9._-]{20,})"
    r"|([?&](api_key|token|key|access_token)=[^\s&]{8,})",
    re.IGNORECASE,
)


# --------------------------------------------------------------------------- #
# Data Structures
# --------------------------------------------------------------------------- #


@dataclass
class MetricsEvent:
    """A single captured professionalize API call event."""

    event_id: str
    call_site_id: str
    endpoint: str
    request_type: str
    status: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    api_calls_count_delta: int
    timestamp: str
    parent_run_id: str | None = None
    work_slice_id: str | None = None
    agent_name: str | None = None
    job_type: str | None = None
    model: str | None = None
    http_status: int | None = None
    latency_ms: int | None = None
    redacted_error_summary: str | None = None


@dataclass
class MetricsRow:
    """The 17-field Google Sheet payload for one completed work slice."""

    timestamp: str
    agent_name: str
    agent_owner: str
    job_type: str
    run_id: str
    status: str
    product: str
    platform: str
    website: str
    website_section: str
    item_name: str
    items_discovered: int
    items_failed: int
    items_succeeded: int
    run_duration_ms: int
    token_usage: int
    api_calls_count: int


@dataclass
class ValidationResult:
    """Outcome of a validation check."""

    valid: bool
    errors: list[str]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def is_valid_iso8601(value: str) -> bool:
    """Return True if *value* can be parsed as ISO-8601 datetime."""
    if not isinstance(value, str) or not value.strip():
        return False
    for fmt in (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S%z",
    ):
        try:
            datetime.strptime(value, fmt)
            return True
        except ValueError:
            continue
    # Fallback: Python 3.11+ fromisoformat handles most ISO strings
    try:
        datetime.fromisoformat(value)
        return True
    except (ValueError, TypeError):
        return False


def redact_secret_like_values(value: str) -> str:
    """Replace secret-like substrings in *value* with ``[REDACTED]``."""
    if not isinstance(value, str):
        return value
    return _SECRET_LIKE_PATTERN.sub("[REDACTED]", value)


def generate_event_id() -> str:
    """Return a new UUID4 string for use as an event_id."""
    return str(uuid.uuid4())


def generate_run_id() -> str:
    """Return a new UUID4 string for use as a run_id."""
    return str(uuid.uuid4())


def now_iso8601() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def event_to_dict(event: MetricsEvent) -> dict:
    """Serialize a MetricsEvent to a plain dict."""
    return asdict(event)


def row_to_dict(row: MetricsRow) -> dict:
    """Serialize a MetricsRow to a plain dict."""
    return asdict(row)


# --------------------------------------------------------------------------- #
# Validation — MetricsEvent
# --------------------------------------------------------------------------- #


def validate_event(event: MetricsEvent) -> ValidationResult:
    """Validate a MetricsEvent. Returns a ValidationResult."""
    errors: list[str] = []

    # Required non-blank strings
    for name in ("event_id", "call_site_id", "endpoint", "request_type", "status", "timestamp"):
        val = getattr(event, name, None)
        if not isinstance(val, str) or not val.strip():
            errors.append(f"{name} must be a non-blank string")

    # Enum checks
    if isinstance(event.status, str) and event.status not in VALID_EVENT_STATUSES:
        errors.append(
            f"status must be one of {sorted(VALID_EVENT_STATUSES)}, got '{event.status}'"
        )

    if isinstance(event.request_type, str) and event.request_type not in VALID_REQUEST_TYPES:
        errors.append(
            f"request_type must be one of {sorted(VALID_REQUEST_TYPES)}, got '{event.request_type}'"
        )

    # Non-negative integer checks
    for name in ("prompt_tokens", "completion_tokens", "total_tokens", "api_calls_count_delta"):
        val = getattr(event, name, None)
        if not isinstance(val, int) or val < 0:
            errors.append(f"{name} must be a non-negative integer")

    # Optional non-negative
    if event.latency_ms is not None and (not isinstance(event.latency_ms, int) or event.latency_ms < 0):
        errors.append("latency_ms must be None or a non-negative integer")

    # Timestamp format
    if isinstance(event.timestamp, str) and event.timestamp.strip():
        if not is_valid_iso8601(event.timestamp):
            errors.append("timestamp must be ISO-8601 parseable")

    # Endpoint must not contain secrets
    if isinstance(event.endpoint, str) and _SECRET_LIKE_PATTERN.search(event.endpoint):
        errors.append("endpoint must not contain API keys or token query parameters")

    return ValidationResult(valid=len(errors) == 0, errors=errors)


# --------------------------------------------------------------------------- #
# Validation — MetricsRow
# --------------------------------------------------------------------------- #

_ROW_FIELD_NAMES = tuple(f.name for f in fields(MetricsRow))
METRICS_ROW_FIELD_COUNT = len(_ROW_FIELD_NAMES)  # 17


def validate_row(row: MetricsRow) -> ValidationResult:
    """Validate a MetricsRow. Returns a ValidationResult."""
    errors: list[str] = []

    # All 17 fields present (dataclass guarantees this structurally, but check values)
    row_dict = asdict(row)
    if len(row_dict) != METRICS_ROW_FIELD_COUNT:
        errors.append(f"Expected {METRICS_ROW_FIELD_COUNT} fields, got {len(row_dict)}")

    for name in row_dict:
        if row_dict[name] is None:
            errors.append(f"{name} must not be None")

    # Non-blank string fields
    for name in (
        "timestamp", "agent_name", "agent_owner", "job_type", "run_id",
        "status", "product", "platform", "website", "website_section", "item_name",
    ):
        val = getattr(row, name, None)
        if not isinstance(val, str) or not val.strip():
            errors.append(f"{name} must be a non-blank string")

    # agent_owner
    if isinstance(row.agent_owner, str) and row.agent_owner.strip() != REQUIRED_AGENT_OWNER:
        errors.append(f"agent_owner must be '{REQUIRED_AGENT_OWNER}'")

    # Status enum
    if isinstance(row.status, str) and row.status not in VALID_ROW_STATUSES:
        errors.append(
            f"status must be one of {sorted(VALID_ROW_STATUSES)}, got '{row.status}'"
        )

    # Non-negative integer counters
    for name in (
        "items_discovered", "items_failed", "items_succeeded",
        "run_duration_ms", "token_usage", "api_calls_count",
    ):
        val = getattr(row, name, None)
        if not isinstance(val, int) or val < 0:
            errors.append(f"{name} must be a non-negative integer")

    # items_succeeded + items_failed <= items_discovered
    if (
        isinstance(row.items_succeeded, int)
        and isinstance(row.items_failed, int)
        and isinstance(row.items_discovered, int)
        and row.items_succeeded >= 0
        and row.items_failed >= 0
        and row.items_discovered >= 0
    ):
        if row.items_succeeded + row.items_failed > row.items_discovered:
            errors.append(
                "items_succeeded + items_failed must not exceed items_discovered"
            )

    # Timestamp format
    if isinstance(row.timestamp, str) and row.timestamp.strip():
        if not is_valid_iso8601(row.timestamp):
            errors.append("timestamp must be ISO-8601 parseable")

    return ValidationResult(valid=len(errors) == 0, errors=errors)


def validate_test_row(row: MetricsRow) -> ValidationResult:
    """Validate a MetricsRow for test-mode posting rules."""
    result = validate_row(row)
    errors = list(result.errors)

    if row.job_type != "test":
        errors.append("test-mode row must have job_type='test'")

    if isinstance(row.item_name, str) and not row.item_name.startswith("[TEST] "):
        errors.append("test-mode row item_name must start with '[TEST] '")

    return ValidationResult(valid=len(errors) == 0, errors=errors)
