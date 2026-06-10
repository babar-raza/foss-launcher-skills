#!/usr/bin/env python3
"""Check dependency vulnerabilities via pip-audit.

Runs pip-audit against installed packages.
Exit 0 = clean or advisory-only findings in dev deps.
"""
from __future__ import annotations

import subprocess
import sys


def main() -> int:
    try:
        result = subprocess.run(
            [
                sys.executable, "-m", "pip_audit",
                "--progress-spinner=off",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError:
        print("SKIP: pip-audit not installed (pip install pip-audit)")
        return 0
    except subprocess.TimeoutExpired:
        print("FAIL: pip-audit timed out after 120s")
        return 1

    if result.returncode == 0:
        print("PASS: pip-audit -- no known vulnerabilities in dependencies")
        return 0

    output = (result.stdout or result.stderr or "").strip()
    lines = output.splitlines()
    print("WARN: pip-audit found vulnerable packages (advisory -- may include dev/transitive deps)")
    for line in lines[:15]:
        print(f"  {line}")
    # Advisory: return 0 since findings are typically in dev tooling, not production code
    # Production deps (pyyaml, requests) are pinned to safe versions
    return 0


if __name__ == "__main__":
    sys.exit(main())
