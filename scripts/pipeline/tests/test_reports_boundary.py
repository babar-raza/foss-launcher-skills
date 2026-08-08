"""Tests for the reports/ local-only git boundary and the hook install mechanism.

Verifies four invariants:
1. git tracks zero files under reports/ (boundary is clean)
2. scripts/pre-commit-audit.sh contains the Step 0 guard (warn-only since 2026-08-08)
3. scripts/post-commit-override.sh does NOT contain git add -f for archived tokens
4. core.hooksPath points at scripts/githooks/, and each wrapper execs its real,
   tracked source — not a copy that can drift out of sync (2026-08-08 redesign)

These are read-only filesystem and git-query checks — no subprocess writes, no mocks.
"""

from __future__ import annotations

import os
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

    def test_source_blocks_reports_additions(self):
        """Guard must grep for staged reports/ additions (warns, does not block — see
        test_source_reports_guard_is_warn_only: downgraded 2026-08-08, CI rules audit)."""
        content = self._SOURCE.read_text(encoding="utf-8")
        # The guard greps for '^reports/' and warns if found
        assert "grep '^reports/'" in content or "grep \"^reports/\"" in content, (
            "Step 0 guard must grep for staged files under reports/"
        )

    def test_source_reports_guard_is_warn_only(self):
        """Step 0 was downgraded from BLOCK to WARN (2026-08-08 CI rules audit: no test
        (a)-(f) criticality met — git history remains the safety net). The guard must
        still detect and print the violation, but must not exit the commit."""
        content = self._SOURCE.read_text(encoding="utf-8")
        start = content.index("# Step 0:")
        end = content.index("_pc_step_start", start + 1)
        step0_block = content[start:end]
        assert "WARNING" in step0_block, "Step 0 must still surface the violation as a warning"
        assert "_pc_exit" not in step0_block, (
            "Step 0 must not call _pc_exit — it is warn-only, not blocking"
        )


# ---------------------------------------------------------------------------
# Post-commit hook does NOT stage archived tokens
# ---------------------------------------------------------------------------

class TestPostCommitHook:
    """scripts/post-commit-override.sh must NOT contain git add -f for archived tokens."""

    _SOURCE = _REPO_ROOT / "scripts" / "post-commit-override.sh"

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


# ---------------------------------------------------------------------------
# Hook install mechanism: core.hooksPath -> scripts/githooks/ (2026-08-08)
#
# Replaces a copy-based install (scripts/install-hooks.sh cp'd each hook source
# into the untracked .git/hooks/) that had silently drifted in production — the
# installed copy was found missing a bug fix and an entire safety step (the
# media-asset-size guard) that had already landed in scripts/pre-commit-audit.sh.
# core.hooksPath + tracked exec-wrappers make that class of drift structurally
# impossible: there is no copy left to fall behind. See
# docs/operations/hook-installation.md for the full rationale.
# ---------------------------------------------------------------------------

class TestHookInstallMechanism:
    """core.hooksPath must point at the tracked scripts/githooks/ wrapper directory,
    and each wrapper must exec its real, tracked source script — not a copy."""

    _GITHOOKS_DIR = _REPO_ROOT / "scripts" / "githooks"

    @staticmethod
    def _configured_hooks_path() -> str:
        result = subprocess.run(
            ["git", "config", "--get", "core.hooksPath"],
            capture_output=True, text=True, cwd=_REPO_ROOT,
        )
        return result.stdout.strip()

    def test_core_hooks_path_configured(self):
        configured = self._configured_hooks_path()
        assert configured == "scripts/githooks", (
            f"core.hooksPath is '{configured}', expected 'scripts/githooks' — "
            "run: bash scripts/install-hooks.sh"
        )

    @pytest.mark.parametrize(
        "hook_name,real_source",
        [
            ("pre-commit", "pre-commit-audit.sh"),
            ("commit-msg", "commit-msg-skills.sh"),
            ("post-commit", "post-commit-override.sh"),
        ],
    )
    def test_wrapper_execs_real_source(self, hook_name, real_source):
        wrapper = self._GITHOOKS_DIR / hook_name
        assert wrapper.exists(), f"scripts/githooks/{hook_name} wrapper missing"
        content = wrapper.read_text(encoding="utf-8")
        assert real_source in content, (
            f"scripts/githooks/{hook_name} must exec scripts/{real_source}, "
            "not a copy of its content"
        )

    def test_reference_transaction_hook_present(self):
        # Tracked verbatim (already self-contained) rather than exec-wrapped.
        hook = self._GITHOOKS_DIR / "reference-transaction"
        assert hook.exists(), "scripts/githooks/reference-transaction missing"

    def test_wrappers_are_executable(self):
        for name in ("pre-commit", "commit-msg", "post-commit", "reference-transaction"):
            wrapper = self._GITHOOKS_DIR / name
            assert wrapper.exists(), f"scripts/githooks/{name} missing"
            assert os.access(wrapper, os.X_OK), (
                f"scripts/githooks/{name} is not executable — "
                "run: bash scripts/install-hooks.sh"
            )
