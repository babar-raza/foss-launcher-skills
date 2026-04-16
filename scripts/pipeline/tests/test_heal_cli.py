"""Tests for remediate.py heal subcommand (TH-C1, TH-C2, TH-C3)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import remediate


def _write_eval_report(tmp_path: Path, findings: list[dict] | None = None) -> Path:
    """Write a minimal eval report JSON file for testing."""
    if findings is None:
        findings = [
            {
                "level": "FAIL",
                "category": "RV",
                "file": "test.md",
                "line": 1,
                "message": "type: missing frontmatter type field",
                "evaluator": "page_role",
            },
            {
                "level": "FAIL",
                "category": "AA",
                "file": "test.md",
                "line": 10,
                "message": "API method Workbook.save does not exist",
                "evaluator": "api_accuracy",
            },
        ]
    report = {"findings": findings}
    path = tmp_path / "eval-report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    return path


class TestHealSubcommandArgparse:
    """Test that the heal subparser is wired correctly."""

    def test_heal_help_does_not_error(self, capsys):
        with pytest.raises(SystemExit) as exc:
            remediate.main(["heal", "--help"])
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "heal" in out
        assert "--mode" in out
        assert "--dry-run" in out

    def test_heal_requires_eval_report(self):
        with pytest.raises(SystemExit) as exc:
            remediate.main(["heal"])
        assert exc.value.code != 0


class TestHealExecution:
    """Test heal subcommand execution with mock data."""

    @patch("heal_controller.run_fixes")
    def test_heal_auto_mode_dry_run(self, mock_run_fixes, tmp_path, capsys):
        mock_run_fixes.return_value = []
        report = _write_eval_report(tmp_path)
        remediate.main(["heal", str(report), "--mode", "auto", "--dry-run"])
        out = capsys.readouterr().out
        assert "dry-run" in out.lower() or "Heal:" in out

    @patch("heal_controller.run_fixes")
    def test_heal_all_mode(self, mock_run_fixes, tmp_path, capsys):
        mock_run_fixes.return_value = []
        report = _write_eval_report(tmp_path)
        remediate.main(["heal", str(report), "--mode", "all"])
        out = capsys.readouterr().out
        assert "Heal:" in out

    @patch("heal_controller.run_fixes")
    def test_heal_json_output(self, mock_run_fixes, tmp_path, capsys):
        mock_run_fixes.return_value = []
        report = _write_eval_report(tmp_path)
        remediate.main(["heal", str(report), "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "plan" in data
        assert "summary" in data
        assert "llm_queue" in data
        assert "regen_queue" in data
        assert "auto_results" in data

    @patch("heal_controller.run_fixes")
    def test_heal_llm_only_mode(self, mock_run_fixes, tmp_path, capsys):
        mock_run_fixes.return_value = []
        report = _write_eval_report(tmp_path)
        remediate.main(["heal", str(report), "--mode", "llm", "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["summary"]["mode"] == "llm"
        # Auto results should be empty since mode=llm
        assert data["auto_results"] == []

    @patch("heal_controller.run_fixes")
    def test_heal_regen_mode(self, mock_run_fixes, tmp_path, capsys):
        """Regen mode with upstream findings."""
        mock_run_fixes.return_value = []
        findings = [
            {
                "level": "FAIL",
                "category": "AA",
                "file": "ref.md",
                "line": 1,
                "message": "link target missing",
                "evaluator": "api_accuracy",
                "cause_class": "UPSTREAM_MISSING",
            },
        ]
        report = _write_eval_report(tmp_path, findings)
        remediate.main(["heal", str(report), "--mode", "regen", "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["summary"]["mode"] == "regen"

    def test_existing_subcommands_still_work(self, tmp_path, capsys):
        """Verify triage subcommand still works (regression check)."""
        report = _write_eval_report(tmp_path)
        remediate.main(["triage", str(report)])
        out = capsys.readouterr().out
        assert "Triage Summary" in out or "Remediation Report" in out


class TestHealVerification:
    """Test heal subcommand with --after-report verification (TH-C2)."""

    @patch("heal_controller.run_fixes")
    def test_heal_with_after_report_json(self, mock_run_fixes, tmp_path, capsys):
        """--after-report triggers verification in JSON output."""
        mock_run_fixes.return_value = []
        before_report = _write_eval_report(tmp_path)
        # Write an after-report with no findings (all resolved)
        after_data = {"findings": []}
        after_path = tmp_path / "after-report.json"
        after_path.write_text(json.dumps(after_data), encoding="utf-8")

        remediate.main([
            "heal", str(before_report),
            "--after-report", str(after_path),
            "--json",
        ])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "verification" in data
        assert data["verification"]["regression_detected"] is False
        assert data["summary"]["verification_pages"] >= 1

    @patch("heal_controller.run_fixes")
    def test_heal_with_after_report_text(self, mock_run_fixes, tmp_path, capsys):
        """--after-report shows verification in text output."""
        mock_run_fixes.return_value = []
        before_report = _write_eval_report(tmp_path)
        after_data = {"findings": []}
        after_path = tmp_path / "after-report.json"
        after_path.write_text(json.dumps(after_data), encoding="utf-8")

        remediate.main([
            "heal", str(before_report),
            "--after-report", str(after_path),
        ])
        out = capsys.readouterr().out
        assert "Verification:" in out
        assert "No regressions" in out

    @patch("heal_controller.run_fixes")
    def test_heal_dry_run_skips_verification(self, mock_run_fixes, tmp_path, capsys):
        """--dry-run + --after-report skips verification."""
        mock_run_fixes.return_value = []
        before_report = _write_eval_report(tmp_path)
        after_data = {"findings": []}
        after_path = tmp_path / "after-report.json"
        after_path.write_text(json.dumps(after_data), encoding="utf-8")

        remediate.main([
            "heal", str(before_report),
            "--after-report", str(after_path),
            "--dry-run", "--json",
        ])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "verification" not in data

    def test_heal_help_shows_after_report(self, capsys):
        """--after-report appears in help text."""
        with pytest.raises(SystemExit) as exc:
            remediate.main(["heal", "--help"])
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "--after-report" in out


class TestFixHealFlag:
    """Test fix --heal flag (TH-C3)."""

    @patch("heal_controller.run_fixes")
    def test_fix_heal_flag_dispatches_to_heal(self, mock_run_fixes, tmp_path, capsys):
        """fix --heal redirects to heal controller in auto mode."""
        mock_run_fixes.return_value = []
        report = _write_eval_report(tmp_path)
        remediate.main(["fix", str(report), "--heal"])
        out = capsys.readouterr().out
        assert "Heal:" in out
        assert "auto" in out.lower()

    @patch("heal_controller.run_fixes")
    def test_fix_heal_dry_run(self, mock_run_fixes, tmp_path, capsys):
        """fix --heal --dry-run works."""
        mock_run_fixes.return_value = []
        report = _write_eval_report(tmp_path)
        remediate.main(["fix", str(report), "--heal", "--dry-run"])
        out = capsys.readouterr().out
        assert "dry-run" in out.lower() or "Heal:" in out

    def test_fix_help_shows_heal_flag(self, capsys):
        """--heal appears in fix help text."""
        with pytest.raises(SystemExit) as exc:
            remediate.main(["fix", "--help"])
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "--heal" in out
