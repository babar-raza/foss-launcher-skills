#!/usr/bin/env python3
"""Classify files where only graded_at changed."""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

_GRADED_AT_DIFF_LINE_RE = re.compile(r"^[+-]graded_at:")


def _classify_file(path: str, *, mode: str) -> str:
    try:
        if mode == "staged":
            cmd = ["git", "diff", "--cached", "HEAD", "--", path]
        else:
            cmd = ["git", "diff", "HEAD", "--", path]
        result = subprocess.run(cmd, capture_output=True, text=True)
    except Exception:
        return "D"
    if result.returncode != 0:
        return "D"
    diff_lines = []
    for line in result.stdout.splitlines():
        if line.startswith(("+++", "---", "@@")):
            continue
        if line.startswith(("+", "-")):
            diff_lines.append(line)
    if not diff_lines:
        return "BC"
    if any(not _GRADED_AT_DIFF_LINE_RE.match(line) for line in diff_lines):
        return "BC"
    return "A"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files-from", required=True)
    parser.add_argument("--mode", choices=("staged", "worktree"), default="staged")
    args = parser.parse_args(argv)
    try:
        paths = [line.strip() for line in Path(args.files_from).read_text(encoding="utf-8").splitlines() if line.strip()]
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
    raise SystemExit(main())
