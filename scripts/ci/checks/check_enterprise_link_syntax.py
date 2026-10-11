#!/usr/bin/env python3
"""Enterprise markdown link syntax gate (TC-BL-011).

Validates that enterprise *.aspose.com hyperlinks in content files have
syntactically correct markdown link syntax — specifically that every
markdown link opener `](https://` has a matching closing `)`.

Catches the class of bug introduced in bb68a63a22 where a one-character
transposition moved the `.` inside the URL parens, producing an unclosed
link that Hugo renders as broken hyperlink.

Rules:
  L1 (FAIL) — Unclosed markdown link: `[text](https://url` with no `)`
               on the same logical line before end-of-content or YAML
               string close.

Scope:
  Files matching content/**/_index.md or content/**/index.md.
  Code fences (``` ... ```) and inline code (` ... `) are excluded.

Usage — staged-file mode (pre-commit):
    check_enterprise_link_syntax.py FILE [FILE ...]
    Exit 1 if any FAIL; exit 0 otherwise.

Usage — scan mode (CI/reporting):
    check_enterprise_link_syntax.py --scan [--root CONTENT_ROOT]
    Exit 1 if any FAIL found.

Exit codes:
    0 — all pass
    1 — at least one FAIL
    2 — configuration error
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import NamedTuple


# ---------------------------------------------------------------------------
# Repo root
# ---------------------------------------------------------------------------

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parents[2]  # scripts/ci/checks -> repo root


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class Finding(NamedTuple):
    file: str
    line: int
    rule: str
    message: str
    level: str  # "FAIL" or "WARN"

    def __str__(self) -> str:
        return f"{self.level} [{self.rule}] {self.file}:{self.line} — {self.message}"


# ---------------------------------------------------------------------------
# Code-block stripping
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")


def _strip_code(text: str) -> str:
    """Replace code fences and inline code with spaces (preserving line numbers)."""
    def _blank(m: re.Match) -> str:
        s = m.group()
        return "\n".join(" " * len(line) for line in s.split("\n"))

    text = _FENCE_RE.sub(_blank, text)
    text = _INLINE_CODE_RE.sub(lambda m: " " * len(m.group()), text)
    return text


# ---------------------------------------------------------------------------
# Link syntax checker
# ---------------------------------------------------------------------------

_LINK_OPENER_RE = re.compile(r"\]\(https?://")


def check_file(path: Path) -> list[Finding]:
    """Return findings for a single content file."""
    try:
        raw = path.read_text(encoding="utf-8")
    except Exception as exc:
        return [Finding(str(path), 0, "L0", f"Could not read file: {exc}", "FAIL")]

    findings: list[Finding] = []
    text = _strip_code(raw)
    lines = text.split("\n")

    for lineno, line in enumerate(lines, 1):
        # Rule L1: find each markdown link opener, check for matching )
        for m in _LINK_OPENER_RE.finditer(line):
            url_start = m.end()  # position right after the (
            rest = line[url_start:]
            if ")" not in rest:
                # No closing ) on this line — broken link
                snippet = line[max(0, m.start() - 10):m.start() + 60].strip()
                findings.append(Finding(
                    file=str(path.relative_to(_REPO_ROOT)) if path.is_relative_to(_REPO_ROOT) else str(path),
                    line=lineno,
                    rule="L1",
                    message=f"Unclosed markdown link (missing closing ')') near: ...{snippet}...",
                    level="FAIL",
                ))

    return findings


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def _is_content_file(path: Path) -> bool:
    return path.name in ("_index.md", "index.md")


def scan_directory(root: Path) -> list[Path]:
    return [p for p in root.rglob("*.md") if _is_content_file(p)]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check enterprise markdown link syntax in content files."
    )
    parser.add_argument(
        "files", nargs="*", help="Specific files to check (staged-file mode)"
    )
    parser.add_argument(
        "--scan", action="store_true",
        help="Scan all content files (CI/reporting mode)"
    )
    parser.add_argument(
        "--root", default=str(_REPO_ROOT / "content"),
        help="Content root directory for --scan mode"
    )
    args = parser.parse_args(argv)

    if not args.files and not args.scan:
        parser.print_help()
        return 2

    if args.scan:
        root = Path(args.root)
        if not root.is_dir():
            print(f"ERROR: content root not found: {root}", file=sys.stderr)
            return 2
        paths = scan_directory(root)
    else:
        paths = [Path(f) for f in args.files]

    all_findings: list[Finding] = []
    for path in paths:
        if not path.exists():
            continue
        findings = check_file(path)
        all_findings.extend(findings)
        for f in findings:
            print(f)

    fails = [f for f in all_findings if f.level == "FAIL"]
    if fails:
        print(f"\n{len(fails)} FAIL(s) found.", file=sys.stderr)
        return 1

    if args.scan:
        print(f"OK: {len(paths)} files checked, 0 failures.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
