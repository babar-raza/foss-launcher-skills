"""Tests for scripts/ci/checks/check_audit_regression.py.

Covers:
  - Empty audit-results.json is treated as a tool crash (exit 2), not a silent
    pass. audit.py's "all" mode only writes JSON once, after its whole product
    loop completes (audit/runner.py: report_json() is the sole stdout write),
    so an empty file can only mean the tool crashed before finishing.
  - Well-formed results within baseline pass (exit 0).
  - Well-formed results exceeding baseline fail (exit 1).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CHECKER = REPO_ROOT / "scripts" / "ci" / "checks" / "check_audit_regression.py"


def _run_checker(current: Path, baseline: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECKER), str(current), str(baseline)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


def test_empty_current_file_fails_not_passes(tmp_path: Path) -> None:
    current = tmp_path / "audit-results.json"
    current.write_text("", encoding="utf-8")
    baseline = tmp_path / "baseline.json"
    baseline.write_text("{}", encoding="utf-8")

    result = _run_checker(current, baseline)

    assert result.returncode == 2
    assert "crashed" in result.stderr.lower()


def test_within_baseline_passes(tmp_path: Path) -> None:
    current = tmp_path / "audit-results.json"
    current.write_text(
        json.dumps({
            "products_checked": ["cells/net"],
            "findings": [{"level": "FAIL", "file": "content/reference.aspose.org/en/cells/net/Foo.md"}],
        }),
        encoding="utf-8",
    )
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"cells/net": {"fail_count": 1}}), encoding="utf-8")

    result = _run_checker(current, baseline)

    assert result.returncode == 0


def test_exceeding_baseline_fails(tmp_path: Path) -> None:
    current = tmp_path / "audit-results.json"
    current.write_text(
        json.dumps({
            "products_checked": ["cells/net"],
            "findings": [
                {"level": "FAIL", "file": "content/reference.aspose.org/en/cells/net/Foo.md"},
                {"level": "FAIL", "file": "content/reference.aspose.org/en/cells/net/Bar.md"},
            ],
        }),
        encoding="utf-8",
    )
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"cells/net": {"fail_count": 1}}), encoding="utf-8")

    result = _run_checker(current, baseline)

    assert result.returncode == 1
    assert "REGRESSION" in result.stderr
