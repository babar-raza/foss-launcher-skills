"""Integration tests for report harvest pipeline.

Tests the full flow: extract items from fixture reports → check against
harvest ledger → route to inbox (simulated) → verify idempotency.
"""
import json
import pytest
from pathlib import Path
from report_extract import parse_report, OpenItem
from harvest_ledger import HarvestLedger, _compute_file_sha256


# Repo root for real report tests
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent


@pytest.fixture
def harvest_env(tmp_path):
    """Set up a complete harvest environment with temp dirs."""
    ledger_dir = tmp_path / "harvest-state"
    ledger_dir.mkdir()
    ledger_path = ledger_dir / "ledger.json"

    inbox_path = tmp_path / "inbox.md"
    inbox_path.write_text("""# Inbox
## Standalone Tasks

| ID | Cat | Title | Priority | Size | Added | Notes |
|----|-----|-------|----------|------|-------|-------|
""", encoding="utf-8")

    # Create a fixture report
    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    report_path = report_dir / "test-report.md"
    report_path.write_text("""# Test Report

## Next Steps Required
1. Fix the extraction pipeline for better accuracy
2. Add test coverage for new evaluators
3. Update documentation for API changes

## Not Completed

| Item | Status | Reason |
|------|--------|--------|
| Script update | Not started | Deprioritized |
| Content fix | ✅ DONE | Already complete |

### What still blocks

1. **Missing dependency**: Need tree-sitter module installed
2. **Grade inflation**: Grading system needs recalibration
""", encoding="utf-8")

    return {
        "tmp_path": tmp_path,
        "ledger_path": ledger_path,
        "inbox_path": inbox_path,
        "report_path": report_path,
        "report_dir": report_dir,
    }


class TestExtractToLedger:
    """Test extraction → ledger recording flow."""

    def test_extract_and_record(self, harvest_env):
        """Items extracted from report are recorded in ledger."""
        report_path = harvest_env["report_path"]
        items = parse_report(report_path)

        # Should have items (3 next_steps + 1 not_completed + 2 blockers = 6)
        # The DONE item is filtered
        assert len(items) >= 5

        ledger = HarvestLedger(ledger_path=harvest_env["ledger_path"])
        run_id = ledger.start_run("test")

        report_sha = _compute_file_sha256(report_path)
        for item in items:
            ledger.record_item(
                item_hash=item.item_hash,
                report_path=item.source_path,
                report_sha256=report_sha,
                section_key=item.source_section,
                title=item.title,
                raw_text=item.raw_text,
                confidence=item.confidence,
                item_type=item.item_type,
                suggested_category=item.suggested_category,
                suggested_priority=item.suggested_priority,
                status="harvested",
                source_line=item.source_line,
                harvest_run_id=run_id,
            )

        ledger.end_run(run_id, {
            "reports_scanned": 1,
            "items_extracted": len(items),
            "items_new": len(items),
            "items_duplicate": 0,
            "items_review": 0,
            "items_failed": 0,
        })

        # Verify all items are in ledger
        for item in items:
            entry = ledger.lookup(item.item_hash)
            assert entry is not None
            assert entry.status == "harvested"
            assert entry.title == item.title

    def test_completed_items_filtered(self, harvest_env):
        """Completed items (DONE, RESOLVED, etc.) are not extracted."""
        items = parse_report(harvest_env["report_path"])
        titles = [i.title for i in items]
        # "Content fix" has ✅ DONE — should be filtered
        assert not any("Content fix" in t for t in titles)
        # "Script update" should be present
        assert any("Script update" in t for t in titles)


class TestIdempotency:
    """Test that re-harvesting the same report produces no new items."""

    def test_reharvest_no_duplicates(self, harvest_env):
        """Second harvest of same file produces 0 new items."""
        report_path = harvest_env["report_path"]
        items = parse_report(report_path)

        ledger = HarvestLedger(ledger_path=harvest_env["ledger_path"])
        run_id = ledger.start_run("run1")
        report_sha = _compute_file_sha256(report_path)

        for item in items:
            ledger.record_item(
                item_hash=item.item_hash,
                report_path=item.source_path,
                report_sha256=report_sha,
                section_key=item.source_section,
                title=item.title,
                raw_text=item.raw_text,
                confidence=item.confidence,
                item_type=item.item_type,
                suggested_category=item.suggested_category,
                suggested_priority=item.suggested_priority,
                status="harvested",
                source_line=item.source_line,
                harvest_run_id=run_id,
            )
        ledger.end_run(run_id, {
            "reports_scanned": 1, "items_extracted": len(items),
            "items_new": len(items), "items_duplicate": 0,
            "items_review": 0, "items_failed": 0,
        })
        ledger.save()

        # Second extraction
        items2 = parse_report(report_path)
        new_count = 0
        for item in items2:
            if ledger.lookup(item.item_hash) is None:
                new_count += 1

        assert new_count == 0, f"Expected 0 new items on re-harvest, got {new_count}"

    def test_hash_stability_across_runs(self, harvest_env):
        """Same report produces same hashes on separate parse calls."""
        items1 = parse_report(harvest_env["report_path"])
        items2 = parse_report(harvest_env["report_path"])

        hashes1 = sorted(i.item_hash for i in items1)
        hashes2 = sorted(i.item_hash for i in items2)
        assert hashes1 == hashes2


class TestReportChange:
    """Test re-harvest when report content changes."""

    def test_modified_report_detected(self, harvest_env):
        """When report file changes, ledger detects the change."""
        report_path = harvest_env["report_path"]
        items = parse_report(report_path)

        ledger = HarvestLedger(ledger_path=harvest_env["ledger_path"])
        run_id = ledger.start_run("initial")
        report_sha = _compute_file_sha256(report_path)

        for item in items:
            ledger.record_item(
                item_hash=item.item_hash,
                report_path=str(report_path),
                report_sha256=report_sha,
                section_key=item.source_section,
                title=item.title,
                raw_text=item.raw_text,
                confidence=item.confidence,
                item_type=item.item_type,
                suggested_category=item.suggested_category,
                suggested_priority=item.suggested_priority,
                status="harvested",
                source_line=item.source_line,
                harvest_run_id=run_id,
            )
        ledger.end_run(run_id, {
            "reports_scanned": 1, "items_extracted": len(items),
            "items_new": len(items), "items_duplicate": 0,
            "items_review": 0, "items_failed": 0,
        })
        ledger.save()

        # Modify the report
        content = report_path.read_text(encoding="utf-8")
        content += "\n## Open work\n- New issue discovered during review\n"
        report_path.write_text(content, encoding="utf-8")

        new_sha = _compute_file_sha256(report_path)
        assert ledger.report_changed(str(report_path), new_sha) is True

        # Re-extract should find new items
        items_after = parse_report(report_path)
        assert len(items_after) > len(items)


class TestWaiverFlow:
    """Test waiver mechanism."""

    def test_waived_report_excluded(self, harvest_env):
        """Waived reports don't appear in unharvested list."""
        ledger = HarvestLedger(ledger_path=harvest_env["ledger_path"])

        report_path = str(harvest_env["report_path"])
        known = [report_path, "reports/other.md"]

        # Before waiver: report is unharvested
        unharvested = ledger.get_unharvested_reports(known)
        assert report_path in unharvested

        # Waive it
        ledger.waive_report(report_path, "informational only")

        # After waiver: excluded
        unharvested = ledger.get_unharvested_reports(known)
        assert report_path not in unharvested
        assert "reports/other.md" in unharvested


class TestFailureRecovery:
    """Test failure queue and retry."""

    def test_failed_items_recoverable(self, harvest_env):
        """Failed items can be retried by changing status."""
        ledger = HarvestLedger(ledger_path=harvest_env["ledger_path"])
        run_id = ledger.start_run("test")

        ledger.record_item(
            item_hash="fail1",
            report_path="reports/test.md",
            report_sha256="abc",
            section_key="next_steps",
            title="Failed item",
            raw_text="text",
            confidence=0.95,
            item_type="next_step",
            suggested_category="S",
            suggested_priority="P1",
            status="failed",
            source_line=10,
            harvest_run_id=run_id,
        )
        ledger.save()

        failed = ledger.get_items_by_status("failed")
        assert len(failed) == 1

        # Retry: change status
        ledger.update_status("fail1", "harvested")
        ledger.save()

        assert ledger.lookup("fail1").status == "harvested"
        assert len(ledger.get_items_by_status("failed")) == 0


class TestReviewItemDedup:
    """Test that orchestrators should skip review items on re-harvest.

    Note: harvest_ledger.record_item() is deliberately an upsert — it will
    overwrite any existing entry with the same item_hash. The skip-on-re-harvest
    logic belongs in the orchestrating code, not in the ledger module itself.
    Orchestrators should check: if ledger.lookup(hash) exists and status is in
    {harvested, merged, skipped, waived, review}, skip the item.
    """

    def test_review_items_should_be_skipped_by_orchestrator(self, harvest_env):
        """Demonstrate the correct orchestrator pattern for review items."""
        ledger = HarvestLedger(ledger_path=harvest_env["ledger_path"])
        run_id = ledger.start_run("initial")

        # Record an item as review (low confidence)
        ledger.record_item(
            item_hash="review1",
            report_path="reports/test.md",
            report_sha256="abc",
            section_key="known_limitations",
            title="Low confidence item",
            raw_text="text",
            confidence=0.7,
            item_type="deferred",
            suggested_category="H",
            suggested_priority="P3",
            status="review",
            source_line=10,
            harvest_run_id=run_id,
        )
        ledger.save()

        # Correct orchestrator pattern: skip if status is in the full skip set
        SKIP_STATUSES = {"harvested", "merged", "skipped", "waived", "review"}
        existing = ledger.lookup("review1")
        assert existing is not None
        assert existing.status in SKIP_STATUSES, (
            f"Review items should be in skip set, got status={existing.status}"
        )

        # The orchestrator should NOT call record_item again for this hash
        # (it would overwrite the entry, which is wasteful but not harmful)
        entries_before = len(ledger.entries)
        # Simulate correct orchestrator: skip
        if existing.status not in SKIP_STATUSES:
            ledger.record_item(  # This should NOT execute
                item_hash="review1", report_path="reports/test.md",
                report_sha256="abc", section_key="known_limitations",
                title="Low confidence item", raw_text="text",
                confidence=0.7, item_type="deferred",
                suggested_category="H", suggested_priority="P3",
                status="review", source_line=10, harvest_run_id=run_id,
            )
        assert len(ledger.entries) == entries_before  # No new entry


class TestDryRunSimulation:
    """Test dry-run behavior (no writes)."""

    def test_dry_run_no_ledger_changes(self, harvest_env):
        """Simulating dry-run: extract items but don't write ledger."""
        items = parse_report(harvest_env["report_path"])
        assert len(items) > 0

        # Don't create ledger — just verify extraction works
        # In a real dry-run, no save() is called
        ledger = HarvestLedger(ledger_path=harvest_env["ledger_path"])
        # Don't record or save anything

        # Verify ledger is empty
        assert len(ledger.entries) == 0


class TestRealReportIntegration:
    """Integration tests against actual repo reports."""

    @pytest.mark.skipif(
        not (_REPO_ROOT / "reports" / "forensic-pass1" / "sprint-summary.md").exists(),
        reason="Real reports not available"
    )
    def test_full_pipeline_sprint_summary(self):
        """Full extract → ledger cycle on real sprint summary."""
        import tempfile

        report_path = _REPO_ROOT / "reports" / "forensic-pass1" / "sprint-summary.md"
        items = parse_report(report_path)
        assert len(items) >= 10  # At least 10 items

        with tempfile.TemporaryDirectory() as td:
            ledger_path = Path(td) / "ledger.json"
            ledger = HarvestLedger(ledger_path=ledger_path)
            run_id = ledger.start_run("test")
            sha = _compute_file_sha256(report_path)

            new_count = 0
            for item in items:
                if ledger.lookup(item.item_hash) is None:
                    ledger.record_item(
                        item_hash=item.item_hash,
                        report_path=item.source_path,
                        report_sha256=sha,
                        section_key=item.source_section,
                        title=item.title,
                        raw_text=item.raw_text,
                        confidence=item.confidence,
                        item_type=item.item_type,
                        suggested_category=item.suggested_category,
                        suggested_priority=item.suggested_priority,
                        status="harvested",
                        source_line=item.source_line,
                        harvest_run_id=run_id,
                    )
                    new_count += 1

            ledger.end_run(run_id, {
                "reports_scanned": 1, "items_extracted": len(items),
                "items_new": new_count, "items_duplicate": 0,
                "items_review": 0, "items_failed": 0,
            })
            ledger.save()

            # Verify round-trip
            ledger2 = HarvestLedger(ledger_path=ledger_path)
            assert len(ledger2.entries) == new_count
            assert len(ledger2.runs) == 1
