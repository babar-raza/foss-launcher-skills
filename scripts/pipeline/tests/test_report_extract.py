"""Tests for report_extract.py -- open item extraction from markdown reports.

Tests section detection, item extraction (tables, numbered lists, bullets,
status scan), completion filtering, confidence scoring, category suggestion,
stable hashing, real report integration, and edge cases.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from report_extract import (
    OpenItem,
    _compute_item_hash,
    _is_completed,
    _normalize,
    _suggest_category,
    parse_report,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "harvest"
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def _fixture(name: str) -> Path:
    return _FIXTURES / name


# ---------------------------------------------------------------------------
# TestSectionDetection
# ---------------------------------------------------------------------------


class TestSectionDetection:
    """8 tests: Each pattern group detected; unknown headers ignored."""

    def test_not_completed_detected(self):
        items = parse_report(_fixture("sprint_report.md"))
        not_completed = [i for i in items if i.item_type == "not_completed"]
        assert len(not_completed) >= 1, "Should find items under Not Completed"

    def test_next_steps_detected(self):
        items = parse_report(_fixture("healing_report.md"))
        next_steps = [i for i in items if i.item_type == "next_step"]
        assert len(next_steps) >= 1, "Should find items under Next Steps Required"

    def test_deferred_detected(self):
        items = parse_report(_fixture("execution_report.md"))
        deferred = [i for i in items if i.item_type == "deferred"]
        assert len(deferred) >= 1, "Should find DEFERRED marker"

    def test_human_action_detected(self):
        items = parse_report(_fixture("system_heal_report.md"))
        human = [i for i in items if i.item_type == "human_action"]
        assert len(human) >= 1, "Should find Required Human Actions"

    def test_blockers_detected(self):
        items = parse_report(_fixture("sprint_report.md"))
        blockers = [i for i in items if i.item_type == "blocker"]
        assert len(blockers) >= 1, "Should find What still blocks"

    def test_escalated_detected(self):
        items = parse_report(_fixture("system_heal_report.md"))
        escalated = [i for i in items if i.item_type == "escalated"]
        assert len(escalated) >= 1, "Should find Files Escalated"

    def test_future_work_detected(self):
        items = parse_report(_fixture("system_heal_report.md"))
        deferred = [i for i in items if i.item_type == "deferred"]
        assert len(deferred) >= 1, "Should find Known limitations"

    def test_unknown_headers_ignored(self):
        items = parse_report(_fixture("sprint_report.md"))
        achieved = [i for i in items if i.source_section == "1. What We Achieved"]
        assert len(achieved) == 0, "Unknown headers should not produce items"


# ---------------------------------------------------------------------------
# TestItemExtraction
# ---------------------------------------------------------------------------


class TestItemExtraction:
    """10 tests: Tables, numbered lists, bullets, multiline."""

    def test_table_extraction(self):
        items = parse_report(_fixture("sprint_report.md"))
        not_completed = [i for i in items if i.item_type == "not_completed"]
        assert len(not_completed) == 2, "Table should yield 2 non-done items"

    def test_numbered_list_extraction(self):
        items = parse_report(_fixture("healing_report.md"))
        next_steps = [i for i in items if i.item_type == "next_step"]
        assert len(next_steps) == 4, "Numbered list should yield 4 items"

    def test_bullet_list_extraction(self):
        items = parse_report(_fixture("system_heal_report.md"))
        escalated = [i for i in items if i.item_type == "escalated"]
        assert len(escalated) == 2, "Bullet list should yield 2 items"

    def test_status_scan_deferred(self):
        items = parse_report(_fixture("execution_report.md"))
        deferred = [i for i in items if i.item_type == "deferred"]
        assert len(deferred) == 1, "Status scan should find 1 DEFERRED item"

    def test_table_header_row_skipped(self):
        items = parse_report(_fixture("sprint_report.md"))
        titles = [i.title for i in items]
        assert "Item" not in titles, "Table header row should be skipped"
        assert "Status" not in titles, "Table header row should be skipped"

    def test_item_type_correct(self):
        items = parse_report(_fixture("system_heal_report.md"))
        types = {i.item_type for i in items}
        assert "human_action" in types
        assert "escalated" in types
        assert "deferred" in types

    def test_source_line_populated(self):
        items = parse_report(_fixture("healing_report.md"))
        for item in items:
            assert item.source_line > 0, f"Line number should be positive: {item}"

    def test_source_section_populated(self):
        items = parse_report(_fixture("healing_report.md"))
        for item in items:
            assert item.source_section, f"Section should be populated: {item}"

    def test_title_truncated_at_120(self):
        for name in ["sprint_report.md", "healing_report.md", "system_heal_report.md"]:
            items = parse_report(_fixture(name))
            for item in items:
                assert len(item.title) <= 120, (
                    f"Title exceeds 120 chars: {item.title!r}"
                )

    def test_multiple_sections_combined(self):
        items = parse_report(_fixture("system_heal_report.md"))
        sections = {i.source_section for i in items}
        assert len(sections) >= 3, (
            f"system_heal has 3 sections; got {sections}"
        )


# ---------------------------------------------------------------------------
# TestCompletionFiltering
# ---------------------------------------------------------------------------


class TestCompletionFiltering:
    """6 tests: Completed items excluded."""

    def test_done_excluded(self):
        assert _is_completed("DONE"), "DONE should be completed"

    def test_resolved_excluded(self):
        assert _is_completed("RESOLVED"), "RESOLVED should be completed"

    def test_verified_excluded(self):
        assert _is_completed("VERIFIED"), "VERIFIED should be completed"

    def test_checkbox_excluded(self):
        assert _is_completed("[x] some task"), "[x] should be completed"

    def test_all_done_report_empty(self):
        items = parse_report(_fixture("all_done_report.md"))
        assert len(items) == 0, "All-done report should have 0 items"

    def test_mixed_section_partial(self):
        items = parse_report(_fixture("sprint_report.md"))
        not_completed = [i for i in items if i.item_type == "not_completed"]
        assert len(not_completed) == 2, (
            "Sprint Not Completed has 3 rows but 1 is DONE; expect 2"
        )


# ---------------------------------------------------------------------------
# TestConfidenceScoring
# ---------------------------------------------------------------------------


class TestConfidenceScoring:
    """5 tests: Structural >=0.9; semantic 0.6-0.8."""

    def test_not_completed_confidence(self):
        items = parse_report(_fixture("sprint_report.md"))
        not_completed = [i for i in items if i.item_type == "not_completed"]
        for item in not_completed:
            assert item.confidence == 0.95

    def test_next_steps_confidence(self):
        items = parse_report(_fixture("healing_report.md"))
        for item in items:
            assert item.confidence == 0.95

    def test_deferred_confidence(self):
        items = parse_report(_fixture("execution_report.md"))
        deferred = [i for i in items if i.item_type == "deferred"]
        for item in deferred:
            assert item.confidence == 0.90

    def test_not_proven_confidence(self):
        from report_extract import _SECTION_PATTERNS
        not_proven = [p for p in _SECTION_PATTERNS if p.item_type == "not_proven"]
        assert len(not_proven) == 1
        assert not_proven[0].base_confidence == 0.85

    def test_min_confidence_filter(self):
        items = parse_report(_fixture("system_heal_report.md"))
        high = [i for i in items if i.confidence >= 0.90]
        low = [i for i in items if i.confidence < 0.90]
        assert len(high) >= 1, "Should have high-confidence items"
        assert len(low) >= 1, "Should have lower-confidence items"


# ---------------------------------------------------------------------------
# TestCategorySuggestion
# ---------------------------------------------------------------------------


class TestCategorySuggestion:
    """5 tests: Keyword heuristics."""

    def test_script_category(self):
        assert _suggest_category("script changes needed") == "S"

    def test_content_category(self):
        assert _suggest_category("content page update") == "C"

    def test_test_category(self):
        assert _suggest_category("add test coverage") == "T"

    def test_governance_category(self):
        assert _suggest_category("update AGENTS.md") == "G"

    def test_default_category(self):
        assert _suggest_category("something unrelated") == "H"


# ---------------------------------------------------------------------------
# TestStableHashing
# ---------------------------------------------------------------------------


class TestStableHashing:
    """5 tests: Hash stability."""

    def test_same_input_same_hash(self):
        h1 = _compute_item_hash("a.md", "sec", "title")
        h2 = _compute_item_hash("a.md", "sec", "title")
        assert h1 == h2, "Deterministic: same inputs must produce same hash"

    def test_title_change_new_hash(self):
        h1 = _compute_item_hash("a.md", "sec", "title")
        h2 = _compute_item_hash("a.md", "sec", "different title")
        assert h1 != h2

    def test_section_change_new_hash(self):
        h1 = _compute_item_hash("a.md", "sec", "title")
        h2 = _compute_item_hash("a.md", "other", "title")
        assert h1 != h2

    def test_path_change_new_hash(self):
        h1 = _compute_item_hash("a.md", "sec", "title")
        h2 = _compute_item_hash("b.md", "sec", "title")
        assert h1 != h2

    def test_line_number_no_hash_change(self):
        h1 = _compute_item_hash("a.md", "sec", "title")
        h2 = _compute_item_hash("a.md", "sec", "title")
        assert h1 == h2, "Line number changes should not affect hash"


# ---------------------------------------------------------------------------
# TestRealReports
# ---------------------------------------------------------------------------


class TestRealReports:
    """3 tests: Known item counts from actual report files."""

    _sprint = _REPO_ROOT / "reports" / "forensic-pass1" / "sprint-summary.md"
    _healing = _REPO_ROOT / "reports" / "healing-2026-04-15-summary.md"
    _execution = _REPO_ROOT / "reports" / "HEALING_PLAN_EXECUTION_REPORT.md"

    @pytest.mark.skipif(
        not (_REPO_ROOT / "reports" / "forensic-pass1" / "sprint-summary.md").exists(),
        reason="Real report not present on disk",
    )
    def test_sprint_summary(self):
        items = parse_report(self._sprint)
        assert len(items) == 17, f"Expected 17 items, got {len(items)}"

    @pytest.mark.skipif(
        not (_REPO_ROOT / "reports" / "healing-2026-04-15-summary.md").exists(),
        reason="Real report not present on disk",
    )
    def test_healing_summary(self):
        items = parse_report(self._healing)
        assert len(items) == 4, f"Expected 4 items, got {len(items)}"

    @pytest.mark.skipif(
        not (_REPO_ROOT / "reports" / "HEALING_PLAN_EXECUTION_REPORT.md").exists(),
        reason="Real report not present on disk",
    )
    def test_execution_report(self):
        items = parse_report(self._execution)
        assert len(items) == 5, f"Expected 5 items, got {len(items)}"


# ---------------------------------------------------------------------------
# TestEdgeCases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """4 tests."""

    def test_empty_file(self):
        items = parse_report(_fixture("empty_report.md"))
        assert len(items) == 0

    def test_no_unresolved(self):
        items = parse_report(_fixture("all_done_report.md"))
        assert len(items) == 0

    def test_malformed_graceful(self):
        items = parse_report(_fixture("malformed_report.md"))
        assert len(items) == 0, "Malformed report should not crash"

    def test_nonexistent_file(self):
        items = parse_report("nonexistent_file_that_does_not_exist.md")
        assert items == [], "Missing file should return empty list"
