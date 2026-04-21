"""Tests for scripts/pre_write.py — pre-write audit hook."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure scripts/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "pipeline"))

from pre_write import main, pre_write_check


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_finding(message="some audit issue", level="FAIL"):
    """Create a mock Finding-like object."""
    f = MagicMock()
    f.message = message
    f.level = level
    return f


# ---------------------------------------------------------------------------
# pre_write_check — path guard DENY
# ---------------------------------------------------------------------------

class TestPathGuardDeny:
    def test_deny_returns_exit_code_1(self, tmp_path):
        target = tmp_path / "scripts" / "some_script.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()
        with patch("pre_write.check_path", return_value=("DENY", "matches forbidden prefix 'scripts/'")):
            code, msg = pre_write_check(str(target))
        assert code == 1

    def test_deny_message_contains_forbidden(self, tmp_path):
        target = tmp_path / "themes" / "style.css"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()
        with patch("pre_write.check_path", return_value=("DENY", "matches forbidden prefix 'themes/'")):
            code, msg = pre_write_check(str(target))
        assert "forbidden" in msg.lower()

    def test_deny_message_starts_with_fail(self, tmp_path):
        target = tmp_path / "skills" / "skill.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()
        with patch("pre_write.check_path", return_value=("DENY", "matches forbidden prefix 'skills/'")):
            code, msg = pre_write_check(str(target))
        assert msg.startswith("FAIL:")

    def test_deny_does_not_call_audit(self, tmp_path):
        target = tmp_path / "layouts" / "base.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()
        with patch("pre_write.check_path", return_value=("DENY", "matches forbidden prefix 'layouts/'")):
            with patch("pre_write._import_audit_files") as mock_audit_import:
                pre_write_check(str(target))
        mock_audit_import.assert_not_called()


# ---------------------------------------------------------------------------
# pre_write_check — file does not exist (new file)
# ---------------------------------------------------------------------------

class TestFileNotExist:
    def test_new_file_returns_pass(self, tmp_path):
        target = tmp_path / "content" / "docs.aspose.org" / "en" / "words" / "python" / "new_page.md"
        # Do NOT create the file
        with patch("pre_write.check_path", return_value=("ALLOW", None)):
            code, msg = pre_write_check(str(target))
        assert code == 0

    def test_new_file_message_starts_with_pass(self, tmp_path):
        target = tmp_path / "content" / "new_page.md"
        with patch("pre_write.check_path", return_value=("ALLOW", None)):
            code, msg = pre_write_check(str(target))
        assert msg.startswith("PASS:")

    def test_new_file_does_not_call_audit(self, tmp_path):
        target = tmp_path / "content" / "new_page.md"
        with patch("pre_write.check_path", return_value=("ALLOW", None)):
            with patch("pre_write._import_audit_files") as mock_audit_import:
                pre_write_check(str(target))
        mock_audit_import.assert_not_called()


# ---------------------------------------------------------------------------
# pre_write_check — file exists, audit returns no findings
# ---------------------------------------------------------------------------

class TestAuditPass:
    def test_no_findings_returns_exit_code_0(self, tmp_path):
        target = tmp_path / "content" / "page.md"
        target.parent.mkdir(parents=True)
        target.write_text("# Hello\n", encoding="utf-8")
        mock_audit = MagicMock(return_value=[])
        with patch("pre_write.check_path", return_value=("ALLOW", None)):
            with patch("pre_write._import_audit_files", return_value=mock_audit):
                code, msg = pre_write_check(str(target))
        assert code == 0

    def test_no_findings_message_starts_with_pass(self, tmp_path):
        target = tmp_path / "content" / "page.md"
        target.parent.mkdir(parents=True)
        target.write_text("# Hello\n", encoding="utf-8")
        mock_audit = MagicMock(return_value=[])
        with patch("pre_write.check_path", return_value=("ALLOW", None)):
            with patch("pre_write._import_audit_files", return_value=mock_audit):
                code, msg = pre_write_check(str(target))
        assert msg.startswith("PASS:")

    def test_no_findings_message_contains_evidence_verified(self, tmp_path):
        target = tmp_path / "content" / "page.md"
        target.parent.mkdir(parents=True)
        target.write_text("# Hello\n", encoding="utf-8")
        mock_audit = MagicMock(return_value=[])
        with patch("pre_write.check_path", return_value=("ALLOW", None)):
            with patch("pre_write._import_audit_files", return_value=mock_audit):
                code, msg = pre_write_check(str(target))
        assert "evidence verified" in msg


# ---------------------------------------------------------------------------
# pre_write_check — file exists, audit returns findings
# ---------------------------------------------------------------------------

class TestAuditFail:
    def test_findings_returns_exit_code_1(self, tmp_path):
        target = tmp_path / "content" / "page.md"
        target.parent.mkdir(parents=True)
        target.write_text("# Hello\n", encoding="utf-8")
        findings = [_make_finding("frontmatter evidence: block absent")]
        mock_audit = MagicMock(return_value=findings)
        with patch("pre_write.check_path", return_value=("ALLOW", None)):
            with patch("pre_write._import_audit_files", return_value=mock_audit):
                code, msg = pre_write_check(str(target))
        assert code == 1

    def test_findings_message_starts_with_fail(self, tmp_path):
        target = tmp_path / "content" / "page.md"
        target.parent.mkdir(parents=True)
        target.write_text("# Hello\n", encoding="utf-8")
        findings = [_make_finding("frontmatter evidence: block absent")]
        mock_audit = MagicMock(return_value=findings)
        with patch("pre_write.check_path", return_value=("ALLOW", None)):
            with patch("pre_write._import_audit_files", return_value=mock_audit):
                code, msg = pre_write_check(str(target))
        assert msg.startswith("FAIL:")

    def test_findings_message_includes_count(self, tmp_path):
        target = tmp_path / "content" / "page.md"
        target.parent.mkdir(parents=True)
        target.write_text("# Hello\n", encoding="utf-8")
        findings = [
            _make_finding("frontmatter evidence: block absent"),
            _make_finding("unknown class Foo"),
            _make_finding("bad method Bar.baz"),
        ]
        mock_audit = MagicMock(return_value=findings)
        with patch("pre_write.check_path", return_value=("ALLOW", None)):
            with patch("pre_write._import_audit_files", return_value=mock_audit):
                code, msg = pre_write_check(str(target))
        assert "3 finding(s)" in msg

    def test_findings_message_includes_first_finding(self, tmp_path):
        target = tmp_path / "content" / "page.md"
        target.parent.mkdir(parents=True)
        target.write_text("# Hello\n", encoding="utf-8")
        findings = [_make_finding("[MISSING_EVIDENCE] frontmatter evidence: block absent")]
        mock_audit = MagicMock(return_value=findings)
        with patch("pre_write.check_path", return_value=("ALLOW", None)):
            with patch("pre_write._import_audit_files", return_value=mock_audit):
                code, msg = pre_write_check(str(target))
        assert "frontmatter evidence: block absent" in msg


# ---------------------------------------------------------------------------
# pre_write_check — audit raises FileNotFoundError (missing knowledge model)
# ---------------------------------------------------------------------------

class TestAuditFileNotFoundError:
    def test_file_not_found_returns_exit_code_1(self, tmp_path):
        """Missing knowledge model is a FAIL (exit 1), not a WARN (exit 0)."""
        target = tmp_path / "content" / "page.md"
        target.parent.mkdir(parents=True)
        target.write_text("# Hello\n", encoding="utf-8")
        mock_audit = MagicMock(side_effect=FileNotFoundError("knowledge model missing"))
        with patch("pre_write.check_path", return_value=("ALLOW", None)):
            with patch("pre_write._import_audit_files", return_value=mock_audit):
                code, msg = pre_write_check(str(target))
        assert code == 1

    def test_file_not_found_message_starts_with_fail(self, tmp_path):
        """Missing knowledge model message must start with FAIL:, not WARN:."""
        target = tmp_path / "content" / "page.md"
        target.parent.mkdir(parents=True)
        target.write_text("# Hello\n", encoding="utf-8")
        mock_audit = MagicMock(side_effect=FileNotFoundError("knowledge model missing"))
        with patch("pre_write.check_path", return_value=("ALLOW", None)):
            with patch("pre_write._import_audit_files", return_value=mock_audit):
                code, msg = pre_write_check(str(target))
        assert msg.startswith("FAIL:")

    def test_file_not_found_message_contains_bootstrap_hint(self, tmp_path):
        """Message should tell operator how to fix the missing knowledge model."""
        target = tmp_path / "content" / "page.md"
        target.parent.mkdir(parents=True)
        target.write_text("# Hello\n", encoding="utf-8")
        mock_audit = MagicMock(side_effect=FileNotFoundError("no such file"))
        with patch("pre_write.check_path", return_value=("ALLOW", None)):
            with patch("pre_write._import_audit_files", return_value=mock_audit):
                code, msg = pre_write_check(str(target))
        assert "S-34" in msg or "bootstrap" in msg.lower() or "knowledge model" in msg.lower()

    def test_generic_exception_returns_exit_code_1(self, tmp_path):
        """Any unexpected exception during audit is also a FAIL, not a WARN."""
        target = tmp_path / "content" / "page.md"
        target.parent.mkdir(parents=True)
        target.write_text("# Hello\n", encoding="utf-8")
        mock_audit = MagicMock(side_effect=RuntimeError("unexpected error from audit"))
        with patch("pre_write.check_path", return_value=("ALLOW", None)):
            with patch("pre_write._import_audit_files", return_value=mock_audit):
                code, msg = pre_write_check(str(target))
        assert code == 1
        assert msg.startswith("FAIL:")


# ---------------------------------------------------------------------------
# CLI — main()
# ---------------------------------------------------------------------------

class TestCLI:
    def test_main_no_args_returns_exit_code_2(self):
        code = main([])
        assert code == 2

    def test_main_pass_returns_exit_code_0(self, tmp_path):
        target = tmp_path / "content" / "page.md"
        # File does not exist -> PASS (new file)
        with patch("pre_write.check_path", return_value=("ALLOW", None)):
            code = main([str(target)])
        assert code == 0

    def test_main_fail_returns_exit_code_1(self, tmp_path):
        target = tmp_path / "content" / "page.md"
        target.parent.mkdir(parents=True)
        target.write_text("# Hello\n", encoding="utf-8")
        findings = [_make_finding("frontmatter evidence: block absent")]
        mock_audit = MagicMock(return_value=findings)
        with patch("pre_write.check_path", return_value=("ALLOW", None)):
            with patch("pre_write._import_audit_files", return_value=mock_audit):
                code = main([str(target)])
        assert code == 1

    def test_main_deny_returns_exit_code_1(self, tmp_path):
        target = tmp_path / "scripts" / "script.py"
        with patch("pre_write.check_path", return_value=("DENY", "matches forbidden prefix 'scripts/'")):
            code = main([str(target)])
        assert code == 1

    def test_main_prints_message(self, tmp_path, capsys):
        target = tmp_path / "content" / "new_page.md"
        with patch("pre_write.check_path", return_value=("ALLOW", None)):
            code = main([str(target)])
        captured = capsys.readouterr()
        assert "PASS:" in captured.out

    def test_main_error_no_args_prints_error(self, capsys):
        main([])
        captured = capsys.readouterr()
        assert "ERROR" in captured.out

    def test_main_knowledge_root_flag(self, tmp_path):
        """--knowledge-root flag is accepted without error."""
        target = tmp_path / "content" / "new_page.md"
        kr = tmp_path / "knowledge"
        kr.mkdir()
        with patch("pre_write.check_path", return_value=("ALLOW", None)):
            code = main([str(target), "--knowledge-root", str(kr)])
        assert code == 0


# ---------------------------------------------------------------------------
# pre_write_check — stale knowledge model detection (TASK-05)
# ---------------------------------------------------------------------------

class TestStaleSinceBlock:
    """Tests that pre_write blocks or warns when model.yaml has stale_since set."""

    def _make_model_yaml(self, tmp_path, stale_since=None):
        """Create a knowledge model directory with optional stale_since."""
        import yaml as _yaml
        merged = tmp_path / "knowledge" / "words" / "python" / "merged"
        merged.mkdir(parents=True)
        model = {
            "family": "words",
            "platform": "python",
            "repo_sha": "abc123",
            "merged_at": "2026-01-01T00:00:00+00:00",
        }
        if stale_since is not None:
            model["stale_since"] = stale_since
        (merged / "model.yaml").write_text(_yaml.dump(model), encoding="utf-8")
        return tmp_path

    def test_stale_model_audit_finding_causes_fail(self, tmp_path):
        """When audit returns a stale-model finding, pre_write returns exit code 1."""
        target = tmp_path / "content" / "page.md"
        target.parent.mkdir(parents=True)
        target.write_text("# Hello\n", encoding="utf-8")

        stale_finding = _make_finding("knowledge model is stale (stale_since: 2026-01-01)", "FAIL")
        mock_audit = MagicMock(return_value=[stale_finding])

        with patch("pre_write.check_path", return_value=("ALLOW", None)):
            with patch("pre_write._import_audit_files", return_value=mock_audit):
                code, msg = pre_write_check(str(target))

        assert code == 1
        assert "stale" in msg.lower() or "finding(s)" in msg.lower()

    def test_stale_model_message_starts_with_fail(self, tmp_path):
        """Stale-model finding produces FAIL: prefix."""
        target = tmp_path / "content" / "page.md"
        target.parent.mkdir(parents=True)
        target.write_text("# Hello\n", encoding="utf-8")

        stale_finding = _make_finding("knowledge model is stale (stale_since: 2026-01-01)", "FAIL")
        mock_audit = MagicMock(return_value=[stale_finding])

        with patch("pre_write.check_path", return_value=("ALLOW", None)):
            with patch("pre_write._import_audit_files", return_value=mock_audit):
                code, msg = pre_write_check(str(target))

        assert msg.startswith("FAIL:")

    def test_fresh_model_passes(self, tmp_path):
        """When audit returns no findings, pre_write returns exit code 0 (fresh model)."""
        target = tmp_path / "content" / "page.md"
        target.parent.mkdir(parents=True)
        target.write_text("# Hello\n", encoding="utf-8")

        mock_audit = MagicMock(return_value=[])  # no findings = model is fresh

        with patch("pre_write.check_path", return_value=("ALLOW", None)):
            with patch("pre_write._import_audit_files", return_value=mock_audit):
                code, msg = pre_write_check(str(target))

        assert code == 0

    def test_multiple_findings_including_stale_all_reported(self, tmp_path):
        """When multiple findings exist including stale, all findings appear in message."""
        target = tmp_path / "content" / "page.md"
        target.parent.mkdir(parents=True)
        target.write_text("# Hello\n", encoding="utf-8")

        findings = [
            _make_finding("knowledge model is stale (stale_since: 2026-01-01)", "FAIL"),
            _make_finding("unverified API token: FooClass", "FAIL"),
        ]
        mock_audit = MagicMock(return_value=findings)

        with patch("pre_write.check_path", return_value=("ALLOW", None)):
            with patch("pre_write._import_audit_files", return_value=mock_audit):
                code, msg = pre_write_check(str(target))

        assert code == 1
        assert "2 finding(s)" in msg
