"""Tests for the reports/ local-only git boundary and the hook install mechanism.

Verifies four invariants:
1. git tracks zero files under reports/ (boundary is clean)
2. scripts/pre-commit-audit.sh contains the Step 0 guard (blocking — restored 2026-08-14,
   TC-CIR-01, after a brief 2026-08-08 to 2026-08-14 warn-only window that removed the
   only enforcement content-audit.yml's identical, pull_request-only copy never provides)
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
        """Guard must grep for staged reports/ additions (blocks — see
        test_source_reports_guard_is_blocking: restored 2026-08-14, TC-CIR-01)."""
        content = self._SOURCE.read_text(encoding="utf-8")
        # The guard greps for '^reports/' and blocks if found
        assert "grep '^reports/'" in content or "grep \"^reports/\"" in content, (
            "Step 0 guard must grep for staged files under reports/"
        )

    def test_source_reports_guard_is_blocking(self):
        """Step 0 was downgraded to WARN on 2026-08-08 (CI rules audit), then restored to
        BLOCK on 2026-08-14 (TC-CIR-01, CI reliability reassessment): content-audit.yml's
        identical whole-tree copy is pull_request-only and never fires under this repo's
        direct-to-main push model, so the WARN window left this defect class with zero
        live enforcement, not enforcement merely relocated to CI. The guard must detect
        the violation and exit the commit."""
        content = self._SOURCE.read_text(encoding="utf-8")
        start = content.index("# Step 0:")
        end = content.index("_pc_step_start", start + 1)
        step0_block = content[start:end]
        assert "BLOCKED" in step0_block, "Step 0 must surface the violation as a blocking error"
        assert "_pc_exit" in step0_block, (
            "Step 0 must call _pc_exit — it is blocking, not warn-only"
        )


# ---------------------------------------------------------------------------
# TC-CIR-01 (2026-08-14, CI reliability reassessment): 6 more steps restored
# from WARN back to BLOCK — each had lost its only live enforcement on
# 2026-08-08 without a working CI backstop (Step 9 onboarding-integrity is
# excluded: it has a genuine, disclosed, working CI backstop and correctly
# stayed WARN, see the plan's Root Cause D / §R2 incident #8).
# ---------------------------------------------------------------------------

class TestTierOneRestoredSteps:
    """Steps 1b, 3, 7, 9b, 15 must be blocking again (TC-CIR-01)."""

    _SOURCE = _REPO_ROOT / "scripts" / "pre-commit-audit.sh"

    @staticmethod
    def _step_block(content: str, start_marker: str, end_marker: str = "_pc_step_start") -> str:
        start = content.index(start_marker)
        end = content.index(end_marker, start + 1)
        return content[start:end]

    def test_step1b_filename_conventions_is_blocking(self):
        content = self._SOURCE.read_text(encoding="utf-8")
        block = self._step_block(content, "# Step 1b:")
        assert "_pc_exit" in block, "Step 1b must call _pc_exit — it is blocking"
        assert "BLOCKED" in block

    def test_step3_plugin_platform_is_blocking(self):
        content = self._SOURCE.read_text(encoding="utf-8")
        block = self._step_block(content, "# Step 3:")
        assert "_pc_exit" in block, "Step 3 must call _pc_exit — it is blocking"
        assert "BLOCKED" in block

    def test_step7_python_placement_is_blocking(self):
        content = self._SOURCE.read_text(encoding="utf-8")
        block = self._step_block(content, "# Step 7:")
        assert "_pc_exit" in block, "Step 7 must call _pc_exit — it is blocking"
        assert "BLOCKED" in block

    def test_step9_onboarding_integrity_stays_warn(self):
        """Step 9 is the one deliberate, working exception — must NOT be reverted."""
        content = self._SOURCE.read_text(encoding="utf-8")
        block = self._step_block(content, "# Step 9:", end_marker="# Step 9b:")
        assert "_pc_exit" not in block, (
            "Step 9 must stay warn-only — ci-eval-consistency.yml's onboarding-integrity "
            "job is a genuine, disclosed, working CI backstop (push-triggered + weekly "
            "schedule), unlike the other 6 restored steps"
        )

    def test_step9b_root_docs_truth_is_blocking(self):
        content = self._SOURCE.read_text(encoding="utf-8")
        block = self._step_block(content, "# Step 9b:")
        assert "_pc_exit" in block, "Step 9b must call _pc_exit — it is blocking"
        assert "BLOCKED" in block

    def test_step15_blog_post_standards_is_blocking(self):
        content = self._SOURCE.read_text(encoding="utf-8")
        block = self._step_block(content, "# Step 15:")
        assert "_pc_exit" in block, "Step 15 must call _pc_exit — it is blocking"
        assert "BLOCKED" in block


# ---------------------------------------------------------------------------
# TC-CIR-10 (2026-08-14): Step 5 must not silently auto-stage corrected content
# ---------------------------------------------------------------------------

class TestStep5NoSilentAutoStage:
    _SOURCE = _REPO_ROOT / "scripts" / "pre-commit-audit.sh"

    def test_step5_does_not_pass_auto_stage_flag(self):
        content = self._SOURCE.read_text(encoding="utf-8")
        start = content.index("# Step 5:")
        end = content.index("_pc_step_start", start + 1)
        step5_block = content[start:end]
        invocation_lines = [
            ln for ln in step5_block.splitlines()
            if "provenance_normalize_hash.py" in ln
        ]
        assert invocation_lines, "Step 5 must invoke provenance_normalize_hash.py"
        assert not any("--auto-stage" in ln for ln in invocation_lines), (
            "Step 5's actual invocation must not pass --auto-stage — corrected content "
            "must be reviewed and staged by the operator, not silently committed (TC-CIR-10)"
        )

    def test_step5_blocks_when_files_were_updated(self):
        content = self._SOURCE.read_text(encoding="utf-8")
        start = content.index("# Step 5:")
        end = content.index("_pc_step_start", start + 1)
        step5_block = content[start:end]
        assert "_pc_exit 1" in step5_block, (
            "Step 5 must block the commit when content_hash was stale, not silently continue"
        )


# ---------------------------------------------------------------------------
# TC-CIR-03/04 (2026-08-14): new local checks wired up
# ---------------------------------------------------------------------------

class TestNewLocalChecksWiredUp:
    _SOURCE = _REPO_ROOT / "scripts" / "pre-commit-audit.sh"

    def test_grade_churn_check_present_and_blocking(self):
        content = self._SOURCE.read_text(encoding="utf-8")
        assert "check_grade_churn.py" in content, (
            "TC-CIR-03: check_grade_churn.py (GUARD-02) must be wired into pre-commit"
        )
        start = content.index("_pc_step_start \"grade churn\"")
        end = content.index("_pc_step_start", start + 1)
        block = content[start:end]
        assert "_pc_exit 1" in block

    def test_skill_registry_json_check_present_and_blocking(self):
        content = self._SOURCE.read_text(encoding="utf-8")
        assert "check_skill_registry_json.py" in content, (
            "TC-CIR-04: check_skill_registry_json.py must be wired into pre-commit Step 25"
        )


# ---------------------------------------------------------------------------
# TC-CIR-11 (2026-08-14): local Python version pin
# ---------------------------------------------------------------------------

class TestPythonVersionPin:
    def test_python_version_file_exists_and_matches_ci(self):
        pin_file = _REPO_ROOT / ".python-version"
        assert pin_file.exists(), "TC-CIR-11: .python-version must exist at repo root"
        assert pin_file.read_text(encoding="utf-8").strip() == "3.12", (
            "Local Python pin must match CI's actions/setup-python@v5 pin ('3.12')"
        )

    def test_precommit_source_checks_version_pin(self):
        content = (_REPO_ROOT / "scripts" / "pre-commit-audit.sh").read_text(encoding="utf-8")
        assert ".python-version" in content, (
            "TC-CIR-11: pre-commit-audit.sh must read .python-version and warn on mismatch"
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
