#!/usr/bin/env python3
"""Frontmatter YAML parse gate (all locales).

Validates that the YAML frontmatter of every content/*.md file parses with
a strict YAML loader and yields a mapping. Unlike the English-only audit
steps, this gate applies to ALL locales — locale files bypass Steps 2/4/5
of the pre-commit hook, which is how the 2026-07-12 "wave 3" locale-refresh
commits landed unparseable frontmatter on main and broke the Hugo site
builds (docs.aspose.org run 29230300508).

Rules:
  F1 (FAIL) — frontmatter does not parse as YAML
  F2 (FAIL) — frontmatter parses but is not a mapping
  F3 (FAIL) — file starts with '---' but has no closing '---' delimiter

For F1, the checker also detects the wave-3 corruption signature — a
single-quoted scalar opened on a `description:` line and never closed
before the next top-level key — and prints a targeted hint.

Scope:
  Files matching content/**/*.md (any subdomain, any locale). Files that do
  not start with '---' are skipped (no frontmatter — Hugo tolerates this).

Usage — staged-file mode (pre-commit):
    check_frontmatter_yaml.py --staged FILE [FILE ...]
    Reads the STAGED blob (:0:file), not the worktree copy. Without --staged
    the listed files are read from disk — which misses corruption when the
    index and worktree diverge (proven by the 2026-07-14 pilot negative
    control; on this host OneDrive makes index/worktree divergence routine).

Usage — scan mode (CI/reporting):
    check_frontmatter_yaml.py --scan [--root CONTENT_ROOT]

Exit codes:
    0 — all pass
    1 — at least one FAIL
    2 — configuration error
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

import yaml

TOP_LEVEL_KEY_RE = re.compile(r"^[A-Za-z_][\w.-]*:")


def find_unterminated_quote_line(fm_text: str) -> int | None:
    """Best-effort detector for the wave-3 signature.

    Returns the 1-based frontmatter line number of a top-level key whose
    value opens a single-quoted scalar that is not closed on that line and
    is followed by another top-level key line (i.e. the quote swallows
    subsequent keys).
    """
    lines = fm_text.splitlines()
    for i, line in enumerate(lines):
        m = TOP_LEVEL_KEY_RE.match(line)
        if not m:
            continue
        value = line[m.end():].strip()
        if not value.startswith("'"):
            continue
        # Count unescaped single quotes: an even count means the scalar
        # closed on this line ('' is an escaped quote and contributes 2).
        if value.count("'") % 2 == 0:
            continue
        # Unclosed on its own line — corruption only if a later top-level
        # key gets swallowed before the quote closes. Key-match is checked
        # first: the closing quote may sit ON a swallowed key line (e.g.
        # date: '2026-03-29' terminating the runaway scalar).
        for later in lines[i + 1:]:
            if TOP_LEVEL_KEY_RE.match(later):
                return i + 1
            if "'" in later:
                break
    return None


def staged_blob(path: str) -> str | None:
    """Return the STAGED content of a path (:0:path), or None if not in index."""
    result = subprocess.run(
        ["git", "show", f":0:{path.replace(chr(92), '/')}"],
        capture_output=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8", errors="replace")


def check_text(text: str, label: str) -> list[str]:
    """Return failure messages for one already-read content string."""
    if not text.startswith("---"):
        return []
    return _check_frontmatter(text, label)


def check_file(path: Path) -> list[str]:
    """Return a list of failure messages for one file (empty = pass)."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [f"F1 FAIL {path}: unreadable: {exc}"]
    return check_text(text, str(path))


def _check_frontmatter(text: str, label: str) -> list[str]:
    end = text.find("\n---", 3)
    if end == -1:
        return [f"F3 FAIL {label}: frontmatter has no closing '---' delimiter"]
    fm_text = text[3:end]
    try:
        parsed = yaml.safe_load(fm_text)
    except yaml.YAMLError as exc:
        msg = str(exc).replace("\n", " ")[:200]
        failures = [f"F1 FAIL {label}: frontmatter does not parse: {msg}"]
        bad_line = find_unterminated_quote_line(fm_text)
        if bad_line is not None:
            failures.append(
                f"        hint: unterminated single-quoted scalar opened at "
                f"frontmatter line {bad_line} swallows later keys "
                f"(wave-3 truncated-description signature)"
            )
        return failures
    if not isinstance(parsed, dict):
        return [
            f"F2 FAIL {label}: frontmatter parses but is "
            f"{type(parsed).__name__}, not a mapping"
        ]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description="Frontmatter YAML parse gate")
    parser.add_argument("files", nargs="*", help="content .md files to check")
    parser.add_argument("--staged", action="store_true",
                        help="validate STAGED blobs (:0:file) instead of worktree copies")
    parser.add_argument("--scan", action="store_true",
                        help="scan the whole content tree instead of listed files")
    parser.add_argument("--root", default="content",
                        help="content root for --scan mode (default: content)")
    args = parser.parse_args()

    if args.scan:
        root = Path(args.root)
        if not root.is_dir():
            print(f"ERROR: content root not found: {root}", file=sys.stderr)
            return 2
        targets = sorted(root.rglob("*.md"))
    elif args.files:
        targets = [Path(f) for f in args.files if f.endswith(".md")]
    else:
        parser.print_usage(sys.stderr)
        return 2

    fail_count = 0
    checked = 0
    for path in targets:
        if args.staged and not args.scan:
            text = staged_blob(str(path))
            if text is None:
                continue  # deleted / not in index
            checked += 1
            failures = check_text(text, str(path))
        else:
            if not path.is_file():
                continue  # deleted/renamed-away staged paths
            checked += 1
            failures = check_file(path)
        if failures:
            fail_count += 1
            for msg in failures:
                print(msg)
    if fail_count:
        print(f"\ncheck_frontmatter_yaml: {fail_count}/{checked} file(s) FAILED")
        return 1
    print(f"check_frontmatter_yaml: {checked} file(s) OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
