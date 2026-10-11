"""Pre-commit guard: reject content files containing U+FFFD replacement characters.

U+FFFD (UTF-8 bytes EF BF BD) indicates encoding corruption — a multi-byte
character was misinterpreted during generation or translation.  This guard
prevents corrupted content from reaching the live site.

Usage (called by pre-commit hook):
    python scripts/ci/check_content_encoding.py file1.md file2.md ...

Exit codes:
    0  — all files clean
    1  — at least one file contains U+FFFD
"""
from __future__ import annotations

import sys
from pathlib import Path

_FFFD = b"\xef\xbf\xbd"


def check_files(paths: list[str]) -> int:
    failures: list[str] = []
    for p in paths:
        try:
            data = Path(p).read_bytes()
        except OSError:
            continue
        if _FFFD not in data:
            continue
        for i, line in enumerate(data.split(b"\n"), 1):
            if _FFFD in line:
                failures.append(f"  {p}:{i}")
    if failures:
        print(
            "BLOCKED: U+FFFD replacement character found in staged content:",
            file=sys.stderr,
        )
        for f in failures:
            print(f, file=sys.stderr)
        print(
            "Fix: replace corrupted characters with correct text before committing.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(check_files(sys.argv[1:]))
