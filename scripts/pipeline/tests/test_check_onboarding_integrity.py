"""
scripts/pipeline/tests/test_check_onboarding_integrity.py

Tests for scripts/ci/check_onboarding_integrity.py.

Each test builds a minimal fake repo in a temp directory and invokes the
check functions directly (no subprocess, no real repo state).

Happy path: all checks pass.
Failure paths: one per check group — exactly the failure that used to break things.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Make the CI script importable without installing it.
# __file__ lives at scripts/pipeline/tests/ → go up 3 levels to repo root → down to scripts/ci
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "scripts" / "ci"))

import check_onboarding_integrity as module  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_repo(tmp_path: Path) -> Path:
    """Scaffold a minimal, fully-passing fake repo."""
    # AGENTS.md — must contain the docs/QUICKSTART.md link
    (tmp_path / "AGENTS.md").write_text(
        "## 2. Read Order\n\nSee [docs/QUICKSTART.md](docs/QUICKSTART.md) for onboarding.\n\n"
        "## 2a. Source-of-Truth Hierarchy\n",
        encoding="utf-8",
    )
    # CLAUDE.md — must contain onboarding reference
    (tmp_path / "CLAUDE.md").write_text(
        "## Available Commands\n\nSee [docs/QUICKSTART.md](docs/QUICKSTART.md) first.\n",
        encoding="utf-8",
    )
    # OPERATOR_GUIDE.md — no broken links
    (tmp_path / "OPERATOR_GUIDE.md").write_text(
        "# Operator Guide\n\nSee [AGENTS.md](AGENTS.md).\n",
        encoding="utf-8",
    )
    # RUNBOOK.md — .venv-prefixed commands, valid link to OPERATOR_GUIDE
    (tmp_path / "RUNBOOK.md").write_text(
        "# Runbook\n\nSee [OPERATOR_GUIDE.md](OPERATOR_GUIDE.md).\n\n"
        "```bash\n.venv/Scripts/python scripts/pipeline/audit.py all\n```\n",
        encoding="utf-8",
    )
    # docs/QUICKSTART.md — all required substrings present
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "QUICKSTART.md").write_text(
        "# Operator Quick-Start Guide\n\n"
        "## 3. Session Flow: Init → Work → Commit\n\n"
        "Run `/session-start` first.\n\n"
        "## 6. Key Safety Rules\n\n"
        "Always use /commit.\n\n"
        "## 8. Further Reading\n\n"
        "See [AGENTS.md](../AGENTS.md).\n",
        encoding="utf-8",
    )
    return tmp_path


def _run_checks(tmp_path: Path) -> int:
    """Patch REPO_ROOT + OPERATOR_DOCS, clear _failures, run all checks, return exit code."""
    module._failures.clear()
    patched_docs = [
        tmp_path / "docs" / "QUICKSTART.md",
        tmp_path / "OPERATOR_GUIDE.md",
        tmp_path / "RUNBOOK.md",
    ]
    with (
        patch.object(module, "REPO_ROOT", tmp_path),
        patch.object(module, "OPERATOR_DOCS", patched_docs),
    ):
        module.check_agents_link()
        module.check_claude_ref()
        module.check_relative_links()
        module.check_runbook_venv()
        module.check_quickstart_structure()
    return 1 if module._failures else 0


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_all_non_git_checks_pass(self, tmp_path):
        """All checks except C1 (git) pass on a well-formed fake repo."""
        _make_repo(tmp_path)
        assert _run_checks(tmp_path) == 0, f"Unexpected failures: {module._failures}"


# ---------------------------------------------------------------------------
# C2 — AGENTS.md link
# ---------------------------------------------------------------------------


class TestC2AgentsLink:
    def test_link_missing(self, tmp_path):
        """AGENTS.md exists but has no link to docs/QUICKSTART.md."""
        _make_repo(tmp_path)
        (tmp_path / "AGENTS.md").write_text(
            "## 2. Read Order\n\nNo onboarding pointer here.\n",
            encoding="utf-8",
        )
        module._failures.clear()
        with patch.object(module, "REPO_ROOT", tmp_path):
            module.check_agents_link()
        assert any("C2-AGENTS-LINK" in f for f in module._failures), module._failures

    def test_agents_md_missing(self, tmp_path):
        """AGENTS.md does not exist at repo root."""
        _make_repo(tmp_path)
        (tmp_path / "AGENTS.md").unlink()
        module._failures.clear()
        with patch.object(module, "REPO_ROOT", tmp_path):
            module.check_agents_link()
        assert any("C2-AGENTS-LINK" in f for f in module._failures), module._failures

    def test_link_present_passes(self, tmp_path):
        """AGENTS.md contains 'docs/QUICKSTART.md' — no C2 failure."""
        _make_repo(tmp_path)
        module._failures.clear()
        with patch.object(module, "REPO_ROOT", tmp_path):
            module.check_agents_link()
        assert not any("C2-AGENTS-LINK" in f for f in module._failures), module._failures


# ---------------------------------------------------------------------------
# C3 — CLAUDE.md reference
# ---------------------------------------------------------------------------


class TestC3ClaudeRef:
    def test_ref_missing(self, tmp_path):
        """CLAUDE.md has neither docs/QUICKSTART.md nor OPERATOR_GUIDE.md reference."""
        _make_repo(tmp_path)
        (tmp_path / "CLAUDE.md").write_text(
            "## Available Commands\n\nNo onboarding pointer.\n",
            encoding="utf-8",
        )
        module._failures.clear()
        with patch.object(module, "REPO_ROOT", tmp_path):
            module.check_claude_ref()
        assert any("C3-CLAUDE-REF" in f for f in module._failures), module._failures

    def test_operator_guide_ref_satisfies(self, tmp_path):
        """CLAUDE.md containing OPERATOR_GUIDE.md (not QUICKSTART) still passes C3."""
        _make_repo(tmp_path)
        (tmp_path / "CLAUDE.md").write_text(
            "## Available Commands\n\nSee OPERATOR_GUIDE.md.\n",
            encoding="utf-8",
        )
        module._failures.clear()
        with patch.object(module, "REPO_ROOT", tmp_path):
            module.check_claude_ref()
        assert not any("C3-CLAUDE-REF" in f for f in module._failures), module._failures


# ---------------------------------------------------------------------------
# C4 — Relative link resolution
# ---------------------------------------------------------------------------


class TestC4RelativeLinks:
    def test_broken_link_detected(self, tmp_path):
        """OPERATOR_GUIDE.md links to a file that does not exist."""
        _make_repo(tmp_path)
        (tmp_path / "OPERATOR_GUIDE.md").write_text(
            "See [NonExistent](NonExistent.md).\n",
            encoding="utf-8",
        )
        module._failures.clear()
        patched_docs = [
            tmp_path / "docs" / "QUICKSTART.md",
            tmp_path / "OPERATOR_GUIDE.md",
            tmp_path / "RUNBOOK.md",
        ]
        with (
            patch.object(module, "REPO_ROOT", tmp_path),
            patch.object(module, "OPERATOR_DOCS", patched_docs),
        ):
            module.check_relative_links()
        assert any("C4-LINKS" in f for f in module._failures), module._failures

    def test_missing_operator_doc(self, tmp_path):
        """RUNBOOK.md deleted — C4 reports doc not found."""
        _make_repo(tmp_path)
        (tmp_path / "RUNBOOK.md").unlink()
        module._failures.clear()
        patched_docs = [
            tmp_path / "docs" / "QUICKSTART.md",
            tmp_path / "OPERATOR_GUIDE.md",
            tmp_path / "RUNBOOK.md",
        ]
        with (
            patch.object(module, "REPO_ROOT", tmp_path),
            patch.object(module, "OPERATOR_DOCS", patched_docs),
        ):
            module.check_relative_links()
        assert any("C4-LINKS" in f for f in module._failures), module._failures

    def test_absolute_url_skipped(self, tmp_path):
        """Absolute https:// links are not checked for filesystem resolution."""
        _make_repo(tmp_path)
        (tmp_path / "OPERATOR_GUIDE.md").write_text(
            "See [Aspose](https://aspose.com) for more info.\n",
            encoding="utf-8",
        )
        module._failures.clear()
        patched_docs = [
            tmp_path / "docs" / "QUICKSTART.md",
            tmp_path / "OPERATOR_GUIDE.md",
            tmp_path / "RUNBOOK.md",
        ]
        with (
            patch.object(module, "REPO_ROOT", tmp_path),
            patch.object(module, "OPERATOR_DOCS", patched_docs),
        ):
            module.check_relative_links()
        assert not any("C4-LINKS" in f for f in module._failures), module._failures


# ---------------------------------------------------------------------------
# C5 — RUNBOOK.md venv prefix
# ---------------------------------------------------------------------------


class TestC5RunbookVenv:
    def test_bare_python_in_code_block_fails(self, tmp_path):
        """RUNBOOK.md with bare 'python scripts/' inside a code block is flagged."""
        _make_repo(tmp_path)
        (tmp_path / "RUNBOOK.md").write_text(
            "# Runbook\n\n"
            "```bash\npython scripts/pipeline/audit.py all\n```\n",
            encoding="utf-8",
        )
        module._failures.clear()
        with patch.object(module, "REPO_ROOT", tmp_path):
            module.check_runbook_venv()
        assert any("C5-VENV-PREFIX" in f for f in module._failures), module._failures

    def test_bare_python_in_prose_not_flagged(self, tmp_path):
        """Bare 'python' appearing in prose (outside code blocks) is not flagged."""
        _make_repo(tmp_path)
        (tmp_path / "RUNBOOK.md").write_text(
            "# Runbook\n\n"
            "You could run python scripts/pipeline/audit.py manually.\n"
            "```bash\n.venv/Scripts/python scripts/pipeline/audit.py all\n```\n",
            encoding="utf-8",
        )
        module._failures.clear()
        with patch.object(module, "REPO_ROOT", tmp_path):
            module.check_runbook_venv()
        assert not any("C5-VENV-PREFIX" in f for f in module._failures), module._failures

    def test_venv_prefixed_command_passes(self, tmp_path):
        """Properly prefixed .venv/Scripts/python command passes C5."""
        _make_repo(tmp_path)
        module._failures.clear()
        with patch.object(module, "REPO_ROOT", tmp_path):
            module.check_runbook_venv()
        assert not any("C5-VENV-PREFIX" in f for f in module._failures), module._failures


# ---------------------------------------------------------------------------
# C6 — QUICKSTART.md structure
# ---------------------------------------------------------------------------


class TestC6QuickstartStructure:
    def test_missing_safety_rules_section(self, tmp_path):
        """docs/QUICKSTART.md missing 'Safety Rules' triggers C6."""
        _make_repo(tmp_path)
        (tmp_path / "docs" / "QUICKSTART.md").write_text(
            "# Guide\n\n"
            "## 3. Session Flow\n\n/session-start\n\n"
            "## 8. Further Reading\n",
            encoding="utf-8",
        )
        module._failures.clear()
        with patch.object(module, "REPO_ROOT", tmp_path):
            module.check_quickstart_structure()
        assert any("C6-STRUCTURE" in f for f in module._failures), module._failures

    def test_missing_session_start_command(self, tmp_path):
        """docs/QUICKSTART.md missing '/session-start' triggers C6."""
        _make_repo(tmp_path)
        (tmp_path / "docs" / "QUICKSTART.md").write_text(
            "# Guide\n\n"
            "## 3. Session Flow\n\nInit your session first.\n\n"
            "## 6. Key Safety Rules\n\nUse /commit.\n\n"
            "## 8. Further Reading\n",
            encoding="utf-8",
        )
        module._failures.clear()
        with patch.object(module, "REPO_ROOT", tmp_path):
            module.check_quickstart_structure()
        assert any("C6-STRUCTURE" in f for f in module._failures), module._failures

    def test_all_substrings_present_passes(self, tmp_path):
        """All required substrings present — no C6 failure."""
        _make_repo(tmp_path)
        module._failures.clear()
        with patch.object(module, "REPO_ROOT", tmp_path):
            module.check_quickstart_structure()
        assert not any("C6-STRUCTURE" in f for f in module._failures), module._failures

    def test_quickstart_absent_skipped_gracefully(self, tmp_path):
        """If QUICKSTART.md is missing, C6 skips gracefully (C1 handles the miss)."""
        _make_repo(tmp_path)
        (tmp_path / "docs" / "QUICKSTART.md").unlink()
        module._failures.clear()
        with patch.object(module, "REPO_ROOT", tmp_path):
            module.check_quickstart_structure()
        # C6 skips — C1 would catch the missing file in the full run
        assert not any("C6-STRUCTURE" in f for f in module._failures), module._failures
