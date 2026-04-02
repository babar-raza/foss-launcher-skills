"""Tests for hardened pre_write.py behavior.

Verifies the two behavioral changes:
  1. Missing knowledge model → FAIL (exit 1), not WARN (exit 0)
  2. Multiple findings are all shown in the output message, not just the first
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline"))

from pre_write import pre_write_check


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_finding(message="some audit issue", level="FAIL"):
    f = MagicMock()
    f.message = message
    f.level = level
    return f


def _allow(target, config=None):
    """Patch check_path to return ALLOW for any path."""
    return patch("pre_write.check_path", return_value=("ALLOW", "ok"))


# ---------------------------------------------------------------------------
# Missing knowledge → FAIL not WARN
# ---------------------------------------------------------------------------

class TestMissingKnowledgeFail:
    def test_filenotfounderror_returns_exit_1(self, tmp_path):
        target = tmp_path / "content" / "page.md"
        target.parent.mkdir(parents=True)
        target.write_text("# page", encoding="utf-8")

        err = FileNotFoundError(2, "No such file", "knowledge/foo/bar/merged/api_surface.json")

        with _allow(target):
            with patch("pre_write._import_audit_files") as mock_import:
                mock_import.return_value = MagicMock(side_effect=err)
                code, msg = pre_write_check(str(target))

        assert code == 1, f"Expected exit 1 (FAIL), got {code}: {msg}"

    def test_filenotfounderror_message_starts_with_fail(self, tmp_path):
        target = tmp_path / "content" / "page.md"
        target.parent.mkdir(parents=True)
        target.write_text("# page", encoding="utf-8")

        err = FileNotFoundError(2, "No such file", "knowledge/foo/bar/merged/api_surface.json")

        with _allow(target):
            with patch("pre_write._import_audit_files") as mock_import:
                mock_import.return_value = MagicMock(side_effect=err)
                code, msg = pre_write_check(str(target))

        assert msg.startswith("FAIL:"), f"Expected message starting with FAIL:, got: {msg[:60]}"

    def test_filenotfounderror_message_contains_bootstrap_hint(self, tmp_path):
        target = tmp_path / "content" / "page.md"
        target.parent.mkdir(parents=True)
        target.write_text("# page", encoding="utf-8")

        err = FileNotFoundError(2, "No such file", "knowledge/foo/bar/merged/api_surface.json")

        with _allow(target):
            with patch("pre_write._import_audit_files") as mock_import:
                mock_import.return_value = MagicMock(side_effect=err)
                code, msg = pre_write_check(str(target))

        # Should tell operator how to fix it
        assert "S-34" in msg or "bootstrap" in msg.lower(), (
            f"Expected bootstrap hint in message, got: {msg}"
        )

    def test_generic_exception_returns_exit_1(self, tmp_path):
        """Any unexpected exception during audit is also a FAIL, not a WARN."""
        target = tmp_path / "content" / "page.md"
        target.parent.mkdir(parents=True)
        target.write_text("# page", encoding="utf-8")

        with _allow(target):
            with patch("pre_write._import_audit_files") as mock_import:
                mock_import.return_value = MagicMock(
                    side_effect=RuntimeError("unexpected import failure")
                )
                code, msg = pre_write_check(str(target))

        assert code == 1
        assert msg.startswith("FAIL:")

    def test_no_knowledge_was_previously_warn_exit_0(self, tmp_path):
        """Document the OLD behavior to make the change visible in test history.

        Previously, FileNotFoundError returned (0, 'WARN: ...'). This test
        explicitly verifies the old behavior NO LONGER APPLIES.
        """
        target = tmp_path / "content" / "page.md"
        target.parent.mkdir(parents=True)
        target.write_text("# page", encoding="utf-8")

        err = FileNotFoundError(2, "No such file", "knowledge/foo/bar/merged/api_surface.json")

        with _allow(target):
            with patch("pre_write._import_audit_files") as mock_import:
                mock_import.return_value = MagicMock(side_effect=err)
                code, msg = pre_write_check(str(target))

        # Old behavior was code == 0 and msg.startswith("WARN:")
        # New behavior: code must be 1
        assert code != 0, "Regression: missing knowledge returned exit 0 (old WARN behavior)"
        assert not msg.startswith("WARN:"), f"Regression: message still says WARN: {msg[:60]}"


# ---------------------------------------------------------------------------
# All findings shown, not just the first
# ---------------------------------------------------------------------------

class TestAllFindingsShown:
    def test_single_finding_shown(self, tmp_path):
        target = tmp_path / "content" / "page.md"
        target.parent.mkdir(parents=True)
        target.write_text("# page", encoding="utf-8")

        findings = [_make_finding("first issue", "FAIL")]

        with _allow(target):
            with patch("pre_write._import_audit_files") as mock_import:
                mock_import.return_value = MagicMock(return_value=findings)
                code, msg = pre_write_check(str(target))

        assert code == 1
        assert "first issue" in msg

    def test_multiple_findings_all_shown(self, tmp_path):
        target = tmp_path / "content" / "page.md"
        target.parent.mkdir(parents=True)
        target.write_text("# page", encoding="utf-8")

        findings = [
            _make_finding("first issue", "FAIL"),
            _make_finding("second issue", "FAIL"),
            _make_finding("third issue", "WARN"),
        ]

        with _allow(target):
            with patch("pre_write._import_audit_files") as mock_import:
                mock_import.return_value = MagicMock(return_value=findings)
                code, msg = pre_write_check(str(target))

        assert code == 1
        assert "first issue" in msg
        assert "second issue" in msg
        assert "third issue" in msg

    def test_finding_count_shown_in_message(self, tmp_path):
        target = tmp_path / "content" / "page.md"
        target.parent.mkdir(parents=True)
        target.write_text("# page", encoding="utf-8")

        findings = [_make_finding(f"issue {i}", "FAIL") for i in range(5)]

        with _allow(target):
            with patch("pre_write._import_audit_files") as mock_import:
                mock_import.return_value = MagicMock(return_value=findings)
                code, msg = pre_write_check(str(target))

        assert "5" in msg  # count is in the message

    def test_zero_findings_returns_pass(self, tmp_path):
        target = tmp_path / "content" / "page.md"
        target.parent.mkdir(parents=True)
        target.write_text("# page", encoding="utf-8")

        with _allow(target):
            with patch("pre_write._import_audit_files") as mock_import:
                mock_import.return_value = MagicMock(return_value=[])
                code, msg = pre_write_check(str(target))

        assert code == 0
        assert msg.startswith("PASS:")


# ---------------------------------------------------------------------------
# Existing behavior preserved
# ---------------------------------------------------------------------------

class TestExistingBehaviorPreserved:
    def test_new_file_still_passes(self, tmp_path):
        """New files (not yet existing) should still pass without audit."""
        target = tmp_path / "content" / "new-page.md"
        target.parent.mkdir(parents=True)
        # Note: target does NOT exist

        with _allow(target):
            code, msg = pre_write_check(str(target))

        assert code == 0
        assert "new file" in msg.lower() or "PASS" in msg

    def test_forbidden_path_still_blocked(self, tmp_path):
        target = tmp_path / "themes" / "style.css"
        target.parent.mkdir(parents=True)
        target.touch()

        with patch("pre_write.check_path", return_value=("DENY", "matches 'themes/'")):
            code, msg = pre_write_check(str(target))

        assert code == 1
        assert "forbidden" in msg.lower() or "FAIL" in msg
