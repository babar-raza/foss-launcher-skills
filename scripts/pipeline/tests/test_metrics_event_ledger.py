"""Tests for MetricsEventLedger (metrics_event_ledger.py).

45 test scenarios covering:
- JSONL writes (record_event, record_events)
- Validation before write (valid events pass, invalid events rejected)
- All-or-nothing record_events() atomicity
- Path traversal prevention (run_id and root_dir)
- File lifecycle (append vs truncate, exists, close, context manager)
- read_events() and validate_file() round-trips
- load_events() and validate_event_file() module-level helpers
- Empty file / non-existent file handling
- Secret safety (events with secrets are rejected)
- validate_before_write=False bypass
- MetricsEventLedgerError semantics

Slice 5 of Agent Metrics Integration (METRICS-PLAN-001 v7.1).
"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import pytest

# Ensure scripts/pipeline is on sys.path
_PIPELINE_ROOT = Path(__file__).resolve().parent.parent
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from commands.ops.metrics_event_ledger import (
    MetricsEventLedger,
    MetricsEventLedgerError,
    load_events,
    validate_event_file,
)
from commands.ops.metrics_schema import (
    MetricsEvent,
    generate_event_id,
    now_iso8601,
    validate_event,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_event(
    call_site_id: str = "CS-001",
    status: str = "success",
    request_type: str = "chat",
    total_tokens: int = 100,
    http_status: int = 200,
) -> MetricsEvent:
    """Return a fully valid MetricsEvent."""
    return MetricsEvent(
        event_id=generate_event_id(),
        call_site_id=call_site_id,
        endpoint="https://llm.professionalize.com/v1/chat/completions",
        request_type=request_type,
        status=status,
        prompt_tokens=70,
        completion_tokens=30,
        total_tokens=total_tokens,
        api_calls_count_delta=1,
        timestamp=now_iso8601(),
        http_status=http_status,
        latency_ms=350,
    )


def _invalid_event() -> MetricsEvent:
    """Return a MetricsEvent that fails schema validation (blank call_site_id)."""
    return MetricsEvent(
        event_id=generate_event_id(),
        call_site_id="",          # INVALID — blank
        endpoint="https://llm.professionalize.com/v1/chat/completions",
        request_type="chat",
        status="success",
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        api_calls_count_delta=1,
        timestamp=now_iso8601(),
    )


@pytest.fixture
def tmp_ledger_dir(tmp_path):
    """Return a tmp directory for ledger JSONL files."""
    d = tmp_path / "events"
    d.mkdir()
    return d


def _make_ledger(tmp_ledger_dir, run_id=None, **kwargs) -> MetricsEventLedger:
    rid = run_id or str(uuid.uuid4())
    return MetricsEventLedger(rid, root_dir=tmp_ledger_dir, **kwargs)


# ===========================================================================
# TC-S5-L001–L005: Constructor and basic properties
# ===========================================================================


def test_constructor_valid_run_id(tmp_ledger_dir):
    """TC-S5-L001: Constructor accepts a valid UUID run_id."""
    rid = str(uuid.uuid4())
    ledger = MetricsEventLedger(rid, root_dir=tmp_ledger_dir)
    assert ledger.run_id == rid


def test_event_path_reflects_run_id(tmp_ledger_dir):
    """TC-S5-L002: event_path contains run_id and ends with .jsonl."""
    rid = "test-run-001"
    ledger = MetricsEventLedger(rid, root_dir=tmp_ledger_dir)
    assert ledger.event_path.name == f"{rid}.jsonl"
    assert str(ledger.event_path).endswith(".jsonl")


def test_exists_returns_false_before_any_write(tmp_ledger_dir):
    """TC-S5-L003: exists() returns False before any event is written."""
    ledger = _make_ledger(tmp_ledger_dir)
    assert not ledger.exists()


def test_exists_returns_true_after_write(tmp_ledger_dir):
    """TC-S5-L004: exists() returns True after a successful record_event()."""
    ledger = _make_ledger(tmp_ledger_dir)
    ledger.record_event(_valid_event())
    assert ledger.exists()


def test_allow_create_dirs_true_creates_nested_dir(tmp_path):
    """TC-S5-L005: allow_create_dirs=True creates the parent directory."""
    nested = tmp_path / "deep" / "nested" / "events"
    assert not nested.exists()
    ledger = MetricsEventLedger("run-001", root_dir=nested, allow_create_dirs=True)
    ledger.record_event(_valid_event())
    assert nested.exists()
    ledger.close()


# ===========================================================================
# TC-S5-L006–L010: record_event() basic behaviour
# ===========================================================================


def test_record_event_writes_jsonl_line(tmp_ledger_dir):
    """TC-S5-L006: record_event() writes exactly one JSON line per event."""
    ledger = _make_ledger(tmp_ledger_dir)
    ev = _valid_event()
    ledger.record_event(ev)
    ledger.close()

    lines = [l for l in ledger.event_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["event_id"] == ev.event_id


def test_record_event_multiple_events_multiple_lines(tmp_ledger_dir):
    """TC-S5-L007: Multiple record_event() calls produce multiple lines."""
    ledger = _make_ledger(tmp_ledger_dir)
    for _ in range(5):
        ledger.record_event(_valid_event())
    ledger.close()

    lines = [l for l in ledger.event_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 5


def test_record_event_each_line_is_valid_json(tmp_ledger_dir):
    """TC-S5-L008: Each JSONL line is valid JSON."""
    ledger = _make_ledger(tmp_ledger_dir)
    for _ in range(3):
        ledger.record_event(_valid_event())
    ledger.close()

    for line in ledger.event_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            json.loads(line)  # must not raise


def test_record_event_valid_event_passes(tmp_ledger_dir):
    """TC-S5-L009: A fully valid event is accepted without error."""
    ledger = _make_ledger(tmp_ledger_dir)
    ev = _valid_event(call_site_id="CS-004", request_type="embedding", total_tokens=256)
    ledger.record_event(ev)  # must not raise
    ledger.close()
    assert ledger.exists()


def test_record_event_rejects_invalid_event(tmp_ledger_dir):
    """TC-S5-L010: An invalid event raises MetricsEventLedgerError."""
    ledger = _make_ledger(tmp_ledger_dir)
    with pytest.raises(MetricsEventLedgerError, match="Invalid MetricsEvent"):
        ledger.record_event(_invalid_event())
    ledger.close()


# ===========================================================================
# TC-S5-L011–L015: record_events() atomicity
# ===========================================================================


def test_record_events_writes_all_events(tmp_ledger_dir):
    """TC-S5-L011: record_events() writes all events on success."""
    ledger = _make_ledger(tmp_ledger_dir)
    events = [_valid_event() for _ in range(4)]
    count = ledger.record_events(events)
    ledger.close()
    assert count == 4
    lines = [l for l in ledger.event_path.read_text("utf-8").splitlines() if l.strip()]
    assert len(lines) == 4


def test_record_events_all_or_nothing_no_write_on_invalid(tmp_ledger_dir):
    """TC-S5-L012: If any event is invalid, record_events() writes nothing."""
    ledger = _make_ledger(tmp_ledger_dir)
    events = [_valid_event(), _invalid_event(), _valid_event()]
    with pytest.raises(MetricsEventLedgerError):
        ledger.record_events(events)
    ledger.close()
    # File must not exist (or be empty)
    if ledger.exists():
        lines = [l for l in ledger.event_path.read_text("utf-8").splitlines() if l.strip()]
        assert len(lines) == 0


def test_record_events_all_or_nothing_preserves_prior_events(tmp_ledger_dir):
    """TC-S5-L013: Failed record_events() does not corrupt previously written events."""
    ledger = _make_ledger(tmp_ledger_dir)
    ledger.record_event(_valid_event())  # 1 good event already written
    good_count_before = len([
        l for l in ledger.event_path.read_text("utf-8").splitlines() if l.strip()
    ])

    with pytest.raises(MetricsEventLedgerError):
        ledger.record_events([_valid_event(), _invalid_event()])  # must not add any

    ledger.close()
    lines = [l for l in ledger.event_path.read_text("utf-8").splitlines() if l.strip()]
    assert len(lines) == good_count_before


def test_record_events_returns_count(tmp_ledger_dir):
    """TC-S5-L014: record_events() returns the number of events written."""
    ledger = _make_ledger(tmp_ledger_dir)
    n = ledger.record_events([_valid_event() for _ in range(7)])
    assert n == 7
    ledger.close()


def test_record_events_empty_list_writes_nothing(tmp_ledger_dir):
    """TC-S5-L015: record_events([]) writes nothing and returns 0."""
    ledger = _make_ledger(tmp_ledger_dir)
    n = ledger.record_events([])
    assert n == 0
    ledger.close()
    assert not ledger.exists()


# ===========================================================================
# TC-S5-L016–L019: validate_before_write=False
# ===========================================================================


def test_validate_before_write_false_allows_invalid_event(tmp_ledger_dir):
    """TC-S5-L016: validate_before_write=False skips validation, writes invalid event."""
    ledger = _make_ledger(tmp_ledger_dir, validate_before_write=False)
    ledger.record_event(_invalid_event())  # must not raise
    ledger.close()
    lines = [l for l in ledger.event_path.read_text("utf-8").splitlines() if l.strip()]
    assert len(lines) == 1


def test_validate_before_write_false_allows_invalid_batch(tmp_ledger_dir):
    """TC-S5-L017: validate_before_write=False allows mixed batch without error."""
    ledger = _make_ledger(tmp_ledger_dir, validate_before_write=False)
    n = ledger.record_events([_valid_event(), _invalid_event()])
    assert n == 2
    ledger.close()


def test_validate_before_write_true_rejects_status_unknown(tmp_ledger_dir):
    """TC-S5-L018: validate_before_write=True rejects event with unknown status."""
    ev = _valid_event()
    object.__setattr__(ev, "status", "unknown_status")
    ledger = _make_ledger(tmp_ledger_dir)
    with pytest.raises(MetricsEventLedgerError):
        ledger.record_event(ev)
    ledger.close()


def test_validate_before_write_true_rejects_negative_tokens(tmp_ledger_dir):
    """TC-S5-L019: validate_before_write=True rejects event with negative total_tokens."""
    ev = _valid_event()
    object.__setattr__(ev, "total_tokens", -5)
    ledger = _make_ledger(tmp_ledger_dir)
    with pytest.raises(MetricsEventLedgerError):
        ledger.record_event(ev)
    ledger.close()


# ===========================================================================
# TC-S5-L020–L023: append vs truncate
# ===========================================================================


def test_append_true_accumulates_events_across_instances(tmp_ledger_dir):
    """TC-S5-L020: append=True accumulates events across separate ledger instances."""
    rid = "append-test-run"
    ledger1 = MetricsEventLedger(rid, root_dir=tmp_ledger_dir, append=True)
    ledger1.record_event(_valid_event())
    ledger1.close()

    ledger2 = MetricsEventLedger(rid, root_dir=tmp_ledger_dir, append=True)
    ledger2.record_event(_valid_event())
    ledger2.close()

    lines = [l for l in (tmp_ledger_dir / f"{rid}.jsonl").read_text("utf-8").splitlines() if l.strip()]
    assert len(lines) == 2


def test_append_false_truncates_file(tmp_ledger_dir):
    """TC-S5-L021: append=False truncates the file on first write."""
    rid = "truncate-test-run"
    ledger1 = MetricsEventLedger(rid, root_dir=tmp_ledger_dir, append=True)
    for _ in range(3):
        ledger1.record_event(_valid_event())
    ledger1.close()

    ledger2 = MetricsEventLedger(rid, root_dir=tmp_ledger_dir, append=False)
    ledger2.record_event(_valid_event())
    ledger2.close()

    lines = [l for l in (tmp_ledger_dir / f"{rid}.jsonl").read_text("utf-8").splitlines() if l.strip()]
    assert len(lines) == 1


def test_append_true_single_session_accumulates(tmp_ledger_dir):
    """TC-S5-L022: append=True within single instance accumulates all writes."""
    ledger = _make_ledger(tmp_ledger_dir, append=True)
    for _ in range(10):
        ledger.record_event(_valid_event())
    ledger.close()
    lines = [l for l in ledger.event_path.read_text("utf-8").splitlines() if l.strip()]
    assert len(lines) == 10


def test_append_default_is_true(tmp_ledger_dir):
    """TC-S5-L023: Default append behavior appends (no truncation)."""
    rid = "default-append"
    for _ in range(2):
        ledger = MetricsEventLedger(rid, root_dir=tmp_ledger_dir)
        ledger.record_event(_valid_event())
        ledger.close()
    lines = [l for l in (tmp_ledger_dir / f"{rid}.jsonl").read_text("utf-8").splitlines() if l.strip()]
    assert len(lines) == 2


# ===========================================================================
# TC-S5-L024–L026: read_events() round-trip
# ===========================================================================


def test_read_events_returns_same_events(tmp_ledger_dir):
    """TC-S5-L024: read_events() returns events equal to what was written."""
    ledger = _make_ledger(tmp_ledger_dir)
    written = [_valid_event(call_site_id=f"CS-00{i}") for i in range(1, 4)]
    for ev in written:
        ledger.record_event(ev)

    read_back = ledger.read_events()
    assert len(read_back) == len(written)
    for orig, back in zip(written, read_back):
        assert orig.event_id == back.event_id
        assert orig.call_site_id == back.call_site_id
    ledger.close()


def test_read_events_empty_file_returns_empty_list(tmp_ledger_dir):
    """TC-S5-L025: read_events() returns [] when no events have been written."""
    ledger = _make_ledger(tmp_ledger_dir)
    assert ledger.read_events() == []
    ledger.close()


def test_read_events_after_close(tmp_ledger_dir):
    """TC-S5-L026: load_events() can read after the ledger is closed."""
    ledger = _make_ledger(tmp_ledger_dir)
    ev = _valid_event()
    ledger.record_event(ev)
    path = ledger.event_path
    ledger.close()

    events = load_events(path)
    assert len(events) == 1
    assert events[0].event_id == ev.event_id


# ===========================================================================
# TC-S5-L027–L030: validate_file() and validate_event_file()
# ===========================================================================


def test_validate_file_valid_events_returns_true(tmp_ledger_dir):
    """TC-S5-L027: validate_file() returns valid=True when all events are valid."""
    ledger = _make_ledger(tmp_ledger_dir)
    for _ in range(3):
        ledger.record_event(_valid_event())
    ledger.close()

    result = ledger.validate_file()
    assert result.valid, result.errors


def test_validate_event_file_nonexistent_returns_true(tmp_ledger_dir):
    """TC-S5-L028: validate_event_file() for non-existent file returns valid=True."""
    result = validate_event_file(tmp_ledger_dir / "nonexistent.jsonl")
    assert result.valid


def test_validate_event_file_malformed_json_returns_false(tmp_ledger_dir):
    """TC-S5-L029: validate_event_file() returns valid=False for malformed JSON."""
    bad_file = tmp_ledger_dir / "bad.jsonl"
    bad_file.write_text("not json\n", encoding="utf-8")
    result = validate_event_file(bad_file)
    assert not result.valid
    assert any("malformed" in e.lower() or "JSON" in e for e in result.errors)


def test_validate_event_file_invalid_event_returns_false(tmp_ledger_dir):
    """TC-S5-L030: validate_event_file() returns valid=False for a schema-invalid event."""
    ledger = _make_ledger(tmp_ledger_dir, validate_before_write=False)
    ledger.record_event(_invalid_event())
    ledger.close()

    result = validate_event_file(ledger.event_path)
    assert not result.valid


# ===========================================================================
# TC-S5-L031–L034: load_events() module helper
# ===========================================================================


def test_load_events_nonexistent_returns_empty(tmp_ledger_dir):
    """TC-S5-L031: load_events() returns [] for a non-existent file."""
    events = load_events(tmp_ledger_dir / "missing.jsonl")
    assert events == []


def test_load_events_skips_blank_lines(tmp_ledger_dir):
    """TC-S5-L032: load_events() skips blank lines without error."""
    f = tmp_ledger_dir / "sparse.jsonl"
    ledger = MetricsEventLedger("sparse", root_dir=tmp_ledger_dir)
    ev = _valid_event()
    ledger.record_event(ev)
    ledger.close()

    # Inject blank lines
    content = f.read_text("utf-8")
    f.write_text("\n" + content + "\n\n", encoding="utf-8")

    events = load_events(f)
    assert len(events) == 1


def test_load_events_raises_on_malformed_json(tmp_ledger_dir):
    """TC-S5-L033: load_events() raises MetricsEventLedgerError on malformed JSON."""
    bad = tmp_ledger_dir / "bad.jsonl"
    bad.write_text("{broken\n", encoding="utf-8")
    with pytest.raises(MetricsEventLedgerError, match="[Mm]alformed"):
        load_events(bad)


def test_load_events_returns_metricsevents(tmp_ledger_dir):
    """TC-S5-L034: load_events() returns MetricsEvent instances."""
    ledger = _make_ledger(tmp_ledger_dir)
    ledger.record_event(_valid_event())
    ledger.close()

    events = load_events(ledger.event_path)
    assert all(isinstance(ev, MetricsEvent) for ev in events)


# ===========================================================================
# TC-S5-L035–L038: Path traversal prevention
# ===========================================================================


def test_run_id_with_slash_raises(tmp_ledger_dir):
    """TC-S5-L035: run_id containing '/' raises MetricsEventLedgerError."""
    with pytest.raises(MetricsEventLedgerError):
        MetricsEventLedger("../../etc/passwd", root_dir=tmp_ledger_dir)


def test_run_id_with_backslash_raises(tmp_ledger_dir):
    """TC-S5-L036: run_id containing '\\' raises MetricsEventLedgerError."""
    with pytest.raises(MetricsEventLedgerError):
        MetricsEventLedger("sub\\dir", root_dir=tmp_ledger_dir)


def test_run_id_with_dotdot_raises(tmp_ledger_dir):
    """TC-S5-L037: run_id containing '..' raises MetricsEventLedgerError."""
    with pytest.raises(MetricsEventLedgerError):
        MetricsEventLedger("run..escape", root_dir=tmp_ledger_dir)


def test_run_id_empty_string_raises(tmp_ledger_dir):
    """TC-S5-L038: Empty run_id raises MetricsEventLedgerError."""
    with pytest.raises(MetricsEventLedgerError):
        MetricsEventLedger("", root_dir=tmp_ledger_dir)


# ===========================================================================
# TC-S5-L039–L040: Lifecycle — close and context manager
# ===========================================================================


def test_close_is_idempotent(tmp_ledger_dir):
    """TC-S5-L039: close() can be called multiple times without error."""
    ledger = _make_ledger(tmp_ledger_dir)
    ledger.record_event(_valid_event())
    ledger.close()
    ledger.close()  # second call must not raise


def test_context_manager_closes_ledger(tmp_ledger_dir):
    """TC-S5-L040: Using 'with' statement closes the ledger on exit."""
    with _make_ledger(tmp_ledger_dir) as ledger:
        ledger.record_event(_valid_event())
        path = ledger.event_path
    # File must exist after context exit
    assert path.exists()
    # Writing after close must raise
    with pytest.raises(MetricsEventLedgerError):
        ledger.record_event(_valid_event())


# ===========================================================================
# TC-S5-L041: record_event after close raises
# ===========================================================================


def test_record_event_after_close_raises(tmp_ledger_dir):
    """TC-S5-L041: record_event() after close() raises MetricsEventLedgerError."""
    ledger = _make_ledger(tmp_ledger_dir)
    ledger.close()
    with pytest.raises(MetricsEventLedgerError, match="closed"):
        ledger.record_event(_valid_event())


# ===========================================================================
# TC-S5-L042: record_events after close raises
# ===========================================================================


def test_record_events_after_close_raises(tmp_ledger_dir):
    """TC-S5-L042: record_events() after close() raises MetricsEventLedgerError."""
    ledger = _make_ledger(tmp_ledger_dir)
    ledger.close()
    with pytest.raises(MetricsEventLedgerError, match="closed"):
        ledger.record_events([_valid_event()])


# ===========================================================================
# TC-S5-L043: allow_create_dirs=False raises when dir missing
# ===========================================================================


def test_allow_create_dirs_false_raises_when_dir_missing(tmp_path):
    """TC-S5-L043: allow_create_dirs=False raises if root_dir doesn't exist."""
    missing = tmp_path / "nonexistent_events"
    ledger = MetricsEventLedger("run-xyz", root_dir=missing, allow_create_dirs=False)
    with pytest.raises(MetricsEventLedgerError):
        ledger.record_event(_valid_event())
    ledger.close()


# ===========================================================================
# TC-S5-L044: Secret safety — endpoint with API key is rejected
# ===========================================================================


def test_secret_in_endpoint_rejected(tmp_ledger_dir):
    """TC-S5-L044: Event with API key in endpoint is rejected by validation."""
    ev = MetricsEvent(
        event_id=generate_event_id(),
        call_site_id="CS-001",
        endpoint="https://llm.professionalize.com/v1?api_key=sk-abc123456789xyz",
        request_type="chat",
        status="success",
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        api_calls_count_delta=1,
        timestamp=now_iso8601(),
    )
    # validate_event should catch it
    result = validate_event(ev)
    assert not result.valid
    # MetricsEventLedger should reject it too
    ledger = _make_ledger(tmp_ledger_dir)
    with pytest.raises(MetricsEventLedgerError):
        ledger.record_event(ev)
    ledger.close()


# ===========================================================================
# TC-S5-L045: JSONL ordering preserved
# ===========================================================================


def test_jsonl_ordering_preserved(tmp_ledger_dir):
    """TC-S5-L045: Events are written and read back in insertion order."""
    ledger = _make_ledger(tmp_ledger_dir)
    ids = []
    for i in range(6):
        ev = _valid_event(call_site_id=f"CS-{i:03d}")
        ledger.record_event(ev)
        ids.append(ev.event_id)
    ledger.close()

    read_back = load_events(ledger.event_path)
    assert [e.event_id for e in read_back] == ids
