#!/usr/bin/env python3
"""check_graded_at_only.py — Classify staged .md files where only graded_at: changed.

Used by the pre-commit hook (Step 10 in scripts/pre-commit-audit.sh) and
S-76 commit skill (Step B.4, --mode worktree) to identify files that should be
reverted from the working tree rather than committed.

Classification rules (Cases A/B/C/D):
  A — Only graded_at: line(s) changed (diff has +/- lines exclusively for graded_at).
      Print path to stdout. Caller should revert the file.
  B — graded_at changed AND other lines also changed.
      Silent pass (no output). Legitimate change — allow commit.
  C — No graded_at in diff, other changes present (or diff empty).
      Silent pass (no output). Unrelated to this rule.
  D — Subprocess failure or unreadable diff.
      Print PARSE_FAILURE:<path> to stderr. Exit code 2.

Usage:
    .venv/Scripts/python scripts/pipeline/check_graded_at_only.py --files-from <list.txt>
    .venv/Scripts/python scripts/pipeline/check_graded_at_only.py --files-from <list.txt> --mode staged
    .venv/Scripts/python scripts/pipeline/check_graded_at_only.py --files-from <list.txt> --mode worktree
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parents[2]  # commands/governance/ -> commands/ -> pipeline/
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from core.env_loader import load_env  # noqa: E402

_GRADED_AT_DIFF_LINE_RE = re.compile(r"^[+-]graded_at:")


def _classify_file(path: str, *, mode: str) -> str:
    """Run git diff and classify the file.

    Returns:
        'A'    — graded_at-only diff
        'BC'   — allow (meaningful diff or no diff)
        'D'    — parse/subprocess failure
    """
    try:
        if mode == "staged":
            result = subprocess.run(
                ["git", "diff", "--cached", "HEAD", "--", path],
                capture_output=True,
                text=True,
            )
        else:  # worktree
            result = subprocess.run(
                ["git", "diff", "HEAD", "--", path],
                capture_output=True,
                text=True,
            )
    except Exception:
        return "D"

    if result.returncode != 0:
        return "D"

    diff_lines = []
    for line in result.stdout.splitlines():
        # Skip unified diff header lines (+++ --- @@ etc.)
        if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
            continue
        if line.startswith("+") or line.startswith("-"):
            diff_lines.append(line)

    if not diff_lines:
        # No diff (Case C — new file with no HEAD, or unstaged)
        return "BC"

    non_graded_at = [l for l in diff_lines if not _GRADED_AT_DIFF_LINE_RE.match(l)]

    if non_graded_at:
        # Case B or C — meaningful changes present
        return "BC"

    # All diff lines are graded_at changes — Case A
    return "A"


def main() -> int:
    load_env()

    parser = argparse.ArgumentParser(
        description="Classify staged .md files where only graded_at: changed."
    )
    parser.add_argument(
        "--files-from",
        metavar="FILE",
        required=True,
        help="Path to a text file containing one file path per line.",
    )
    parser.add_argument(
        "--mode",
        choices=["staged", "worktree"],
        default="staged",
        help="Whether to diff against staged (--cached) or worktree. Default: staged.",
    )
    args = parser.parse_args()

    files_from = Path(args.files_from)
    try:
        paths = [
            line.strip()
            for line in files_from.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except OSError as exc:
        print(f"PARSE_FAILURE:{args.files_from} (cannot read: {exc})", file=sys.stderr)
        return 2

    exit_code = 0
    for path in paths:
        result = _classify_file(path, mode=args.mode)
        if result == "A":
            print(path)
        elif result == "D":
            print(f"PARSE_FAILURE:{path}", file=sys.stderr)
            exit_code = 2

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
