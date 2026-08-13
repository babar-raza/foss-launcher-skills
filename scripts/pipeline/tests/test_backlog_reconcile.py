"""MT030-2026-08-13: backlog_reconcile.py -- Cat=knowledge rows vs knowledge_state.json."""
import json

import pytest

# sys.path is set by tests/conftest.py
import backlog_reconcile as br


class TestReconcileRow:
    def test_unresolvable_product_key(self):
        row = {"id": "SOME-ROW", "title": "No slash here", "status": "queued", "cat": "knowledge"}
        result = br.reconcile_row(row, None)
        assert result["disposition"] == "unresolvable_product"

    def test_insufficient_data_fails_open(self):
        """No knowledge_state entry yet must never be treated as a red flag --
        every never-yet-refreshed product would otherwise spuriously fail."""
        row = {"id": "NEW-PRODUCT-001", "title": "cad/net first refresh", "status": "queued", "cat": "knowledge"}
        result = br.reconcile_row(row, None)
        assert result["disposition"] == "insufficient_data"
        assert result["product_key"] == "cad/net"

    def test_non_closed_row_is_ok_regardless_of_state(self):
        row = {"id": "PDF-JAVA-REFRESH-003", "title": "pdf/java new upstream drift", "status": "queued", "cat": "knowledge"}
        state = {"family": "pdf", "platform": "java"}  # no truth_audit at all
        result = br.reconcile_row(row, state)
        assert result["disposition"] == "ok"

    def test_closed_with_no_truth_audit_is_stale(self):
        """The exact PDF-JAVA-REFRESH-003 pattern: row claims CLOSED but nothing
        durable proves a clean truth-audit backs that claim."""
        row = {"id": "PDF-JAVA-REFRESH-003", "title": "pdf/java new upstream drift", "status": "CLOSED", "cat": "knowledge"}
        state = {"family": "pdf", "platform": "java"}
        result = br.reconcile_row(row, state)
        assert result["disposition"] == "stale_closure"

    def test_closed_with_failing_truth_audit_is_stale(self):
        row = {"id": "PDF-JAVA-REFRESH-003", "title": "pdf/java new upstream drift", "status": "CLOSED", "cat": "knowledge"}
        state = {
            "family": "pdf", "platform": "java",
            "truth_audit": {"verdict": "FAIL", "fail_count": 1, "report_path": "reports/audit/x.md"},
        }
        result = br.reconcile_row(row, state)
        assert result["disposition"] == "stale_closure"

    def test_closed_with_passing_truth_audit_is_ok(self):
        row = {"id": "PDF-JAVA-REFRESH-003", "title": "pdf/java new upstream drift", "status": "CLOSED", "cat": "knowledge"}
        state = {
            "family": "pdf", "platform": "java",
            "truth_audit": {"verdict": "PASS", "fail_count": 0, "report_path": "reports/audit/x.md"},
        }
        result = br.reconcile_row(row, state)
        assert result["disposition"] == "ok"

    def test_accepted_ceiling_status_also_treated_as_closure_claim(self):
        row = {"id": "SOME-ROW", "title": "cells/typescript accepted ceiling", "status": "ACCEPTED_CEILING", "cat": "knowledge"}
        state = {"family": "cells", "platform": "typescript"}
        result = br.reconcile_row(row, state)
        assert result["disposition"] == "stale_closure"


class TestReconcileEndToEnd:
    @pytest.fixture(autouse=True)
    def _isolate(self, tmp_path, monkeypatch):
        import knowledge_state as ks
        monkeypatch.setattr(ks, "_STATE_PATH", tmp_path / "knowledge_state.json")
        monkeypatch.setattr(ks, "_LOCK_PATH", tmp_path / "knowledge_state.json.lock")
        self.ks = ks

    def test_full_reconcile_over_sample_backlog(self, tmp_path):
        backlog = tmp_path / "BACKLOG.md"
        backlog.write_text(
            "## Active\n\n"
            "| ID | Cat | Effect | Title | Status | Priority | Size | Wave | Score | Plan | Blocker | Updated |\n"
            "|----|-----|--------|-------|--------|----------|------|------|-------|------|---------|---------|\n"
            "| PDF-JAVA-REFRESH-003 | knowledge | HIGH | pdf/java new upstream drift | CLOSED | P1 | L | 0 | 0 | plan | — | 2026-08-13 |\n"
            "| SOME-OPS-ROW | ops | LOW | Not a knowledge row | CLOSED | P4 | XS | 0 | 1 | plan | — | 2026-06-10 |\n",
            encoding="utf-8",
        )
        # pdf/java has no recorded truth_audit yet -> should flag stale_closure
        self.ks.record_baseline_accepted(
            "pdf", "java", repo_sha="sha1", sha_source="scout",
            run_id="run1", accepted_at="2026-01-01T00:00:00Z",
        )

        results = br.reconcile(backlog)
        assert len(results) == 1  # ops row excluded (cat != knowledge)
        assert results[0]["disposition"] == "stale_closure"

    def test_main_writes_report_and_exits_zero(self, tmp_path, capsys):
        backlog = tmp_path / "BACKLOG.md"
        backlog.write_text(
            "## Active\n\n"
            "| ID | Cat | Effect | Title | Status | Priority | Size | Wave | Score | Plan | Blocker | Updated |\n"
            "|----|-----|--------|-------|--------|----------|------|------|-------|------|---------|---------|\n"
            "| PDF-JAVA-REFRESH-003 | knowledge | HIGH | pdf/java new upstream drift | queued | P1 | L | 0 | 0 | — | — | 2026-08-01 |\n",
            encoding="utf-8",
        )
        report_path = tmp_path / "backlog_reconciliation.json"
        import backlog_reconcile as br_module
        br_module.REPORT_PATH = report_path
        exit_code = br.main(["--backlog", str(backlog), "--json"])
        assert exit_code == 0
        assert report_path.exists()
        data = json.loads(report_path.read_text(encoding="utf-8"))
        assert data["stale_count"] == 0
