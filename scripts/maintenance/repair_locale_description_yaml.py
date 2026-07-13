#!/usr/bin/env python
"""Repair locale content files whose YAML frontmatter no longer parses.

Incident: the 2026-07-12 "wave 3" locale-refresh commits (6812d020fb docs,
2ef1def182 reference) replaced multi-line translated ``description:`` scalars
with the truncated first line of the English multi-line description, leaving
an unterminated single quote. The same pattern also exists as uncommitted
working-tree corruption on kb.aspose.org files. Hugo aborts the whole site
build on the first unparseable frontmatter block.

Strategy (per broken file):
  1. Walk ``git log`` for the file and find the most recent committed version
     whose frontmatter parses ("last good").
  2. Textually replace only the ``description:`` block in the working file
     with the block from the last-good version (everything else is preserved
     byte-for-byte).
  3. If the result still does not parse (e.g. prompt-leak pollution beyond the
     description field), fall back to restoring the entire file from the
     last-good version, and report it as such.

Usage:
    python scripts/maintenance/repair_locale_description_yaml.py [--apply]

Without ``--apply`` the script is a dry run: it reports what it would do.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTENT_ROOT = REPO_ROOT / "content"

# A top-level frontmatter key at column 0, e.g. "date:", "weight:".
TOP_LEVEL_KEY_RE = re.compile(r"^[A-Za-z_][\w.-]*:")


def split_frontmatter(text: str) -> tuple[str, str] | None:
    """Return (frontmatter_without_delimiters, rest_including_delimiters)."""
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    return text[3:end], text[end:]


def frontmatter_parses(text: str) -> bool:
    parts = split_frontmatter(text)
    if parts is None:
        return False
    try:
        parsed = yaml.safe_load(parts[0])
    except yaml.YAMLError:
        return False
    return isinstance(parsed, dict)


def description_block_span(fm_text: str) -> tuple[int, int] | None:
    """Line span [start, end) of the description block inside frontmatter text."""
    lines = fm_text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.startswith("description:"):
            start = i
            break
    if start is None:
        return None
    end = start + 1
    while end < len(lines):
        line = lines[end]
        if line.strip() and TOP_LEVEL_KEY_RE.match(line):
            break
        end += 1
    return start, end


def replace_description_block(current: str, good: str) -> str | None:
    """Replace the description block in *current* with the one from *good*."""
    cur_parts = split_frontmatter(current)
    good_parts = split_frontmatter(good)
    if cur_parts is None or good_parts is None:
        return None
    cur_fm, cur_rest = cur_parts
    good_fm, _ = good_parts

    cur_span = description_block_span(cur_fm)
    good_span = description_block_span(good_fm)
    if cur_span is None or good_span is None:
        return None

    cur_lines = cur_fm.splitlines()
    good_lines = good_fm.splitlines()
    new_fm_lines = (
        cur_lines[: cur_span[0]]
        + good_lines[good_span[0] : good_span[1]]
        + cur_lines[cur_span[1] :]
    )
    return "---" + "\n".join(new_fm_lines) + "\n" + cur_rest.lstrip("\n")


def git_file_history(rel_path: str) -> list[str]:
    out = subprocess.run(
        ["git", "log", "--format=%H", "HEAD", "--", rel_path],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=True,
    ).stdout
    return out.split()


def git_show(sha: str, rel_path: str) -> str | None:
    r = subprocess.run(
        ["git", "show", f"{sha}:{rel_path}"],
        capture_output=True,
        cwd=REPO_ROOT,
    )
    if r.returncode != 0:
        return None
    return r.stdout.decode("utf-8", errors="replace")


def find_last_good(rel_path: str) -> tuple[str, str] | None:
    """Return (sha, text) of the most recent committed version that parses."""
    for sha in git_file_history(rel_path):
        text = git_show(sha, rel_path)
        if text is not None and frontmatter_parses(text):
            return sha, text
    return None


def find_broken_files() -> list[Path]:
    broken = []
    for path in sorted(CONTENT_ROOT.rglob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        if not text.startswith("---"):
            continue
        if not frontmatter_parses(text):
            broken.append(path)
    return broken


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write repairs (default: dry run)")
    args = parser.parse_args()

    broken = find_broken_files()
    print(f"broken files found: {len(broken)}")

    repaired = fell_back = failed = 0
    for path in broken:
        rel = path.relative_to(REPO_ROOT).as_posix()
        current = path.read_text(encoding="utf-8")
        last_good = find_last_good(rel)
        if last_good is None:
            print(f"FAIL   {rel} | no parseable committed version found")
            failed += 1
            continue
        sha, good_text = last_good

        fixed = replace_description_block(current, good_text)
        if fixed is not None and frontmatter_parses(fixed):
            action = "desc-restore"
            new_text = fixed
        else:
            # Surgical repair impossible (e.g. pollution beyond description).
            action = "FULL-restore"
            new_text = good_text
            fell_back += 1

        if args.apply:
            path.write_text(new_text, encoding="utf-8", newline="\n")
        print(f"{action:>12} {rel} <- {sha[:10]}")
        repaired += 1

    mode = "APPLIED" if args.apply else "DRY RUN"
    print(
        f"\n{mode}: {repaired} repaired ({fell_back} full-file restores), {failed} failed"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
