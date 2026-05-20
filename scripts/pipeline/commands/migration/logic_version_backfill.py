# Adapted from aspose.org
#!/usr/bin/env python3
"""logic_version_backfill.py — Backfill graded_logic_version="2" for existing graded files.

Scans all .md files that have a ``grade:`` field but no ``graded_logic_version:``
field and inserts ``graded_logic_version: "2"`` into the grade block.

All pre-existing grades were produced by logic version 2; this backfill makes
that explicit so downstream tools can distinguish pre-backfill files from future
grades produced with a different version.

Usage:
    python logic_version_backfill.py [--apply] [--path PATH]

    --dry-run  (default) Show what would be changed, no writes
    --apply    Write changes to disk
    --path     Directory to scan (default: content/ relative to repo root)
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE.parent.parent))  # scripts/pipeline/  # scripts/pipeline/

from core.fs import atomic_write  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BACKFILL_VERSION = "2"

# Detect presence of grade field
_GRADE_RE = re.compile(r"^grade:\s*[A-F]\s*$", re.MULTILINE)

# Detect presence of graded_logic_version field
_LOGIC_VER_RE = re.compile(r"^graded_logic_version:", re.MULTILINE)

# Detect graded_evaluators line (insert graded_logic_version after it)
_GRADED_EVALUATORS_RE = re.compile(r"^(graded_evaluators:[^\n]*\n)", re.MULTILINE)

# Detect graded_at line (fallback insert point)
_GRADED_AT_RE = re.compile(r"^(graded_at:[^\n]*\n)", re.MULTILINE)

from core.markdown import _FRONTMATTER_WRITER_RE as _FRONTMATTER_RE


def _insert_logic_version(text: str, version: str) -> str | None:
    """Insert ``graded_logic_version: "<version>"`` after graded_evaluators or graded_at.

    Operates only within the frontmatter block so that field names appearing
    in body content do not produce a spurious insertion.

    Returns the modified text, or None if the grade block cannot be found/modified.
    """
    insert_line = f'graded_logic_version: "{version}"\n'

    # Extract frontmatter block; abort if none found
    fm_match = _FRONTMATTER_RE.match(text)
    if fm_match is None:
        return None
    fm_start = fm_match.start()
    fm_end = fm_match.end()
    frontmatter = fm_match.group(0)
    body = text[fm_end:]

    # Prefer inserting after graded_evaluators
    m = _GRADED_EVALUATORS_RE.search(frontmatter)
    if m:
        pos = m.end()
        return text[:fm_start] + frontmatter[:pos] + insert_line + frontmatter[pos:] + body

    # Fallback: insert after graded_at
    m = _GRADED_AT_RE.search(frontmatter)
    if m:
        pos = m.end()
        return text[:fm_start] + frontmatter[:pos] + insert_line + frontmatter[pos:] + body

    # Last resort: insert after the grade: line itself
    grade_m = _GRADE_RE.search(frontmatter)
    if grade_m:
        pos = grade_m.end()
        # Ensure we're at a newline boundary
        if frontmatter[pos - 1] != "\n":
            pos = frontmatter.find("\n", pos) + 1
        return text[:fm_start] + frontmatter[:pos] + insert_line + frontmatter[pos:] + body

    return None


def process_file(filepath: Path, apply: bool) -> str:
    """Process a single file.

    Returns one of: 'skipped-no-grade', 'skipped-ok', 'updated', 'error'.
    """
    try:
        text = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"  ERROR reading {filepath}: {exc}")
        return "error"

    # Must have a grade field
    if not _GRADE_RE.search(text):
        return "skipped-no-grade"

    # Already has graded_logic_version — skip
    if _LOGIC_VER_RE.search(text):
        return "skipped-ok"

    # Insert graded_logic_version
    new_text = _insert_logic_version(text, BACKFILL_VERSION)
    if new_text is None:
        print(f"  ERROR could not find insert point in {filepath}")
        return "error"

    if apply:
        try:
            atomic_write(filepath, new_text)
        except Exception as exc:
            print(f"  ERROR writing {filepath}: {exc}")
            return "error"
        print(f"  UPDATED  {filepath}")
    else:
        print(f"  WOULD UPDATE  {filepath}")

    return "updated"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill graded_logic_version=2 for existing graded files."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Write changes to disk (default: dry-run)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print what would be changed without writing (default behaviour)",
    )
    parser.add_argument(
        "--path",
        default=None,
        help="Directory to scan (default: content/ relative to repo root)",
    )
    args = parser.parse_args()

    apply = args.apply

    if args.path:
        scan_root = Path(args.path).resolve()
    else:
        scan_root = (_HERE / ".." / ".." / ".." / ".." / "content").resolve()

    if not scan_root.exists():
        print(f"ERROR: scan path does not exist: {scan_root}", file=sys.stderr)
        sys.exit(1)

    mode_label = "APPLY" if apply else "DRY-RUN"
    print(f"logic_version_backfill — mode={mode_label}  root={scan_root}")
    print()

    total = 0
    skipped_ok = 0
    skipped_no_grade = 0
    updated = 0
    errors = 0

    for md_file in sorted(scan_root.rglob("*.md")):
        total += 1
        result = process_file(md_file, apply=apply)
        if result == "skipped-ok":
            skipped_ok += 1
        elif result == "skipped-no-grade":
            skipped_no_grade += 1
        elif result == "updated":
            updated += 1
        elif result == "error":
            errors += 1

    print()
    print("=" * 60)
    print(f"Files scanned          : {total}")
    print(f"No grade field         : {skipped_no_grade}")
    print(f"Skipped (already set)  : {skipped_ok}")
    if apply:
        print(f"Updated                : {updated}")
    else:
        print(f"Would update           : {updated}  (run --apply to write)")
    print(f"Errors                 : {errors}")
    print("=" * 60)

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
