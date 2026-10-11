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

import git_tracking_policy_sync as _gtp

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
    """reports/ must contain zero git-tracked files, except the deliberate,
    named exceptions declared in scripts/pipeline/config/git_tracking_policy.yaml
    (S-125, 2026-09-06) -- reports/repo-presenter-regen-full/ was carved out
    as tracked, reviewable pipeline evidence, and PKGINSTALL-DEFECT-SWEEP-
    REDESIGN (2026-09-10) added reports/audit/install-defect-sweep-latest/
    the same way. This test was never updated for the first carve-out
    (confirmed live: 245 already-tracked repo-presenter-regen-full files
    failed this exact assertion before this session touched anything) --
    fixed to check against the SAME policy-derived allowlist
    scripts/pre-commit-audit.sh's own reports/ boundary gate already uses
    (git_tracking_policy_sync.list_tracked_prefixes()), so the two
    enforcement points can never drift apart again."""

    def test_no_tracked_files_under_reports(self):
        """Every git-tracked file under reports/ must fall under a prefix
        scripts/pipeline/config/git_tracking_policy.yaml explicitly allows --
        anything else tracked there is the real boundary violation this test
        exists to catch."""
        tracked = _git_ls_files_reports()
        policy = _gtp.load_policy(_gtp._cfg_policy_path)
        allowed_prefixes = _gtp.list_tracked_prefixes(policy.get("policies", []), _REPO_ROOT)
        unexpected = [
            t for t in tracked
            if not any(t.startswith(prefix) for prefix in allowed_prefixes)
        ]
        assert unexpected == [], (
            f"Found {len(unexpected)} tracked file(s) under reports/ with no matching "
            f"git_tracking_policy.yaml exception — all must be untracked:\n"
            + "\n".join(unexpected[:20])
        )


# ---------------------------------------------------------------------------
# Pre-commit hook source contains the reports/ boundary guard
# ---------------------------------------------------------------------------

def _step_block_by_name(content: str, name: str) -> str:
    """One step's code block, located by its stable ``_pc_step_start`` name.

    Keyed on the step NAME, never the ``# Step N:`` header: the 2026-08-26
    renumbering silently retargeted every number-keyed lookup in this file
    (some tests failed outright; test_step3/7/15 kept PASSING against the
    WRONG step's block — found 2026-08-31, stale-guard plan TC-SG-20(b)).
    Names survive renumbering; a removed/renamed step fails loudly here.
    Same pattern TestNewLocalChecksWiredUp below already used.
    """
    start = content.index(f'_pc_step_start "{name}"')
    end = content.index("_pc_step_start", start + 1)
    return content[start:end]


class TestPreCommitGuard:
    """scripts/pre-commit-audit.sh must contain the reports/ boundary guard."""

    _SOURCE = _REPO_ROOT / "scripts" / "pre-commit-audit.sh"
    _INSTALLED = _REPO_ROOT / ".git" / "hooks" / "pre-commit"

    def test_source_contains_reports_guard(self):
        content = self._SOURCE.read_text(encoding="utf-8")
        assert '_pc_step_start "reports/ boundary"' in content, (
            "scripts/pre-commit-audit.sh is missing the reports/ boundary guard step"
        )
        assert "local-only artifacts" in content, (
            "reports/ boundary guard text not found in pre-commit-audit.sh"
        )

    def test_source_checks_diff_filter_acm(self):
        """Guard must use --diff-filter=ACM to allow staged deletions (git rm --cached)."""
        block = _step_block_by_name(
            self._SOURCE.read_text(encoding="utf-8"), "reports/ boundary")
        assert "--diff-filter=ACM" in block, (
            "The reports/ boundary guard must use --diff-filter=ACM to allow deletions"
        )

    def test_source_blocks_reports_additions(self):
        """Guard must grep for staged reports/ additions (blocks — see
        test_source_reports_guard_is_blocking: restored 2026-08-14, TC-CIR-01)."""
        block = _step_block_by_name(
            self._SOURCE.read_text(encoding="utf-8"), "reports/ boundary")
        assert "grep '^reports/'" in block or 'grep "^reports/"' in block, (
            "The reports/ boundary guard must grep for staged files under reports/"
        )

    def test_source_reports_guard_is_blocking(self):
        """The guard was downgraded to WARN on 2026-08-08 (CI rules audit), then restored
        to BLOCK on 2026-08-14 (TC-CIR-01, CI reliability reassessment): content-audit.yml's
        identical whole-tree copy is pull_request-only and never fires under this repo's
        direct-to-main push model, so the WARN window left this defect class with zero
        live enforcement, not enforcement merely relocated to CI. The guard must detect
        the violation and exit the commit."""
        block = _step_block_by_name(
            self._SOURCE.read_text(encoding="utf-8"), "reports/ boundary")
        assert "BLOCKED" in block, (
            "The reports/ boundary guard must surface the violation as a blocking error"
        )
        assert "_pc_exit" in block, (
            "The reports/ boundary guard must call _pc_exit — blocking, not warn-only"
        )


# ---------------------------------------------------------------------------
# TC-CIR-01 (2026-08-14, CI reliability reassessment): 6 more steps restored
# from WARN back to BLOCK — each had lost its only live enforcement on
# 2026-08-08 without a working CI backstop (Step 9 onboarding-integrity is
# excluded: it has a genuine, disclosed, working CI backstop and correctly
# stayed WARN, see the plan's Root Cause D / §R2 incident #8).
# ---------------------------------------------------------------------------

class TestTierOneRestoredSteps:
    """The filename-conventions, forbidden-path, Python-placement, root-docs and
    blog-post-standards steps must be blocking again (TC-CIR-01); onboarding
    integrity is the one deliberate warn-only exception. Keyed on step NAMES
    (TC-SG-20(b)) — the old '# Step N:' keys broke (or silently retargeted)
    on the 2026-08-26 renumbering."""

    _SOURCE = _REPO_ROOT / "scripts" / "pre-commit-audit.sh"

    def _block(self, name: str) -> str:
        return _step_block_by_name(self._SOURCE.read_text(encoding="utf-8"), name)

    def test_filename_conventions_is_blocking(self):
        block = self._block("filename conventions")
        assert "_pc_exit" in block, "filename conventions must call _pc_exit — blocking"
        assert "BLOCKED" in block

    def test_plugin_platform_is_blocking(self):
        block = self._block("plugin_platform")
        assert "_pc_exit" in block, "plugin_platform must call _pc_exit — blocking"
        assert "BLOCKED" in block

    def test_python_placement_is_blocking(self):
        block = self._block("Python placement")
        assert "_pc_exit" in block, "Python placement must call _pc_exit — blocking"
        assert "BLOCKED" in block

    def test_onboarding_integrity_stays_warn(self):
        """The one deliberate, working exception — must NOT be reverted to blocking."""
        block = self._block("onboarding integrity")
        assert "_pc_exit" not in block, (
            "onboarding integrity must stay warn-only — ci-eval-consistency.yml's "
            "onboarding-integrity job is a genuine, disclosed, working CI backstop "
            "(push-triggered + weekly schedule), unlike the other restored steps"
        )

    def test_root_docs_truth_is_blocking(self):
        block = self._block("root docs truth")
        assert "_pc_exit" in block, "root docs truth must call _pc_exit — blocking"
        assert "BLOCKED" in block

    def test_blog_post_standards_is_blocking(self):
        block = self._block("Blog post standards")
        assert "_pc_exit" in block, "Blog post standards must call _pc_exit — blocking"
        assert "BLOCKED" in block


# ---------------------------------------------------------------------------
# TC-CIR-10 (2026-08-14): content_hash normalization must not silently
# auto-stage corrected content
# ---------------------------------------------------------------------------

class TestContentHashNoSilentAutoStage:
    _SOURCE = _REPO_ROOT / "scripts" / "pre-commit-audit.sh"

    def test_normalize_does_not_pass_auto_stage_flag(self):
        block = _step_block_by_name(
            self._SOURCE.read_text(encoding="utf-8"), "content_hash normalization")
        invocation_lines = [
            ln for ln in block.splitlines()
            if "provenance_normalize_hash.py" in ln
        ]
        assert invocation_lines, (
            "content_hash normalization must invoke provenance_normalize_hash.py"
        )
        assert not any("--auto-stage" in ln for ln in invocation_lines), (
            "the normalize invocation must not pass --auto-stage — corrected content "
            "must be reviewed and staged by the operator, not silently committed (TC-CIR-10)"
        )

    def test_normalize_blocks_when_files_were_updated(self):
        block = _step_block_by_name(
            self._SOURCE.read_text(encoding="utf-8"), "content_hash normalization")
        assert "_pc_exit 1" in block, (
            "content_hash normalization must block the commit when content_hash was "
            "stale, not silently continue"
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
        assert pin_file.read_text(encoding="utf-8").strip() == "3.13", (
            "Local Python pin must match CI's actions/setup-python@v5 pin ('3.13')"
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
        # TC-CIR-09 (2026-08-14): originally skipped in CI here, because CI never
        # ran install-hooks.sh (a fresh actions/checkout@v4 clone has
        # core.hooksPath unset). CORRECTED (2026-08-16, found live: this exact
        # skip pattern combined with test_wrappers_are_executable's -- which had
        # NO skip -- broke skill-governance.yml on every single push for 2 days
        # before being noticed, since core.fileMode=false also means the
        # executable bit isn't preserved by checkout either). Real fix:
        # skill-governance.yml now runs `bash scripts/install-hooks.sh` before
        # this suite, so this assertion is genuinely meaningful in CI too --
        # no skip needed, this now verifies the installer itself still works on
        # a fresh checkout, not just a locally-installed developer machine.
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

# TC-CIR-06's Tier 2 pre-push gate (scripts/githooks/pre-push ->
# scripts/pre-push-audit.sh) and its TestPrePushGate coverage here were removed
# 2026-08-16 — see docs/operations/hook-installation.md.
