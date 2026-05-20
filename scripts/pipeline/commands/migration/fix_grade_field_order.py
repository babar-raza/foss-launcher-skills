# Adapted from aspose.org
"""Repair utility: reorder grade frontmatter fields to satisfy check_grade_integrity.py.

Root cause: grade_writer.py (before fix) emitted graded_content_hash immediately after
graded_at, before graded_model_sha / graded_evaluators / graded_logic_version.
check_grade_integrity.py treats any non-grade key between two grade keys as a
non_consecutive anomaly.

Canonical write order (matches corrected grade_writer.py):
  grade → graded_at → graded_model_sha → graded_evaluators → graded_logic_version
  → graded_content_hash → grade_final → grade_stale_reason → grade_stale_targets
  → grade_reasons

Usage:
    python scripts/pipeline/commands/migration/fix_grade_field_order.py               # dry-run
    python scripts/pipeline/commands/migration/fix_grade_field_order.py --apply       # write fixes
    python scripts/pipeline/commands/migration/fix_grade_field_order.py --apply --limit 10  # first 10 only
    python scripts/pipeline/commands/migration/fix_grade_field_order.py --apply --scope content/blog
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
_CONTENT_DIR = _REPO_ROOT / "content"

# Canonical position order for grade-related keys.
_GRADE_KEY_ORDER = [
    "grade",
    "graded_at",
    "graded_model_sha",
    "graded_evaluators",
    "graded_logic_version",
    "graded_content_hash",
    "grade_final",
    "grade_stale_reason",
    "grade_stale_targets",
    "grade_reasons",
]
_GRADE_KEY_SET = set(_GRADE_KEY_ORDER)

# Regex to capture a YAML frontmatter block
_FM_RE = re.compile(r"^(---\s*\n)(.*?)(\n---)", re.DOTALL)

# Matches a top-level YAML key block: one key line plus any indented continuation lines
_KEY_BLOCK_RE = re.compile(r"^(\S[^\n]*)(?:\n(?:[ \t][^\n]*))*", re.MULTILINE)


def _key_name(line: str) -> Optional[str]:
    """Return the key name from a YAML key line, or None if not a key line."""
    m = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*):", line)
    return m.group(1) if m else None


def _reorder_frontmatter(fm_text: str) -> tuple[str, bool]:
    """Reorder grade keys inside frontmatter text.

    Returns (new_fm_text, changed: bool).
    Only grade-related keys are moved; all other keys stay in place.
    The grade block is extracted as a unit and re-sorted, then re-inserted
    at the position where the first grade key was found.
    """
    # Parse into (start_pos, end_pos, key_name) tuples for all top-level key blocks
    key_blocks: list[tuple[int, int, Optional[str]]] = []
    for m in _KEY_BLOCK_RE.finditer(fm_text):
        key = _key_name(m.group(0))
        key_blocks.append((m.start(), m.end(), key))

    grade_block_texts: list[str] = []
    first_grade_start: Optional[int] = None
    last_grade_end: Optional[int] = None

    for start, end, key in key_blocks:
        if key in _GRADE_KEY_SET:
            grade_block_texts.append(fm_text[start:end])
            if first_grade_start is None:
                first_grade_start = start
            last_grade_end = end

    if not grade_block_texts:
        return fm_text, False

    # Sort grade blocks by canonical order
    def _sort_key(block: str) -> int:
        k = _key_name(block)
        try:
            return _GRADE_KEY_ORDER.index(k)
        except ValueError:
            return len(_GRADE_KEY_ORDER)

    sorted_grade_blocks = sorted(grade_block_texts, key=_sort_key)

    if sorted_grade_blocks == grade_block_texts:
        return fm_text, False

    # Find the separator text that was between consecutive grade keys in the original.
    # We want to know if any non-grade text appeared between grade keys — if so,
    # we need to carefully reconstruct without losing that text.
    # Strategy: rebuild the entire frontmatter with grade keys removed,
    # then splice the sorted grade block back in at first_grade_start.

    # Build non-grade segments by removing all grade key block text from fm_text
    result = fm_text
    # We'll do a single-pass substitution: remove all grade key lines and
    # their continuations, then insert sorted grade block at the right position.
    # Simpler approach: slice out the region first_grade_start..last_grade_end,
    # replace with sorted grade keys joined by newlines, preserve everything else.

    # Collect all grade key positions in order they appear in the original
    grade_positions: list[tuple[int, int]] = [
        (start, end) for start, end, key in key_blocks if key in _GRADE_KEY_SET
    ]

    # Build the replacement: sorted grade blocks joined with the separators that
    # originally appeared between them (to preserve newline formatting)
    # For simplicity, join with '\n' — the original separators between grade keys
    # are single newlines since each block ends at the last non-whitespace char.
    # Non-grade keys between grade keys (the anomaly!) are intentionally dropped
    # from the grade region and left in place outside.

    # Rebuild: take everything outside the range [first_grade_start, last_grade_end],
    # plus the sorted grade blocks joined with '\n', in place of that range.
    prefix = fm_text[:first_grade_start]
    suffix = fm_text[last_grade_end:]

    # Any non-grade text that was interspersed BETWEEN grade keys is moved outside:
    # collect non-grade key blocks that fall between first_grade_start and last_grade_end
    interstitial_non_grade: list[str] = []
    for start, end, key in key_blocks:
        if first_grade_start < start < last_grade_end and key not in _GRADE_KEY_SET:
            interstitial_non_grade.append(fm_text[start:end])

    # Re-insert interstitial non-grade content after the grade block (not before)
    grade_section = "\n".join(sorted_grade_blocks)
    interstitial = ("\n" + "\n".join(interstitial_non_grade)) if interstitial_non_grade else ""

    new_fm = prefix + grade_section + interstitial + suffix
    return new_fm, new_fm != fm_text


def fix_file(path: Path, apply: bool) -> Optional[str]:
    """Check and optionally fix a single file.

    Returns:
        None  — file already correct (no change needed)
        str   — description of change made/that would be made (may be ERROR:...)
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    m = _FM_RE.match(text)
    if not m:
        return None

    open_fence = m.group(1)
    fm_text = m.group(2)
    close_fence = m.group(3)
    rest = text[m.end():]

    new_fm, changed = _reorder_frontmatter(fm_text)
    if not changed:
        return None

    if not apply:
        return f"WOULD FIX: {path}"

    new_text = open_fence + new_fm + close_fence + rest
    dir_ = path.parent
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(dir=dir_, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(new_text)
        os.replace(tmp, path)
    except OSError as exc:
        if tmp:
            try:
                os.unlink(tmp)
            except OSError:
                pass
        return f"ERROR: {path}: {exc}"

    return f"FIXED: {path}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reorder grade frontmatter fields in content files."
    )
    parser.add_argument("--apply", action="store_true",
                        help="Write changes (default: dry-run, print only)")
    parser.add_argument("--limit", type=int, default=0,
                        help="Stop after N files changed (0 = no limit)")
    parser.add_argument("--scope", type=str, default=None,
                        help="Restrict to subtree path relative to repo root "
                             "(e.g. content/blog)")
    parser.add_argument("--files", nargs="+",
                        help="Explicit file list (overrides --scope)")
    args = parser.parse_args(argv)

    if args.files:
        targets = [Path(f) for f in args.files]
    else:
        root = (_REPO_ROOT / args.scope) if args.scope else _CONTENT_DIR
        targets = sorted(root.rglob("*.md"))

    changed = 0
    errors = 0
    for path in targets:
        result = fix_file(path, apply=args.apply)
        if result is None:
            continue
        if result.startswith("ERROR"):
            print(result, file=sys.stderr)
            errors += 1
        else:
            print(result)
            changed += 1
        if args.limit and changed >= args.limit:
            break

    verb = "Fixed" if args.apply else "Would fix"
    print(f"\n{verb}: {changed} file(s)  Errors: {errors}", file=sys.stderr)

    if not args.apply and changed > 0:
        return 1   # anomalies found; run with --apply
    return 0 if errors == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
