"""Tests for the reports/ local-only git boundary.

Verifies three invariants:
1. git tracks zero files under reports/ (boundary is clean)
2. scripts/pre-commit-audit.sh contains the Step 0 guard
3. scripts/post-commit-override.sh does NOT contain git add -f for archived tokens

These are read-only filesystem and git-query checks — no subprocess writes, no mocks.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _git_ls_files_reports() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "reports/"],
        capture_output=True, text=True, cwd=_REPO_ROOT,
    )
    assert result.returncode == 0, f"git ls-files failed: {result.stderr}"
    return [line for line in result.stdout.splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# Git boundary
# ---------------------------------------------------------------------------

class TestGitBoundary:
    """reports/ must contain zero git-tracked files."""

    def test_no_tracked_files_under_reports(self):
        """reports/ is a local-only artifact directory — nothing may be tracked."""
        tracked = _git_ls_files_reports()
        assert tracked == [], (
            f"Found {len(tracked)} tracked file(s) under reports/ — "
            f"all must be untracked:\n" + "\n".join(tracked[:20])
        )


# ---------------------------------------------------------------------------
# Pre-commit hook source contains Step 0 guard
# ---------------------------------------------------------------------------

class TestPreCommitGuard:
    """scripts/pre-commit-audit.sh must contain the reports/ boundary guard."""

    _SOURCE = _REPO_ROOT / "scripts" / "pre-commit-audit.sh"
    _INSTALLED = _REPO_ROOT / ".git" / "hooks" / "pre-commit"

    def test_source_contains_step0_guard(self):
        content = self._SOURCE.read_text(encoding="utf-8")
        assert "Step 0" in content, (
            "scripts/pre-commit-audit.sh is missing the Step 0 reports/ guard"
        )
        assert "reports/ boundary" in content or "local-only artifacts" in content, (
            "Step 0 guard text not found in pre-commit-audit.sh"
        )

    def test_source_checks_diff_filter_acm(self):
        """Guard must use --diff-filter=ACM to allow staged deletions (git rm --cached)."""
        content = self._SOURCE.read_text(encoding="utf-8")
        # Find the Step 0 block — look for the diff-filter line near the reports/ grep
        assert "--diff-filter=ACM" in content, (
            "Pre-commit Step 0 guard must use --diff-filter=ACM to allow deletions"
        )

    def test_installed_hook_contains_guard(self):
        """The installed .git/hooks/pre-commit must also contain the guard."""
        if not self._INSTALLED.exists():
            pytest.skip("Pre-commit hook not installed (run bash scripts/install-hooks.sh)")
        content = self._INSTALLED.read_text(encoding="utf-8")
        assert "Step 0" in content or "reports/ boundary" in content, (
            ".git/hooks/pre-commit is missing the reports/ guard — "
            "run: bash scripts/install-hooks.sh"
        )

    def test_source_blocks_reports_additions(self):
        """Guard must exit 1 on staged reports/ additions."""
        content = self._SOURCE.read_text(encoding="utf-8")
        # The guard greps for '^reports/' and exits 1 if found
        assert "grep '^reports/'" in content or "grep \"^reports/\"" in content, (
            "Step 0 guard must grep for staged files under reports/"
        )
        assert "exit 1" in content, "Step 0 guard must exit 1 to block the commit"


# ---------------------------------------------------------------------------
# Post-commit hook does NOT stage archived tokens
# ---------------------------------------------------------------------------

class TestPostCommitHook:
    """scripts/post-commit-override.sh must NOT contain git add -f for archived tokens."""

    _SOURCE = _REPO_ROOT / "scripts" / "post-commit-override.sh"
    _INSTALLED = _REPO_ROOT / ".git" / "hooks" / "post-commit"

    def test_source_no_git_add_force_archived(self):
        content = self._SOURCE.read_text(encoding="utf-8")
        assert "git add -f" not in content, (
            "scripts/post-commit-override.sh must not force-add any files. "
            "Override token archival is a local filesystem operation only."
        )

    def test_source_no_staging_of_reports(self):
        content = self._SOURCE.read_text(encoding="utf-8")
        lines_with_stage = [
            ln for ln in content.splitlines()
            if "git add" in ln and "reports/" in ln
        ]
        assert lines_with_stage == [], (
            "post-commit-override.sh must not stage any reports/ files:\n"
            + "\n".join(lines_with_stage)
        )

    def test_installed_hook_no_git_add_force_archived(self):
        if not self._INSTALLED.exists():
            pytest.skip("Post-commit hook not installed (run bash scripts/install-hooks.sh)")
        content = self._INSTALLED.read_text(encoding="utf-8")
        assert "git add -f" not in content, (
            ".git/hooks/post-commit must not force-add any files — "
            "run: bash scripts/install-hooks.sh"
        )
