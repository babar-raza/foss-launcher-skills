"""Tests for harvest_ledger.py — ledger CRUD, idempotency, runs, waivers, change detection."""
from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timezone, timedelta

from harvest_ledger import HarvestLedger, LedgerEntry, RunRecord, configure, _compute_file_sha256


@pytest.fixture
def ledger(tmp_path):
    """Create a HarvestLedger backed by a temp directory."""
    ledger_dir = tmp_path / "harvest-state"
    ledger_dir.mkdir()
    ledger_path = ledger_dir / "ledger.json"
    return HarvestLedger(ledger_path=ledger_path)


def _make_item_kwargs(item_hash="abc123", **overrides):
    """Helper to produce keyword args for record_item."""
    defaults = dict(
        item_hash=item_hash,
        report_path="reports/test.md",
        report_sha256="deadbeef" * 8,
        section_key="not_completed",
        title="Test item",
        raw_text="Full text here",
        confidence=0.95,
        item_type="not_completed",
        suggested_category="S",
        suggested_priority="P1",
        status="harvested",
        source_line=42,
        harvest_run_id="harvest-20260421-120000",
    )
    defaults.update(overrides)
    return defaults


class TestLedgerCRUD:
    """6 tests: Create, read, update, lookup."""

    def test_create_entry(self, ledger):
        entry = ledger.record_item(**_make_item_kwargs())
        assert isinstance(entry, LedgerEntry)
        assert entry.item_hash == "abc123"
        assert entry.status == "harvested"

    def test_lookup_found(self, ledger):
        ledger.record_item(**_make_item_kwargs())
        found = ledger.lookup("abc123")
        assert found is not None
        assert found.title == "Test item"

    def test_lookup_miss(self, ledger):
        assert ledger.lookup("nonexistent") is None

    def test_update_status(self, ledger):
        ledger.record_item(**_make_item_kwargs())
        ledger.update_status("abc123", "waived")
        assert ledger.lookup("abc123").status == "waived"

    def test_update_status_invalid(self, ledger):
        ledger.record_item(**_make_item_kwargs())
        with pytest.raises(ValueError):
            ledger.update_status("abc123", "invalid_status")

    def test_save_and_reload(self, ledger, tmp_path):
        ledger.record_item(**_make_item_kwargs())
        ledger.save()
        # Reload from disk
        ledger2 = HarvestLedger(ledger_path=ledger._path)
        assert ledger2.lookup("abc123") is not None
        assert ledger2.lookup("abc123").title == "Test item"


class TestIdempotency:
    """4 tests: Duplicate detection."""

    def test_same_hash_overwrites(self, ledger):
        ledger.record_item(**_make_item_kwargs(status="harvested"))
        ledger.record_item(**_make_item_kwargs(status="review"))
        assert ledger.lookup("abc123").status == "review"

    def test_different_hash_separate(self, ledger):
        ledger.record_item(**_make_item_kwargs(item_hash="hash1"))
        ledger.record_item(**_make_item_kwargs(item_hash="hash2", title="Other item"))
        assert ledger.lookup("hash1") is not None
        assert ledger.lookup("hash2") is not None

    def test_save_reload_preserves_all(self, ledger):
        ledger.record_item(**_make_item_kwargs(item_hash="h1"))
        ledger.record_item(**_make_item_kwargs(item_hash="h2", title="Second"))
        ledger.save()
        ledger2 = HarvestLedger(ledger_path=ledger._path)
        assert len(ledger2.entries) == 2

    def test_get_items_by_status(self, ledger):
        ledger.record_item(**_make_item_kwargs(item_hash="h1", status="harvested"))
        ledger.record_item(**_make_item_kwargs(item_hash="h2", status="failed"))
        ledger.record_item(**_make_item_kwargs(item_hash="h3", status="harvested"))
        assert len(ledger.get_items_by_status("harvested")) == 2
        assert len(ledger.get_items_by_status("failed")) == 1


class TestStatusTransitions:
    """5 tests: Status transitions."""

    def test_harvested_to_waived(self, ledger):
        ledger.record_item(**_make_item_kwargs(status="harvested"))
        ledger.update_status("abc123", "waived")
        assert ledger.lookup("abc123").status == "waived"

    def test_review_to_harvested(self, ledger):
        ledger.record_item(**_make_item_kwargs(status="review"))
        ledger.update_status("abc123", "harvested")
        assert ledger.lookup("abc123").status == "harvested"

    def test_failed_to_harvested_retry(self, ledger):
        ledger.record_item(**_make_item_kwargs(status="failed"))
        ledger.update_status("abc123", "harvested")
        assert ledger.lookup("abc123").status == "harvested"

    def test_update_sets_updated_at(self, ledger):
        ledger.record_item(**_make_item_kwargs())
        old_updated = ledger.lookup("abc123").updated_at
        ledger.update_status("abc123", "review")
        new_updated = ledger.lookup("abc123").updated_at
        assert new_updated >= old_updated

    def test_update_nonexistent_raises(self, ledger):
        with pytest.raises(KeyError):
            ledger.update_status("nonexistent", "harvested")


class TestRunRecords:
    """3 tests: Run lifecycle."""

    def test_start_run(self, ledger):
        run_id = ledger.start_run("manual")
        assert run_id.startswith("harvest-")
        assert run_id in ledger.runs

    def test_end_run(self, ledger):
        run_id = ledger.start_run("auto:test")
        ledger.end_run(run_id, {"reports_scanned": 3, "items_new": 5, "items_extracted": 5,
                                 "items_duplicate": 0, "items_review": 1, "items_failed": 0})
        record = ledger.runs[run_id]
        assert record.completed_at != ""
        assert record.reports_scanned == 3
        assert record.items_new == 5

    def test_multiple_runs(self, ledger):
        t1 = datetime(2026, 4, 21, 12, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 4, 21, 12, 0, 1, tzinfo=timezone.utc)
        with patch("harvest_ledger.datetime") as mock_dt:
            mock_dt.now.return_value = t1
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            r1 = ledger.start_run("run1")
            ledger.end_run(r1, {"reports_scanned": 1, "items_extracted": 1, "items_new": 1,
                                "items_duplicate": 0, "items_review": 0, "items_failed": 0})
            mock_dt.now.return_value = t2
            r2 = ledger.start_run("run2")
            ledger.end_run(r2, {"reports_scanned": 2, "items_extracted": 2, "items_new": 2,
                                "items_duplicate": 0, "items_review": 0, "items_failed": 0})
        assert r1 != r2
        assert len(ledger.runs) == 2


class TestWaivers:
    """3 tests: Waiver management."""

    def test_waive_and_check(self, ledger):
        ledger.waive_report("reports/old.md", "informational only")
        assert ledger.is_waived("reports/old.md") is True

    def test_not_waived(self, ledger):
        assert ledger.is_waived("reports/new.md") is False

    def test_waived_excluded_from_unharvested(self, ledger):
        ledger.waive_report("reports/waived.md", "not relevant")
        unharvested = ledger.get_unharvested_reports(["reports/waived.md", "reports/new.md"])
        assert "reports/waived.md" not in unharvested
        assert "reports/new.md" in unharvested


class TestReportChange:
    """4 tests: File change detection."""

    def test_no_change(self, ledger):
        ledger.record_item(**_make_item_kwargs(report_sha256="aaa"))
        assert ledger.report_changed("reports/test.md", "aaa") is False

    def test_changed(self, ledger):
        ledger.record_item(**_make_item_kwargs(report_sha256="aaa"))
        assert ledger.report_changed("reports/test.md", "bbb") is True

    def test_new_report(self, ledger):
        # No entries for this report -> not "changed" (it's new)
        assert ledger.report_changed("reports/brand-new.md", "ccc") is False

    def test_compute_file_sha256(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world", encoding="utf-8")
        sha = _compute_file_sha256(f)
        assert len(sha) == 64
        # Verify deterministic
        assert _compute_file_sha256(f) == sha
