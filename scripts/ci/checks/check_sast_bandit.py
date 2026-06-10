#!/usr/bin/env python3
"""Check SAST findings via bandit — security scanning gate.

Runs bandit against scripts/ targeting MEDIUM+ severity issues.
Exit 0 = clean, Exit 1 = findings found.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
TARGET_DIR = REPO_ROOT / "scripts"


def main() -> int:
    try:
        result = subprocess.run(
            [
                sys.executable, "-m", "bandit",
                "-r", str(TARGET_DIR),
                "--severity-level", "medium",  # MEDIUM+ severity
                "-q",   # quiet (no banner)
                "--format", "json",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError:
        print("SKIP: bandit not installed (pip install bandit)")
        return 0
    except subprocess.TimeoutExpired:
        print("FAIL: bandit timed out after 120s")
        return 1

    if result.returncode == 0:
        print("PASS: bandit SAST scan — no MEDIUM+ severity findings")
        return 0

    # Parse JSON output for summary
    import json
    try:
        data = json.loads(result.stdout)
        count = len(data.get("results", []))
        print(f"FAIL: bandit found {count} MEDIUM+ severity finding(s)")
        for finding in data.get("results", [])[:5]:
            print(f"  {finding.get('filename', '?')}:{finding.get('line_number', '?')} "
                  f"[{finding.get('test_id', '?')}] {finding.get('issue_text', '?')}")
    except (json.JSONDecodeError, KeyError):
        print(f"FAIL: bandit returned exit code {result.returncode}")
        if result.stderr:
            print(result.stderr[:500])
    return 1


if __name__ == "__main__":
    sys.exit(main())
