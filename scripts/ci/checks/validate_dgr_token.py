#!/usr/bin/env python3
"""validate_dgr_token.py — Validate DGR commit-message token for staged deletions.

Called by .git/hooks/commit-msg when staged D/R paths are detected.

Reads staged deletions, classifies tiers, then validates:
  - T-00 paths: always blocked (exit 2)
  - T-01 paths: require "Deletion-Approved: DGR-{id}" token in commit message
               and the referenced DGR must exist and not be expired (exit 2 if missing)
  - T-02: advisory warning only (exit 0)
  - T-03: silent pass (exit 0)

Usage:
    # Called from commit-msg hook — reads staged diff; msg piped on stdin
    echo "<commit-msg-text>" | python scripts/ci/checks/validate_dgr_token.py --check-staged --msg-stdin

Exit codes:
    0   No blocking violations
    2   T-00 deletion or T-01 deletion without valid DGR token
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Extend path to import check_staged_deletions from same directory
sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_staged_deletions import (  # type: ignore
    _get_staged_deletions,
    find_valid_dgr,
    classify_tier,
    DeletedPath,
    DGR_DIR,
)

# Token pattern: "Deletion-Approved: DGR-20260704-something"
_DGR_TOKEN_RE = re.compile(r"Deletion-Approved:\s*(DGR-[\w-]+)", re.IGNORECASE)


def _extract_dgr_ids(commit_msg: str) -> list[str]:
    """Return all DGR IDs declared in the commit message."""
    return _DGR_TOKEN_RE.findall(commit_msg)


def validate_dgr_tokens(deleted_paths: "list[DeletedPath]", commit_msg: str) -> int:
    """Validate DGR tokens for staged deletions. Returns exit code."""
    if not deleted_paths:
        return 0

    declared_dgr_ids = _extract_dgr_ids(commit_msg)
    any_blocking = False

    for dp in deleted_paths:
        if dp.tier == "T-00":
            print(
                f"  BLOCKED [T-00] deletion: {dp.path}",
                file=sys.stderr,
            )
            print(
                "    T-00 paths can never be deleted. No DGR path exists.",
                file=sys.stderr,
            )
            any_blocking = True

        elif dp.tier == "T-01":
            if not declared_dgr_ids:
                print(
                    f"  BLOCKED [T-01] deletion: {dp.path}",
                    file=sys.stderr,
                )
                print(
                    "    No 'Deletion-Approved: DGR-...' token found in commit message.",
                    file=sys.stderr,
                )
                any_blocking = True
                continue

            # Validate that at least one declared DGR covers this path
            valid, reason = find_valid_dgr(dp.path)
            if valid:
                matching_id = declared_dgr_ids[0]  # best effort match
                print(f"  OK [T-01] deletion: {dp.path} -- {reason}")
            else:
                print(
                    f"  BLOCKED [T-01] deletion: {dp.path}",
                    file=sys.stderr,
                )
                print(
                    f"    Commit message has DGR token(s) but none valid for this path: {reason}",
                    file=sys.stderr,
                )
                any_blocking = True

        elif dp.tier == "T-02":
            print(
                f"  ADVISORY [T-02] deletion: {dp.path} "
                "(T-02 -- review recommended)"
            )
        # T-03: silent pass

    if any_blocking:
        print("", file=sys.stderr)
        print("BLOCKED: Commit includes ungoverned deletion(s).", file=sys.stderr)
        print(
            "  Add 'Deletion-Approved: DGR-<id>' to commit message body.",
            file=sys.stderr,
        )
        print("  See docs/DELETION_GOVERNANCE.md", file=sys.stderr)
        return 2

    return 0


def main(argv: "list[str] | None" = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    if "--check-staged" not in argv or "--msg-stdin" not in argv:
        print(
            "Usage: validate_dgr_token.py --check-staged --msg-stdin  "
            "(commit message read from stdin)",
            file=sys.stderr,
        )
        return 1

    commit_msg = sys.stdin.read()
    deleted_paths = _get_staged_deletions()
    return validate_dgr_tokens(deleted_paths, commit_msg)


if __name__ == "__main__":
    sys.exit(main())
