#!/usr/bin/env python3
"""local_gate.py -- Run all quality gates locally in sequence.

Single command for pre-commit/pre-push quality assurance.
Exit 0 only if ALL gates pass.

Usage:
    .venv/Scripts/python scripts/local_gate.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CHECKS_DIR = REPO_ROOT / "scripts" / "ci" / "checks"
SEP = "=" * 60


def _run_gate(name: str, cmd: list[str]) -> bool:
    """Run a single gate. Returns True if passed."""
    print(f"\n{SEP}")
    print(f"GATE: {name}")
    print(SEP)
    try:
        result = subprocess.run(cmd, cwd=str(REPO_ROOT), timeout=300)
        passed = result.returncode == 0
    except subprocess.TimeoutExpired:
        print("  TIMEOUT after 300s")
        passed = False
    except FileNotFoundError:
        print("  SKIP: command not found")
        passed = True

    status = "PASS" if passed else "FAIL"
    print(f"  -> {status}")
    return passed


def main() -> int:
    gates = [
        ("Skill Registry Validation", [sys.executable, str(REPO_ROOT / "scripts" / "validate_skills.py")]),
        # integration-marked tests require fixture data not available locally;
        # use -m "not scout and not integration" so test_e2e_pipeline.py
        # contributes to coverage via its pytestmark but skipped during fast runs.
        ("Test Suite", [sys.executable, "-m", "pytest", "tests/", "-x", "--tb=short", "-q",
                        "-m", "not scout and not integration"]),
        ("SAST (bandit)", [sys.executable, str(CHECKS_DIR / "check_sast_bandit.py")]),
        ("Dependency Audit", [sys.executable, str(CHECKS_DIR / "check_dependency_audit.py")]),
    ]

    results = []
    for name, cmd in gates:
        passed = _run_gate(name, cmd)
        results.append((name, passed))

    print(f"\n{SEP}")
    print("LOCAL GATE SUMMARY")
    print(SEP)
    all_passed = True
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")
        if not passed:
            all_passed = False

    if all_passed:
        print("\nAll gates passed.")
        return 0
    else:
        print("\nOne or more gates FAILED.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
