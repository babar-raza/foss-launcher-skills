#!/usr/bin/env python3
"""check_pipeline_root_clean.py — Block new .py files at pipeline/ root.

After the scripts/ transition architecture migration, only _bootstrap.py and
__init__.py may exist at scripts/pipeline/ root. All other .py files must be
in commands/, lib/, or other subdirectories.

Usage:
    python scripts/ci/checks/check_pipeline_root_clean.py
    python scripts/ci/checks/check_pipeline_root_clean.py --dry-run

Exit codes:
    0 — root is clean
    1 — unauthorized .py file(s) found at root
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PIPELINE_ROOT = REPO_ROOT / "scripts" / "pipeline"

# Only these .py files are allowed at pipeline/ root
ALLOWLIST = {"_bootstrap.py", "__init__.py"}


def check() -> list[str]:
    """Return list of unauthorized .py files at pipeline root."""
    violations = []
    for p in sorted(PIPELINE_ROOT.glob("*.py")):
        if p.name not in ALLOWLIST:
            violations.append(p.name)
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Report issues but always exit 0")
    args = parser.parse_args()

    violations = check()
    if violations:
        print(f"FAIL: {len(violations)} unauthorized .py file(s) at scripts/pipeline/ root:",
              file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        print(f"\nAllowed: {sorted(ALLOWLIST)}", file=sys.stderr)
        print("Move new scripts to commands/{domain}/ or lib/.", file=sys.stderr)
        if args.dry_run:
            print("\n(dry-run: exiting 0 despite failures)")
            return 0
        return 1

    print(f"OK: pipeline root clean (only {sorted(ALLOWLIST)} present)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
