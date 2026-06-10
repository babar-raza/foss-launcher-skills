#!/usr/bin/env python3
"""check_coverage_gate.py -- Local gate: verify test coverage meets threshold.

Runs pytest with --cov and checks the exit code. The fail_under threshold
is configured in pyproject.toml [tool.coverage.report].

Usage:
    python scripts/ci/checks/check_coverage_gate.py

Exit codes:
    0  Coverage meets or exceeds the configured threshold
    1  Coverage below threshold or test failures
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def main() -> int:
    cmd = [
        sys.executable, "-m", "pytest",
        "tests/",
        "-q",
        "-m", "not scout",
        "--ignore=tests/test_e2e_pipeline.py",
        "--cov=scripts",
        "--cov-report=term-missing",
    ]
    result = subprocess.run(cmd, cwd=REPO_ROOT)

    if result.returncode == 0:
        print("PASS: test coverage meets configured threshold")
    else:
        print("FAIL: test coverage below threshold or test failures detected")

    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
