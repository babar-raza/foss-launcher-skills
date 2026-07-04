"""Tests for scripts/ci/checks/check_sast_bandit.py and check_dependency_audit.py.

Covers all execution paths (pass, fail, timeout, FileNotFoundError) via
subprocess mocking so the tests run fast and don't need bandit or pip-audit
installed.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci" / "checks"))


def _proc(returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


# ---------------------------------------------------------------------------
# check_sast_bandit
# ---------------------------------------------------------------------------

class TestCheckSastBandit:
    def test_pass_returns_0(self, capsys) -> None:
        """Returns 0 when bandit exits 0 (no findings)."""
        with patch("check_sast_bandit.subprocess.run", return_value=_proc(0)):
            import check_sast_bandit
            rc = check_sast_bandit.main()
        assert rc == 0
        assert "PASS" in capsys.readouterr().out

    def test_fail_with_findings_returns_1(self, capsys) -> None:
        """Returns 1 when bandit finds MEDIUM+ issues and prints summary."""
        findings = json.dumps({
            "results": [
                {
                    "filename": "scripts/foo.py",
                    "line_number": 42,
                    "test_id": "B301",
                    "issue_text": "Pickle usage",
                }
            ]
        })
        with patch("check_sast_bandit.subprocess.run", return_value=_proc(1, stdout=findings)):
            import check_sast_bandit
            rc = check_sast_bandit.main()
        assert rc == 1
        out = capsys.readouterr().out
        assert "FAIL" in out

    def test_fail_invalid_json_returns_1(self, capsys) -> None:
        """Returns 1 when bandit exits non-zero and output is not JSON."""
        with patch("check_sast_bandit.subprocess.run", return_value=_proc(1, stdout="not-json")):
            import check_sast_bandit
            rc = check_sast_bandit.main()
        assert rc == 1
        assert "FAIL" in capsys.readouterr().out

    def test_not_installed_returns_0(self, capsys) -> None:
        """Returns 0 (SKIP) when bandit is not installed."""
        with patch("check_sast_bandit.subprocess.run", side_effect=FileNotFoundError):
            import check_sast_bandit
            rc = check_sast_bandit.main()
        assert rc == 0
        assert "SKIP" in capsys.readouterr().out

    def test_timeout_returns_1(self, capsys) -> None:
        """Returns 1 when bandit times out."""
        with patch(
            "check_sast_bandit.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["bandit"], timeout=120),
        ):
            import check_sast_bandit
            rc = check_sast_bandit.main()
        assert rc == 1
        assert "FAIL" in capsys.readouterr().out

    def test_fail_with_stderr(self, capsys) -> None:
        """Returns 1 and prints stderr when JSON parse fails and stderr present."""
        with patch(
            "check_sast_bandit.subprocess.run",
            return_value=_proc(1, stdout="bad", stderr="error detail"),
        ):
            import check_sast_bandit
            rc = check_sast_bandit.main()
        assert rc == 1


# ---------------------------------------------------------------------------
# check_dependency_audit
# ---------------------------------------------------------------------------

class TestCheckDependencyAudit:
    def test_pass_returns_0(self, capsys) -> None:
        """Returns 0 when pip-audit exits 0."""
        with patch("check_dependency_audit.subprocess.run", return_value=_proc(0)):
            import check_dependency_audit
            rc = check_dependency_audit.main()
        assert rc == 0
        assert "PASS" in capsys.readouterr().out

    def test_vulnerable_packages_returns_0(self, capsys) -> None:
        """Returns 0 (advisory) even when pip-audit finds vulns in dev deps."""
        output = "Found 3 known vulnerabilities\nvulnpkg 1.0.0  CVE-9999-1234"
        with patch(
            "check_dependency_audit.subprocess.run",
            return_value=_proc(1, stdout=output),
        ):
            import check_dependency_audit
            rc = check_dependency_audit.main()
        # Returns 0 (advisory mode — dev tooling vulns are not blocking)
        assert rc == 0
        out = capsys.readouterr().out
        assert "WARN" in out

    def test_not_installed_returns_0(self, capsys) -> None:
        """Returns 0 (SKIP) when pip-audit is not installed."""
        with patch("check_dependency_audit.subprocess.run", side_effect=FileNotFoundError):
            import check_dependency_audit
            rc = check_dependency_audit.main()
        assert rc == 0
        assert "SKIP" in capsys.readouterr().out

    def test_timeout_returns_1(self, capsys) -> None:
        """Returns 1 when pip-audit times out."""
        with patch(
            "check_dependency_audit.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["pip-audit"], timeout=120),
        ):
            import check_dependency_audit
            rc = check_dependency_audit.main()
        assert rc == 1
        assert "FAIL" in capsys.readouterr().out

    def test_stderr_output_included(self, capsys) -> None:
        """When stdout is empty, stderr is used for advisory output."""
        with patch(
            "check_dependency_audit.subprocess.run",
            return_value=_proc(1, stdout="", stderr="some stderr output"),
        ):
            import check_dependency_audit
            rc = check_dependency_audit.main()
        assert rc == 0  # advisory mode
