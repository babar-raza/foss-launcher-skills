"""Tests for scripts/ci/checks/check_staged_deletions.py — 10 detection cases."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "ci" / "checks"))

from check_staged_deletions import (  # type: ignore
    classify_tier,
    check_paths,
    find_valid_dgr,
    DeletedPath,
    DGR_DIR,
)


# ---------------------------------------------------------------------------
# Tier classification tests
# ---------------------------------------------------------------------------

class TestClassifyTier:
    def test_agents_md_is_t00(self):
        assert classify_tier("AGENTS.md") == "T-00"

    def test_hook_script_is_t00(self):
        assert classify_tier("scripts/ci/hooks/check_session_gate.sh") == "T-00"

    def test_workflow_is_t00(self):
        assert classify_tier(".github/workflows/content-audit.yml") == "T-00"

    def test_content_page_is_t01(self):
        assert classify_tier("content/products.aspose.org/ar/pdf/_index.md") == "T-01"

    def test_scripts_pipeline_is_t01(self):
        assert classify_tier("scripts/pipeline/commands/ops/some.py") == "T-01"

    def test_scripts_ci_checks_is_t01(self):
        assert classify_tier("scripts/ci/checks/check_staged_deletions.py") == "T-01"

    def test_docs_non_forbidden_is_t02(self):
        assert classify_tier("docs/contributing.md") == "T-02"

    def test_scripts_maintenance_is_t02(self):
        assert classify_tier("scripts/maintenance/cleanup.py") == "T-02"

    def test_reports_gitignored_is_t03(self):
        assert classify_tier("reports/audit/x.json") == "T-03"

    def test_path_guard_is_t00(self):
        assert classify_tier("scripts/pipeline/commands/governance/path_guard.py") == "T-00"

    def test_themes_is_t00(self):
        assert classify_tier("themes/main/layout.html") == "T-00"

    def test_skills_is_t00(self):
        assert classify_tier("skills/some-skill.md") == "T-00"


# ---------------------------------------------------------------------------
# Detection case tests (10 cases from plan)
# ---------------------------------------------------------------------------

def _make_deletion(path: str, status: str = "D") -> DeletedPath:
    tier = classify_tier(path)
    return DeletedPath(path=path, status=status, tier=tier)


class TestCheckPaths:
    """Tests the 10 detection cases from the plan, in both Phase 1 and Phase 2."""

    def test_case1_git_rm_agents_md_phase1(self, monkeypatch):
        """Case 1: git rm AGENTS.md — Phase 1 should warn but exit 0."""
        monkeypatch.setenv("DELETION_GATE_PHASE", "1")
        dp = _make_deletion("AGENTS.md")
        assert dp.tier == "T-00"
        result = check_paths([dp])
        assert result == 0

    def test_case1_git_rm_agents_md_phase2(self, monkeypatch):
        """Case 1: git rm AGENTS.md — Phase 2 should exit 2."""
        monkeypatch.setenv("DELETION_GATE_PHASE", "2")
        dp = _make_deletion("AGENTS.md")
        result = check_paths([dp])
        assert result == 2

    def test_case2_git_rm_hook_script_phase2(self, monkeypatch):
        """Case 2: git rm scripts/ci/hooks/check_session_gate.sh — Phase 2 exits 2."""
        monkeypatch.setenv("DELETION_GATE_PHASE", "2")
        dp = _make_deletion("scripts/ci/hooks/check_session_gate.sh")
        result = check_paths([dp])
        assert result == 2

    def test_case3_git_rm_workflow_phase2(self, monkeypatch):
        """Case 3: git rm .github/workflows/content-audit.yml — Phase 2 exits 2."""
        monkeypatch.setenv("DELETION_GATE_PHASE", "2")
        dp = _make_deletion(".github/workflows/content-audit.yml")
        result = check_paths([dp])
        assert result == 2

    def test_case4_t01_without_dgr_phase2(self, monkeypatch, tmp_path):
        """Case 4: git rm T-01 path without DGR — Phase 2 exits 2."""
        monkeypatch.setenv("DELETION_GATE_PHASE", "2")
        # Patch DGR_DIR to a non-existent tmp location
        import check_staged_deletions as csd
        original = csd.DGR_DIR
        csd.DGR_DIR = tmp_path / "deletion-approvals"
        try:
            dp = _make_deletion("content/products.aspose.org/ar/pdf/_index.md")
            assert dp.tier == "T-01"
            result = check_paths([dp])
            assert result == 2
        finally:
            csd.DGR_DIR = original

    def test_case5_t01_with_valid_dgr_phase2(self, monkeypatch, tmp_path):
        """Case 5: git rm T-01 path with valid DGR — exits 0."""
        monkeypatch.setenv("DELETION_GATE_PHASE", "2")
        import check_staged_deletions as csd
        original = csd.DGR_DIR
        dgr_dir = tmp_path / "deletion-approvals"
        dgr_dir.mkdir()
        csd.DGR_DIR = dgr_dir

        # Write a valid DGR
        from datetime import datetime, timezone, timedelta
        now = datetime.now(tz=timezone.utc)
        dgr_content = f"""dgr_id: DGR-20260704-test
dgr_version: "1.0"
approver: human-maintainer
approved_at: "{now.isoformat().replace('+00:00', 'Z')}"
expires_at: "{(now + timedelta(days=7)).isoformat().replace('+00:00', 'Z')}"
plan_ref: test
reason: "Test deletion"
files:
  - path: content/products.aspose.org/ar/pdf/_index.md
    deletion_class: T-01
    operation: hard_delete
rename_destination: null
commit_message_token: "Deletion-Approved: DGR-20260704-test"
"""
        (dgr_dir / "DGR-20260704-test.yaml").write_text(dgr_content, encoding="utf-8")

        try:
            dp = _make_deletion("content/products.aspose.org/ar/pdf/_index.md")
            result = check_paths([dp])
            assert result == 0
        finally:
            csd.DGR_DIR = original

    def test_case6_t01_with_expired_dgr_phase2(self, monkeypatch, tmp_path):
        """Case 6: git rm T-01 path with expired DGR — Phase 2 exits 2."""
        monkeypatch.setenv("DELETION_GATE_PHASE", "2")
        import check_staged_deletions as csd
        original = csd.DGR_DIR
        dgr_dir = tmp_path / "deletion-approvals"
        dgr_dir.mkdir()
        csd.DGR_DIR = dgr_dir

        # Write an expired DGR
        dgr_content = """dgr_id: DGR-20260601-expired
dgr_version: "1.0"
approver: human-maintainer
approved_at: "2026-06-01T00:00:00Z"
expires_at: "2026-06-08T00:00:00Z"
plan_ref: test
reason: "Test expired"
files:
  - path: content/products.aspose.org/ar/pdf/_index.md
    deletion_class: T-01
    operation: hard_delete
commit_message_token: "Deletion-Approved: DGR-20260601-expired"
"""
        (dgr_dir / "DGR-20260601-expired.yaml").write_text(dgr_content, encoding="utf-8")

        try:
            dp = _make_deletion("content/products.aspose.org/ar/pdf/_index.md")
            result = check_paths([dp])
            assert result == 2
        finally:
            csd.DGR_DIR = original

    def test_case7_t02_docs_advisory(self, monkeypatch):
        """Case 7: git rm docs/contributing.md (T-02) — advisory, exit 0."""
        monkeypatch.setenv("DELETION_GATE_PHASE", "2")
        dp = _make_deletion("docs/contributing.md")
        assert dp.tier == "T-02"
        result = check_paths([dp])
        assert result == 0

    def test_case8_git_mv_t01_source_without_dgr_phase2(self, monkeypatch, tmp_path):
        """Case 8: git mv T-01 source (rename) without DGR — Phase 2 exits 2."""
        monkeypatch.setenv("DELETION_GATE_PHASE", "2")
        import check_staged_deletions as csd
        original = csd.DGR_DIR
        csd.DGR_DIR = tmp_path / "deletion-approvals"
        try:
            dp = DeletedPath(
                path="content/products.aspose.org/ar/pdf/_index.md",
                status="R",
                tier="T-01",
            )
            result = check_paths([dp])
            assert result == 2
        finally:
            csd.DGR_DIR = original

    def test_case9_t03_gitignored_silent_pass(self, monkeypatch):
        """Case 9: git rm reports/audit/x.json (T-03) — silent pass, exit 0."""
        monkeypatch.setenv("DELETION_GATE_PHASE", "2")
        dp = _make_deletion("reports/audit/x.json")
        assert dp.tier == "T-03"
        result = check_paths([dp])
        assert result == 0

    def test_case10_scripts_pipeline_t01_without_dgr_phase2(self, monkeypatch, tmp_path):
        """Case 10: git rm scripts/pipeline/commands/ops/some.py — Phase 2 exits 2."""
        monkeypatch.setenv("DELETION_GATE_PHASE", "2")
        import check_staged_deletions as csd
        original = csd.DGR_DIR
        csd.DGR_DIR = tmp_path / "deletion-approvals"
        try:
            dp = _make_deletion("scripts/pipeline/commands/ops/some.py")
            assert dp.tier == "T-01"
            result = check_paths([dp])
            assert result == 2
        finally:
            csd.DGR_DIR = original

    def test_no_deletions_exits_0(self, monkeypatch):
        """Empty path list always exits 0."""
        monkeypatch.setenv("DELETION_GATE_PHASE", "2")
        result = check_paths([])
        assert result == 0
