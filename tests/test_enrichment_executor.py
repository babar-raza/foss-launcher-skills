"""Tests for S-98 enrichment executor safety (TC-014)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_LIB_DIR = str(Path(__file__).resolve().parent.parent / "scripts" / "pipeline" / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from enrichment.executor import execute_plan
from enrichment.coverage_matrix import configure


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_repo(tmp_path):
    """Set up a temporary repo root for executor output."""
    (tmp_path / "reports" / "enrichment" / "testfam" / "testplat").mkdir(parents=True)
    configure(repo_root=tmp_path)
    yield tmp_path


@pytest.fixture
def valid_plan():
    """Minimal valid plan result for executor."""
    return {
        "manifest": {
            "family": "testfam",
            "platform": "testplat",
            "dry_run": False,
            "manifest_items": [
                {"cluster": "alpha", "subdomain": "docs", "action": "create_docs_page", "target_skill": "S-56", "score": 0.85},
                {"cluster": "beta", "subdomain": "kb", "action": "create_kb_howto", "target_skill": "S-58", "score": 0.75},
                {"cluster": "gamma", "subdomain": "docs", "action": "create_docs_page", "target_skill": "S-56", "score": 0.70},
            ],
            "backlog_items": [
                {"cluster": "delta", "subdomain": "blog", "reason": "Low score", "score": 0.25},
            ],
        },
        "decisions": {},
        "denominator_check": {"valid": True, "total_candidates": 4, "bucket_sum": 4, "delta": 0},
    }


# ---------------------------------------------------------------------------
# Safety tests
# ---------------------------------------------------------------------------

class TestExecutorSafety:
    """Verify execute mode safety invariants."""

    def test_no_content_directory_writes(self, tmp_repo, valid_plan):
        """Execute mode must not create any files under content/."""
        content_dir = tmp_repo / "content"
        content_dir.mkdir(exist_ok=True)
        result = execute_plan(valid_plan, "testfam", "testplat")
        content_files = list(content_dir.rglob("*"))
        assert content_files == [], f"Execute mode wrote to content/: {content_files}"

    def test_produces_execution_log(self, tmp_repo, valid_plan):
        """Execute mode must produce execution-log.json."""
        execute_plan(valid_plan, "testfam", "testplat")
        log_path = tmp_repo / "reports" / "enrichment" / "testfam" / "testplat" / "execution-log.json"
        assert log_path.exists()
        log = json.loads(log_path.read_text(encoding="utf-8"))
        assert log["status"] == "manifest_ready"

    def test_produces_execution_report(self, tmp_repo, valid_plan):
        """Execute mode must produce enrichment-report.md."""
        execute_plan(valid_plan, "testfam", "testplat")
        report_path = tmp_repo / "reports" / "enrichment" / "testfam" / "testplat" / "enrichment-report.md"
        assert report_path.exists()
        text = report_path.read_text(encoding="utf-8")
        assert "No content was directly written" in text

    def test_conservative_pilot_limit(self, tmp_repo, valid_plan):
        """Execute mode must select at most 2 items (conservative limit)."""
        result = execute_plan(valid_plan, "testfam", "testplat")
        assert result["selected_count"] <= 2

    def test_excess_items_deferred(self, tmp_repo, valid_plan):
        """Items beyond conservative limit must be deferred, not dropped."""
        result = execute_plan(valid_plan, "testfam", "testplat")
        assert result["deferred_from_execute_count"] == 1
        assert result["deferred_from_execute"][0]["cluster"] == "gamma"

    def test_denominator_failure_halts(self, tmp_repo, valid_plan):
        """Execute mode must halt if denominator invariant fails."""
        valid_plan["denominator_check"] = {"valid": False, "delta": 1}
        result = execute_plan(valid_plan, "testfam", "testplat")
        assert result.get("error") == "denominator_invariant_failed"

    def test_manifest_status_field(self, tmp_repo, valid_plan):
        """Result status must be manifest_ready, not executed or published."""
        result = execute_plan(valid_plan, "testfam", "testplat")
        assert result["status"] == "manifest_ready"
        assert "publish" not in json.dumps(result).lower()
