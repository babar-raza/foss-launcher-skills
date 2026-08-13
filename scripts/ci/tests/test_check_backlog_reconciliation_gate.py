"""Tests for scripts/ci/checks/check_backlog_reconciliation_gate.py (MT030-2026-08-13, Step 32)."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

_CHECKS_DIR = Path(__file__).resolve().parent.parent / "checks"
if str(_CHECKS_DIR) not in sys.path:
    sys.path.insert(0, str(_CHECKS_DIR))

import check_backlog_reconciliation_gate as gate  # noqa: E402


_TABLE_HEADER = (
    "| ID | Cat | Effect | Title | Status | Priority | Size | Wave | Score | Plan | Blocker | Updated |\n"
    "|----|-----|--------|-------|--------|----------|------|------|-------|------|---------|---------|\n"
)


def _table(rows: list[str]) -> str:
    return "## Active\n\n" + _TABLE_HEADER + "\n".join(rows) + "\n"


class TestFindNewlyClosedKnowledgeRows:
    def test_row_absent_at_head_and_closed_in_staged_is_newly_closed(self):
        head = _table([])
        staged = _table([
            "| PDF-JAVA-REFRESH-003 | knowledge | HIGH | pdf/java drift | CLOSED | P1 | L | 0 | 0 | plan | — | 2026-08-13 |",
        ])
        result = gate.find_newly_closed_knowledge_rows(head, staged)
        assert len(result) == 1
        assert result[0]["id"] == "PDF-JAVA-REFRESH-003"

    def test_row_queued_at_head_and_closed_in_staged_is_newly_closed(self):
        head = _table([
            "| PDF-JAVA-REFRESH-003 | knowledge | HIGH | pdf/java drift | queued | P1 | L | 0 | 0 | — | — | 2026-08-01 |",
        ])
        staged = _table([
            "| PDF-JAVA-REFRESH-003 | knowledge | HIGH | pdf/java drift | CLOSED | P1 | L | 0 | 0 | plan | — | 2026-08-13 |",
        ])
        result = gate.find_newly_closed_knowledge_rows(head, staged)
        assert len(result) == 1

    def test_row_already_closed_at_head_is_not_newly_closed(self):
        head = _table([
            "| PDF-JAVA-REFRESH-003 | knowledge | HIGH | pdf/java drift | CLOSED | P1 | L | 0 | 0 | plan | — | 2026-08-01 |",
        ])
        staged = _table([
            "| PDF-JAVA-REFRESH-003 | knowledge | HIGH | pdf/java drift | CLOSED | P1 | L | 0 | 0 | plan | — | 2026-08-13 |",
        ])
        result = gate.find_newly_closed_knowledge_rows(head, staged)
        assert result == []

    def test_non_knowledge_row_ignored(self):
        head = _table([])
        staged = _table([
            "| SOME-OPS-ROW | ops | LOW | Not knowledge | CLOSED | P4 | XS | 0 | 1 | plan | — | 2026-08-13 |",
        ])
        result = gate.find_newly_closed_knowledge_rows(head, staged)
        assert result == []

    def test_still_queued_row_is_not_newly_closed(self):
        head = _table([])
        staged = _table([
            "| PDF-JAVA-REFRESH-003 | knowledge | HIGH | pdf/java drift | queued | P1 | L | 0 | 0 | — | — | 2026-08-13 |",
        ])
        result = gate.find_newly_closed_knowledge_rows(head, staged)
        assert result == []


class TestCheckBacklogClosure:
    def test_fails_open_when_no_knowledge_state_entry(self, tmp_path):
        """Never punish a product nothing has ever recorded state for."""
        head = _table([])
        staged = _table([
            "| NEW-PRODUCT-001 | knowledge | HIGH | cad/net first refresh | CLOSED | P1 | L | 0 | 0 | plan | — | 2026-08-13 |",
        ])
        with mock.patch.object(gate, "read_state", return_value=None):
            blocked = gate.check_backlog_closure(head, staged, repo_root=tmp_path)
        assert blocked == []

    def test_blocks_closure_with_no_truth_audit_record(self, tmp_path):
        head = _table([])
        staged = _table([
            "| PDF-JAVA-REFRESH-003 | knowledge | HIGH | pdf/java drift | CLOSED | P1 | L | 0 | 0 | plan | — | 2026-08-13 |",
        ])
        with mock.patch.object(gate, "read_state", return_value={"family": "pdf", "platform": "java"}), \
             mock.patch.object(gate, "_has_override", return_value=False):
            blocked = gate.check_backlog_closure(head, staged, repo_root=tmp_path)
        assert len(blocked) == 1
        assert blocked[0][0] == "PDF-JAVA-REFRESH-003"

    def test_blocks_closure_with_failing_truth_audit(self, tmp_path):
        head = _table([])
        staged = _table([
            "| PDF-JAVA-REFRESH-003 | knowledge | HIGH | pdf/java drift | CLOSED | P1 | L | 0 | 0 | plan | — | 2026-08-13 |",
        ])
        state = {"family": "pdf", "platform": "java",
                 "truth_audit": {"verdict": "FAIL", "fail_count": 1, "report_path": "x.md"}}
        with mock.patch.object(gate, "read_state", return_value=state), \
             mock.patch.object(gate, "_has_override", return_value=False):
            blocked = gate.check_backlog_closure(head, staged, repo_root=tmp_path)
        assert len(blocked) == 1

    def test_passes_closure_with_passing_truth_audit(self, tmp_path):
        head = _table([])
        staged = _table([
            "| PDF-JAVA-REFRESH-003 | knowledge | HIGH | pdf/java drift | CLOSED | P1 | L | 0 | 0 | plan | — | 2026-08-13 |",
        ])
        state = {"family": "pdf", "platform": "java",
                 "truth_audit": {"verdict": "PASS", "fail_count": 0, "report_path": "x.md"}}
        with mock.patch.object(gate, "read_state", return_value=state):
            blocked = gate.check_backlog_closure(head, staged, repo_root=tmp_path)
        assert blocked == []

    def test_governed_override_clears_the_block(self, tmp_path):
        head = _table([])
        staged = _table([
            "| PDF-JAVA-REFRESH-003 | knowledge | HIGH | pdf/java drift | CLOSED | P1 | L | 0 | 0 | plan | — | 2026-08-13 |",
        ])
        with mock.patch.object(gate, "read_state", return_value={"family": "pdf", "platform": "java"}), \
             mock.patch.object(gate, "_has_override", return_value=True):
            blocked = gate.check_backlog_closure(head, staged, repo_root=tmp_path)
        assert blocked == []

    def test_unresolvable_product_key_is_skipped_not_blocked(self, tmp_path):
        head = _table([])
        staged = _table([
            "| G-99 | knowledge | LOW | A row with no product-key title | CLOSED | P4 | XS | 0 | 0 | plan | — | 2026-08-13 |",
        ])
        blocked = gate.check_backlog_closure(head, staged, repo_root=tmp_path)
        assert blocked == []


class TestMainStdinGate:
    def test_exits_zero_when_backlog_not_staged(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "stdin", __import__("io").StringIO("content/docs.aspose.org/en/pdf/java/x.md\n"))
        assert gate.main() == 0

    def test_exits_zero_on_empty_stdin(self, monkeypatch):
        monkeypatch.setattr(sys, "stdin", __import__("io").StringIO(""))
        assert gate.main() == 0
