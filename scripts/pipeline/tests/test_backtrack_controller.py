"""Tests for backtrack_controller.py — dataclasses and controller logic.

Covers:
  - ActionItem and BacktrackReport dataclasses
  - BacktrackController.run() with no upstream findings → status=complete
  - BacktrackController.run() with depth >= max_depth → status=escalated
  - BacktrackController.run() with missing eval report → status=escalated
  - BacktrackController.run() with upstream findings → cause_classifications populated
"""
import json
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backtrack_controller import (
    ActionItem,
    BacktrackReport,
    BacktrackController,
    MAX_BACKTRACK_DEPTH,
)


# ---------------------------------------------------------------------------
# ActionItem dataclass
# ---------------------------------------------------------------------------

class TestActionItem:
    def test_creation_with_required_fields(self):
        item = ActionItem(
            action_type="REGEN_PAGE",
            skill_id="heal-page",
            skill_args={"page": "/en/cells/python/"},
            source_pages=["/en/cells/python/index.md"],
            target_url="https://docs.aspose.org/cells/python/",
            target_slug="/cells/python/",
            correct_url=None,
            reason="Missing linked page",
        )
        assert item.action_type == "REGEN_PAGE"
        assert item.skill_id == "heal-page"
        assert item.reason == "Missing linked page"

    def test_can_convert_to_dict(self):
        item = ActionItem(
            action_type="REGEN_PAGE",
            skill_id="heal-page",
            skill_args={},
            source_pages=[],
            target_url="https://example.com",
            target_slug="/slug/",
            correct_url=None,
            reason="Test",
        )
        d = asdict(item)
        assert "action_type" in d
        assert "skill_id" in d


# ---------------------------------------------------------------------------
# BacktrackReport dataclass
# ---------------------------------------------------------------------------

class TestBacktrackReport:
    def test_defaults(self):
        r = BacktrackReport(
            run_id="cells-python-20260101",
            family="cells",
            platform="python",
            backtrack_depth=0,
            dry_run=False,
            started_at="2026-01-01T00:00:00Z",
        )
        assert r.status == "pending"
        assert r.action_items == []
        assert r.cause_classifications == []
        assert r.escalated_pages == []

    def test_status_values(self):
        r = BacktrackReport(
            run_id="test", family="cells", platform="python",
            backtrack_depth=0, dry_run=False, started_at="2026-01-01",
        )
        for status in ("pending", "complete", "escalated", "cycle_detected"):
            r.status = status
            assert r.status == status


# ---------------------------------------------------------------------------
# BacktrackController
# ---------------------------------------------------------------------------

def _write_eval_report(path: Path, findings: list[dict]) -> None:
    path.write_text(json.dumps({"findings": findings}), encoding="utf-8")


class TestBacktrackControllerMissingReport:
    def test_missing_eval_report_escalates(self, tmp_path):
        ctrl = BacktrackController(repo_root=tmp_path, dry_run=True)
        missing = tmp_path / "nonexistent_report.json"
        report = ctrl.run(missing, "cells", "python")
        assert report.status == "escalated"


class TestBacktrackControllerNoUpstreamFindings:
    def test_no_upstream_findings_completes(self, tmp_path):
        eval_report = tmp_path / "eval_report.json"
        _write_eval_report(eval_report, [
            {"id": "F1", "filepath": "/page.md", "cause_class": "MISSING_EVIDENCE",
             "message": "No evidence block", "line_no": 1},
        ])
        ctrl = BacktrackController(repo_root=tmp_path, dry_run=True)
        report = ctrl.run(eval_report, "cells", "python")
        assert report.status == "complete"
        assert report.cause_classifications == []

    def test_empty_findings_completes(self, tmp_path):
        eval_report = tmp_path / "eval_report.json"
        _write_eval_report(eval_report, [])
        ctrl = BacktrackController(repo_root=tmp_path, dry_run=True)
        report = ctrl.run(eval_report, "cells", "python")
        assert report.status == "complete"


class TestBacktrackControllerDepthGuard:
    def test_max_depth_escalates(self, tmp_path):
        eval_report = tmp_path / "eval_report.json"
        _write_eval_report(eval_report, [
            {"id": "F1", "filepath": "/page.md",
             "cause_class": "UPSTREAM_MISSING",
             "message": "Link `https://docs.aspose.org/cells/python/` is missing",
             "line_no": 5},
        ])
        ctrl = BacktrackController(repo_root=tmp_path, dry_run=True, max_depth=0)
        report = ctrl.run(eval_report, "cells", "python", depth=MAX_BACKTRACK_DEPTH)
        assert report.status == "escalated"

    def test_depth_at_max_escalates_not_processes(self, tmp_path):
        eval_report = tmp_path / "eval_report.json"
        _write_eval_report(eval_report, [
            {"id": "F1", "filepath": "/page.md",
             "cause_class": "UPSTREAM_MISSING",
             "message": "Link `https://docs.aspose.org/missing/` is broken",
             "line_no": 1},
        ])
        ctrl = BacktrackController(repo_root=tmp_path, dry_run=True)
        # depth == max_depth triggers escalation before DependencyVerifier is called
        report = ctrl.run(eval_report, "cells", "python", depth=ctrl.max_depth)
        assert report.status == "escalated"
        assert len(report.escalated_pages) > 0


class TestBacktrackControllerCauseClassification:
    def test_cause_classifications_populated_for_upstream_findings(self, tmp_path):
        from unittest.mock import patch
        from dependency_resolver import DependencyVerificationRecord
        eval_report = tmp_path / "eval_report.json"
        _write_eval_report(eval_report, [
            {"id": "F1", "filepath": "/page.md",
             "cause_class": "UPSTREAM_MISSING",
             "message": "Link `https://docs.aspose.org/cells/python/save/` is missing",
             "line_no": 10},
        ])

        # Mock DependencyVerifier.verify() to return a proper dataclass instance
        mock_record = DependencyVerificationRecord(
            source_url="https://docs.aspose.org/cells/python/save/",
            subdomain="docs.aspose.org",
            target_slug="save",
            family="cells",
            platform="python",
            page_exists=False,
            url_format_mismatch=False,
            api_surface_match=False,
            knowledge_stale=False,
            verdict="ESCALATE",
            verdict_reason="Page not found",
        )
        with patch("backtrack_controller.BacktrackController._write_report"), \
             patch("backtrack_controller.BacktrackController._write_human_queue"), \
             patch("dependency_resolver.DependencyVerifier") as MockVerifier:
            MockVerifier.return_value.verify.return_value = mock_record
            ctrl = BacktrackController(repo_root=tmp_path, dry_run=True)
            report = ctrl.run(eval_report, "cells", "python", depth=0)

        # cause_classifications must be populated from upstream findings
        assert len(report.cause_classifications) >= 1
        assert report.cause_classifications[0]["cause_class"] == "UPSTREAM_MISSING"
        assert report.cause_classifications[0]["filepath"] == "/page.md"


class TestBacktrackControllerReportFields:
    def test_report_family_platform_set(self, tmp_path):
        eval_report = tmp_path / "eval_report.json"
        _write_eval_report(eval_report, [])
        ctrl = BacktrackController(repo_root=tmp_path, dry_run=True)
        report = ctrl.run(eval_report, "words", "java")
        assert report.family == "words"
        assert report.platform == "java"

    def test_report_has_started_at(self, tmp_path):
        eval_report = tmp_path / "eval_report.json"
        _write_eval_report(eval_report, [])
        ctrl = BacktrackController(repo_root=tmp_path, dry_run=True)
        report = ctrl.run(eval_report, "cells", "python")
        assert report.started_at != ""
        assert report.completed_at != ""

    def test_dry_run_flag_preserved(self, tmp_path):
        eval_report = tmp_path / "eval_report.json"
        _write_eval_report(eval_report, [])
        ctrl = BacktrackController(repo_root=tmp_path, dry_run=True)
        report = ctrl.run(eval_report, "cells", "python")
        assert report.dry_run is True
