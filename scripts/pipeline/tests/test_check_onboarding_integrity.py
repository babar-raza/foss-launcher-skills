"""
scripts/pipeline/tests/test_check_onboarding_integrity.py

Tests for scripts/ci/check_onboarding_integrity.py.

Each test builds a minimal fake repo in a temp directory and invokes the
check functions directly (no subprocess, no real repo state).

Happy path: all non-git checks pass.
Failure paths: one per check group — exactly the failure that used to break things.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Make the CI script importable without installing it.
# Walk up from __file__ until we find the repo root (identified by AGENTS.md),
# then descend to scripts/ci. Robust to file moves — no hardcoded parent depth.
def _find_repo_root(start: Path) -> Path:
    current = start.resolve()
    while current.parent != current:
        if (current / "AGENTS.md").exists():
            return current
        current = current.parent
    raise RuntimeError(
        f"Could not find repo root (no AGENTS.md found starting from {start}). "
        "Ensure the test is run from within the repository."
    )


sys.path.insert(0, str(_find_repo_root(Path(__file__)) / "scripts" / "ci" / "checks"))

import check_onboarding_integrity as module  # noqa: E402


# ---------------------------------------------------------------------------
# Path isolation (autouse)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_module(tmp_path):
    module.configure(repo_root=tmp_path)
    yield
    module.configure()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_repo(tmp_path: Path) -> Path:
    """Scaffold a minimal, fully-passing fake repo."""
    # AGENTS.md — must contain the docs/QUICKSTART.md link; headings must round-trip
    # through the GitHub slug algorithm (C7 check validates this)
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
    # docs/QUICKSTART.md — all required substrings from REQUIRED_QUICKSTART_SUBSTRINGS present
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "QUICKSTART.md").write_text(
        "# Operator Quick-Start Guide\n\n"
        "## Step 1: Environment Setup (5 minutes)\n\n"
        "Install the toolchain.\n\n"
        "## Step 4: Five Common Operator Workflows (15 minutes)\n\n"
        "Run `/session-start` first.\n\n"
        "## 6. Key Safety Rules\n\n"
        "Always use /commit.\n\n"
        "## After This Quickstart\n\n"
        "See [AGENTS.md](../AGENTS.md).\n",
        encoding="utf-8",
    )
    return tmp_path


def _run_checks() -> int:
    """Clear _failures, run all non-git checks, return exit code."""
    module._failures.clear()
    module._passed_labels.clear()
    module._verbose = False
    module.check_agents_link()
    module.check_claude_ref()
    module.check_relative_links()
    module.check_runbook_venv()
    module.check_quickstart_structure()
    module.check_toc_anchors()
    return 1 if module._failures else 0


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_all_non_git_checks_pass(self, tmp_path):
        """All checks except C1 (git subprocess) pass on a well-formed fake repo."""
        _make_repo(tmp_path)
        assert _run_checks() == 0, f"Unexpected failures: {module._failures}"


# ---------------------------------------------------------------------------
# C1 — git-tracking check (subprocess mocked — SR-03)
# ---------------------------------------------------------------------------


class TestC1GitTracked:
    def test_tracked_file_passes(self, tmp_path):
        """subprocess returns the expected path → C1 passes."""
        _make_repo(tmp_path)
        module._failures.clear()
        mock_result = type("CP", (), {"stdout": "docs/QUICKSTART.md\n", "returncode": 0})()
        # T3-MOCK: target=subprocess.run reason="git ls-files boundary call" removal=PERMANENT
        with patch("subprocess.run", return_value=mock_result):
            module.check_quickstart_tracked()
        assert not any("C1-TRACKED" in f for f in module._failures), module._failures

    def test_untracked_file_fails(self, tmp_path):
        """subprocess returns empty stdout → C1 fires."""
        _make_repo(tmp_path)
        module._failures.clear()
        mock_result = type("CP", (), {"stdout": "", "returncode": 0})()
        # T3-MOCK: target=subprocess.run reason="git ls-files boundary call" removal=PERMANENT
        with patch("subprocess.run", return_value=mock_result):
            module.check_quickstart_tracked()
        assert any("C1-TRACKED" in f for f in module._failures), module._failures

    def test_git_subprocess_called_with_correct_args(self, tmp_path):
        """check_quickstart_tracked calls git ls-files with the correct path and cwd."""
        _make_repo(tmp_path)
        module._failures.clear()
        mock_result = type("CP", (), {"stdout": "docs/QUICKSTART.md\n", "returncode": 0})()
        # T3-MOCK: target=subprocess.run reason="git ls-files boundary call" removal=PERMANENT
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            module.check_quickstart_tracked()
        mock_run.assert_called_once_with(
            ["git", "ls-files", "docs/QUICKSTART.md"],
            capture_output=True,
            text=True,
            cwd=tmp_path,
        )


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
        module.check_agents_link()
        assert any("C2-AGENTS-LINK" in f for f in module._failures), module._failures

    def test_agents_md_missing(self, tmp_path):
        """AGENTS.md does not exist at repo root."""
        _make_repo(tmp_path)
        (tmp_path / "AGENTS.md").unlink()
        module._failures.clear()
        module.check_agents_link()
        assert any("C2-AGENTS-LINK" in f for f in module._failures), module._failures

    def test_link_present_passes(self, tmp_path):
        """AGENTS.md contains 'docs/QUICKSTART.md' — no C2 failure."""
        _make_repo(tmp_path)
        module._failures.clear()
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
        module.check_relative_links()
        assert any("C4-LINKS" in f for f in module._failures), module._failures

    def test_missing_operator_doc(self, tmp_path):
        """RUNBOOK.md deleted — C4 reports doc not found."""
        _make_repo(tmp_path)
        (tmp_path / "RUNBOOK.md").unlink()
        module._failures.clear()
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
        module.check_runbook_venv()
        assert not any("C5-VENV-PREFIX" in f for f in module._failures), module._failures

    def test_venv_prefixed_command_passes(self, tmp_path):
        """Properly prefixed .venv/Scripts/python command passes C5."""
        _make_repo(tmp_path)
        module._failures.clear()
        module.check_runbook_venv()
        assert not any("C5-VENV-PREFIX" in f for f in module._failures), module._failures

    def test_bare_python_in_operator_guide_fails(self, tmp_path):
        """OPERATOR_GUIDE.md with bare 'python scripts/' inside a code block is flagged."""
        _make_repo(tmp_path)
        (tmp_path / "OPERATOR_GUIDE.md").write_text(
            "# Guide\n\n"
            "```bash\npython scripts/pipeline/audit.py all\n```\n",
            encoding="utf-8",
        )
        module._failures.clear()
        module.check_runbook_venv()
        assert any("C5-VENV-PREFIX" in f for f in module._failures), module._failures

    def test_venv_prefixed_operator_guide_passes(self, tmp_path):
        """OPERATOR_GUIDE.md with .venv/Scripts/python prefix passes C5."""
        _make_repo(tmp_path)
        (tmp_path / "OPERATOR_GUIDE.md").write_text(
            "# Guide\n\n"
            "See [AGENTS.md](AGENTS.md).\n\n"
            "```bash\n.venv/Scripts/python scripts/pipeline/audit.py all\n```\n",
            encoding="utf-8",
        )
        module._failures.clear()
        module.check_runbook_venv()
        assert not any("C5-VENV-PREFIX" in f for f in module._failures), module._failures

    def test_bare_python_in_codex_md_fails(self, tmp_path):
        """CODEX.md with bare 'python scripts/' inside a code block is flagged."""
        _make_repo(tmp_path)
        (tmp_path / "CODEX.md").write_text(
            "# CODEX.md\n\n"
            "```bash\npython scripts/pipeline/preflight.py <path>\n```\n",
            encoding="utf-8",
        )
        module._failures.clear()
        module.check_runbook_venv()
        assert any("C5-VENV-PREFIX" in f for f in module._failures), module._failures

    def test_venv_prefixed_codex_md_passes(self, tmp_path):
        """CODEX.md with .venv/Scripts/python prefix passes C5."""
        _make_repo(tmp_path)
        (tmp_path / "CODEX.md").write_text(
            "# CODEX.md\n\n"
            "```bash\n.venv/Scripts/python scripts/pipeline/preflight.py <path>\n```\n",
            encoding="utf-8",
        )
        module._failures.clear()
        module.check_runbook_venv()
        assert not any("C5-VENV-PREFIX" in f for f in module._failures), module._failures

    def test_codex_md_absent_skipped_gracefully(self, tmp_path):
        """If CODEX.md is absent, C5 skips it without error (unlike RUNBOOK.md which C4 catches)."""
        _make_repo(tmp_path)
        # CODEX.md is not created in _make_repo — it doesn't exist
        assert not (tmp_path / "CODEX.md").exists()
        module._failures.clear()
        module.check_runbook_venv()
        assert not any("C5-VENV-PREFIX" in f for f in module._failures), module._failures

    def test_bare_python_in_prose_operator_guide_not_flagged(self, tmp_path):
        """Bare 'python scripts/' in prose (outside code blocks) in OPERATOR_GUIDE.md is not flagged."""
        _make_repo(tmp_path)
        (tmp_path / "OPERATOR_GUIDE.md").write_text(
            "# Guide\n\n"
            "You can run python scripts/pipeline/audit.py manually.\n"
            "```bash\n.venv/Scripts/python scripts/pipeline/audit.py all\n```\n",
            encoding="utf-8",
        )
        module._failures.clear()
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
        module.check_quickstart_structure()
        assert any("C6-STRUCTURE" in f for f in module._failures), module._failures

    def test_all_substrings_present_passes(self, tmp_path):
        """All required substrings present — no C6 failure."""
        _make_repo(tmp_path)
        module._failures.clear()
        module.check_quickstart_structure()
        assert not any("C6-STRUCTURE" in f for f in module._failures), module._failures

    def test_quickstart_absent_skipped_gracefully(self, tmp_path):
        """If QUICKSTART.md is missing, C6 skips gracefully (C1 handles the miss)."""
        _make_repo(tmp_path)
        (tmp_path / "docs" / "QUICKSTART.md").unlink()
        module._failures.clear()
        module.check_quickstart_structure()
        # C6 skips — C1 would catch the missing file in the full run
        assert not any("C6-STRUCTURE" in f for f in module._failures), module._failures


# ---------------------------------------------------------------------------
# C7 — TOC anchor validation (SR-01)
# ---------------------------------------------------------------------------


class TestC7TocAnchors:
    def test_valid_anchor_passes(self, tmp_path):
        """An (#anchor) that matches a real heading slug does not fire C7."""
        _make_repo(tmp_path)
        # Heading '## 2. Read Order' → slug '2-read-order'
        (tmp_path / "AGENTS.md").write_text(
            "## 2. Read Order\n\nSee [docs/QUICKSTART.md](docs/QUICKSTART.md).\n\n"
            "See also [Read Order](#2-read-order).\n\n"
            "## 2a. Source-of-Truth Hierarchy\n",
            encoding="utf-8",
        )
        module._failures.clear()
        module.check_toc_anchors()
        assert not any("C7-TOC-ANCHORS" in f for f in module._failures), module._failures

    def test_broken_anchor_detected(self, tmp_path):
        """An (#anchor) with no matching heading fires C7."""
        _make_repo(tmp_path)
        (tmp_path / "AGENTS.md").write_text(
            "## 2. Read Order\n\nSee [docs/QUICKSTART.md](docs/QUICKSTART.md).\n\n"
            "See also [Wrong](#nonexistent-heading-slug).\n\n"
            "## 2a. Source-of-Truth Hierarchy\n",
            encoding="utf-8",
        )
        module._failures.clear()
        module.check_toc_anchors()
        assert any("C7-TOC-ANCHORS" in f for f in module._failures), module._failures

    def test_slug_algorithm_strips_punctuation(self, tmp_path):
        """Heading '## 6c. Protocol (added 2026-04-03)' → slug '6c-protocol-added-2026-04-03'."""
        _make_repo(tmp_path)
        (tmp_path / "AGENTS.md").write_text(
            "## 2. Read Order\n\nSee [docs/QUICKSTART.md](docs/QUICKSTART.md).\n\n"
            "## 6c. Protocol (added 2026-04-03)\n\n"
            "See [this](#6c-protocol-added-2026-04-03).\n\n"
            "## 2a. Source-of-Truth Hierarchy\n",
            encoding="utf-8",
        )
        module._failures.clear()
        module.check_toc_anchors()
        assert not any("C7-TOC-ANCHORS" in f for f in module._failures), module._failures

    def test_agents_missing_skips_gracefully(self, tmp_path):
        """If AGENTS.md is absent, C7 returns without error (C2 handles the miss)."""
        _make_repo(tmp_path)
        (tmp_path / "AGENTS.md").unlink()
        module._failures.clear()
        module.check_toc_anchors()
        assert not any("C7-TOC-ANCHORS" in f for f in module._failures), module._failures


# ---------------------------------------------------------------------------
# Observability — verbose mode and GitHub Actions annotations (SR-05)
# ---------------------------------------------------------------------------


class TestObservability:
    def test_verbose_pass_output(self, tmp_path, capsys):
        """With _verbose=True, passing checks emit 'PASS [Cx]' lines to stdout."""
        _make_repo(tmp_path)
        module._failures.clear()
        module._verbose = True
        try:
            module.check_agents_link()
        finally:
            module._verbose = False
        captured = capsys.readouterr()
        assert "PASS [C2-AGENTS-LINK]" in captured.out

    def test_verbose_false_no_pass_output(self, tmp_path, capsys):
        """With _verbose=False (default), no PASS lines are emitted on stdout."""
        _make_repo(tmp_path)
        module._failures.clear()
        module._verbose = False
        module.check_agents_link()
        captured = capsys.readouterr()
        assert "PASS" not in captured.out

    def test_github_actions_annotation_on_failure(self, tmp_path, capsys):
        """When GITHUB_ACTIONS env var is set, failures emit ::error:: annotations."""
        _make_repo(tmp_path)
        (tmp_path / "AGENTS.md").write_text(
            "## 2. Read Order\n\nNo quickstart link.\n\n## 2a. Source\n",
            encoding="utf-8",
        )
        module._failures.clear()
        with patch.dict("os.environ", {"GITHUB_ACTIONS": "true"}):
            module.check_agents_link()
        captured = capsys.readouterr()
        assert "::error title=Onboarding Integrity [C2-AGENTS-LINK]::" in captured.out

    def test_verbose_dedup_for_multi_call_checks(self, tmp_path, capsys):
        """With --verbose, C4-LINKS appears exactly once even when multiple links pass."""
        _make_repo(tmp_path)
        # OPERATOR_GUIDE.md has two valid links — check_relative_links will call _check
        # with C4-LINKS twice (both passing); only one PASS line should be emitted.
        (tmp_path / "OPERATOR_GUIDE.md").write_text(
            "See [AGENTS.md](AGENTS.md) and [RUNBOOK.md](RUNBOOK.md).\n",
            encoding="utf-8",
        )
        module._failures.clear()
        module._passed_labels.clear()
        module._verbose = True
        try:
            module.check_relative_links()
        finally:
            module._verbose = False
            module._passed_labels.clear()
        captured = capsys.readouterr()
        assert captured.out.count("PASS [C4-LINKS]") == 1


# ---------------------------------------------------------------------------
# SR-08 — Encoding crash guard (non-UTF-8 bytes produce named FAIL, not traceback)
# ---------------------------------------------------------------------------


class TestEncodingGuard:
    def test_agents_md_non_utf8_named_fail(self, tmp_path):
        """AGENTS.md with non-UTF-8 bytes produces C2 FAIL with 'non-UTF-8' message, not crash."""
        _make_repo(tmp_path)
        # 0x96 is an em-dash in Windows-1252 — invalid in UTF-8
        (tmp_path / "AGENTS.md").write_bytes(
            b"## 2. Read Order\n\nSee docs/QUICKSTART.md\x96here.\n"
        )
        module._failures.clear()
        module.check_agents_link()
        assert any("C2-AGENTS-LINK" in f for f in module._failures), module._failures
        assert any("non-UTF-8" in f for f in module._failures), module._failures

    def test_operator_doc_non_utf8_named_fail(self, tmp_path):
        """An operator doc with non-UTF-8 bytes produces C4 FAIL, not crash."""
        _make_repo(tmp_path)
        (tmp_path / "OPERATOR_GUIDE.md").write_bytes(
            b"See [AGENTS.md](AGENTS.md).\x80Invalid byte.\n"
        )
        module._failures.clear()
        module.check_relative_links()
        assert any("C4-LINKS" in f for f in module._failures), module._failures
        assert any("non-UTF-8" in f for f in module._failures), module._failures

    def test_runbook_non_utf8_named_fail(self, tmp_path):
        """RUNBOOK.md with non-UTF-8 bytes produces C5 FAIL, not crash."""
        _make_repo(tmp_path)
        (tmp_path / "RUNBOOK.md").write_bytes(b"# Runbook\n\nBad byte: \xff\n")
        module._failures.clear()
        module.check_runbook_venv()
        assert any("C5-VENV-PREFIX" in f for f in module._failures), module._failures
        assert any("non-UTF-8" in f for f in module._failures), module._failures

    def test_quickstart_non_utf8_named_fail(self, tmp_path):
        """docs/QUICKSTART.md with non-UTF-8 bytes produces C6 FAIL, not crash."""
        _make_repo(tmp_path)
        (tmp_path / "docs" / "QUICKSTART.md").write_bytes(
            b"# Guide\n\nBad byte: \x81\n"
        )
        module._failures.clear()
        module.check_quickstart_structure()
        assert any("C6-STRUCTURE" in f for f in module._failures), module._failures
        assert any("non-UTF-8" in f for f in module._failures), module._failures
