#!/usr/bin/env python3
# Adapted from aspose.org scripts/ci/checks/ for standalone use
"""
check_content_filenames.py — Content filename convention validator.

Walks a configurable content root and reports files that violate slug/filename
conventions.  Two rule tiers apply based on directory tree:

  Prose trees (docs, kb, blog, products):
    - Extension must be lowercase .md  (.MD / .Md / .mD → FAIL)
    - Allowed stems:
        _index
        index
        index.<locale>          locale = [a-z]{2}(-[a-z]{2,4})?
        <slug>                  [a-z0-9]+(-[a-z0-9]+)*
        <slug>.<locale>
    - Uppercase stems, invalid locale suffixes → FAIL

  Reference tree (content/reference.aspose.org/):
    - Extension must be lowercase .md
    - PascalCase class-name stems allowed
    - Structural violations still rejected (leading hyphen, etc.)

Structural rejections (apply to ALL trees including reference):
    - Stem starts with hyphen
    - Stem ends with hyphen
    - Stem contains '--'
    - Filename contains space
    - Filename contains '..'
    - Extension is .MD / .Md / .mD (uppercase markdown)
    - Empty stem

CLI:
    check_content_filenames.py [--root PATH] [--report-only | --strict]
    --root         Content root directory (default: content)
    --report-only  Print violations but exit 0
    --strict       Exit 1 if any violations found (default behaviour)

Exit codes:
    0  no violations found (or --report-only)
    1  violations found (--strict mode)
    2  configuration error (bad root path)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_SLUG_RE = re.compile(r'^[a-z0-9]+(-[a-z0-9]+)*$')
_LOCALE_RE = re.compile(r'^[a-z]{2}(-[a-z]{2,4})?$')

# Top-level subdirectories of content/ that are internal tooling, not publishable pages.
# Filename slug conventions do not apply to these directories.
_INTERNAL_CONTENT_DIRS: frozenset[str] = frozenset({'templates'})


def _is_reference_tree(path: Path, content_root: Path) -> bool:
    """Return True if *path* is under content/reference.aspose.org/."""
    try:
        rel = path.relative_to(content_root)
    except ValueError:
        return False
    return bool(rel.parts) and rel.parts[0].startswith(os.environ.get('REFERENCE_DIR_PREFIX', 'reference.'))


def is_valid_filename(path: Path, content_root: Path) -> tuple[bool, str]:
    """Validate a single file path against content filename conventions.

    Returns ``(valid, reason)`` where *reason* is an empty string when valid.
    The full *path* must be provided so that tree-membership rules can be applied.
    """
    name = path.name
    suffix = path.suffix

    # ------------------------------------------------------------------
    # Extension check: must be exactly lowercase .md
    # ------------------------------------------------------------------
    if suffix.lower() == '.md' and suffix != '.md':
        return False, f"uppercase markdown extension '{suffix}'"

    if suffix.lower() != '.md':
        # Not a markdown file — caller should pre-filter; skip silently
        return True, ''

    stem = path.stem  # filename without the final extension

    # ------------------------------------------------------------------
    # Structural rejections — apply to ALL trees including reference
    # ------------------------------------------------------------------
    if not stem:
        return False, "empty stem"

    if ' ' in name:
        return False, "filename contains space"

    if name.startswith(' ') or name.endswith(' '):
        return False, "filename has leading or trailing whitespace"

    if '..' in name:
        return False, "filename contains '..'"

    if stem.startswith('-'):
        return False, "stem starts with hyphen"

    if stem.endswith('-'):
        return False, "stem ends with hyphen"

    if '--' in stem:
        return False, "stem contains doubled hyphen '--'"

    # ------------------------------------------------------------------
    # Reference tree: structural rules only; PascalCase class names OK
    # ------------------------------------------------------------------
    if _is_reference_tree(path, content_root):
        return True, ''

    # ------------------------------------------------------------------
    # Prose tree rules
    # ------------------------------------------------------------------
    # A stem may have at most one embedded dot (locale suffix).
    # Split on the FIRST dot to separate base slug from optional locale.
    parts = stem.split('.', 1)
    base = parts[0]
    locale_part = parts[1] if len(parts) > 1 else None

    # Validate locale suffix when present
    if locale_part is not None:
        if not _LOCALE_RE.match(locale_part):
            return False, (
                f"invalid or uppercase locale suffix '.{locale_part}' "
                f"(expected [a-z]{{2}}(-[a-z]{{2,4}})?)"
            )

    # Special allowed bases
    if base in ('_index', 'index'):
        return True, ''

    # Must be a valid lowercase hyphen-separated slug
    if not _SLUG_RE.match(base):
        return False, (
            f"stem '{base}' is not a valid lowercase slug — "
            f"must match [a-z0-9]+(-[a-z0-9]+)* "
            f"(no uppercase, no leading/trailing hyphen)"
        )

    return True, ''


def _find_markdown_files(root: Path):
    """Yield all files whose extension is .md case-insensitively.

    Skips top-level subdirectories of *root* that are internal tooling
    (e.g. ``content/templates/``) and not publishable page trees.
    """
    for path in sorted(root.rglob('*')):
        if not path.is_file() or path.suffix.lower() != '.md':
            continue
        try:
            rel_parts = path.relative_to(root).parts
        except ValueError:
            rel_parts = ()
        if rel_parts and rel_parts[0] in _INTERNAL_CONTENT_DIRS:
            continue
        yield path


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Validate content filename conventions.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        '--root', default='content',
        help='Content root directory (default: content)',
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        '--report-only', action='store_true',
        help='Print violations but exit 0 regardless',
    )
    mode.add_argument(
        '--strict', action='store_true',
        help='Exit 1 if any violations found (this is the default)',
    )
    args = parser.parse_args(argv)

    # Default to strict when neither flag is given
    report_only = args.report_only

    root = Path(args.root)
    if not root.is_dir():
        print(
            f"ERROR: content root '{root}' is not a directory or does not exist",
            file=sys.stderr,
        )
        return 2

    violations: list[tuple[str, str]] = []

    for path in _find_markdown_files(root):
        valid, reason = is_valid_filename(path, root)
        if not valid:
            try:
                rel = str(path.relative_to(Path('.'))).replace('\\', '/')
            except ValueError:
                rel = str(path).replace('\\', '/')
            violations.append((rel, reason))

    for rel_path, reason in violations:
        print(f"VIOLATION: {rel_path} — {reason}")

    if violations:
        print(
            f"\n{len(violations)} filename violation(s) found.",
            file=sys.stderr,
        )
        return 0 if report_only else 1

    print("OK: 0 filename violations.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
