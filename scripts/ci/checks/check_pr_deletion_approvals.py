#!/usr/bin/env python3
"""check_pr_deletion_approvals.py — CI gate: PR deletions must have valid DGRs.

Reads the git diff between base and HEAD to find deleted and renamed-source
paths, classifies them by tier, and requires valid DGRs for T-01 paths.
T-00 paths always block the PR.

Usage (called from content-audit.yml GUARD-DEL-01):
    python scripts/ci/checks/check_pr_deletion_approvals.py --base origin/main

Exit codes:
    0   No ungoverned deletions
    2   T-00 or T-01 deletion without a valid DGR — blocks PR
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_staged_deletions import (  # type: ignore
    _get_pr_deletions,
    check_paths,
)

import os


def main(argv: "list[str] | None" = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    if "--base" not in argv:
        print(
            "Usage: check_pr_deletion_approvals.py --base <ref>",
            file=sys.stderr,
        )
        return 1

    idx = argv.index("--base")
    if idx + 1 >= len(argv):
        print("ERROR: --base requires a ref argument", file=sys.stderr)
        return 1

    base_ref = argv[idx + 1]
    paths = _get_pr_deletions(base_ref)

    if not paths:
        print("GUARD-DEL-01: OK — no deletions or renames in this PR.")
        return 0

    # Always run in blocking mode for CI
    os.environ["DELETION_GATE_PHASE"] = "2"
    return check_paths(paths)


if __name__ == "__main__":
    sys.exit(main())
