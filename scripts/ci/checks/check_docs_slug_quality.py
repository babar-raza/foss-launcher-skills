#!/usr/bin/env python3
"""Docs developer-guide slug quality gate (SQ-08).

Checks docs developer-guide page filenames for known slug defect patterns:

  Check D1 — CamelCase/concatenated token leak
    Slug is a single word > 12 chars that contains no hyphens.
    Indicates a C# namespace or Java package name was not split at word
    boundaries by the site planner (e.g. "javascriptextensions",
    "logicalstructure"). These leak internal implementation naming into
    production URLs.

Usage — staged-file mode (pre-commit hook):
    python check_docs_slug_quality.py FILE [FILE ...]
    Exit 1 if any FILE is a developer-guide slug with a D1 defect; 0 otherwise.
    Files that are not developer-guide topic pages are silently skipped.

Usage — scan mode (full-repo reporting):
    python check_docs_slug_quality.py --scan [--root PATH]
    Scans all docs.aspose.org developer-guide slugs and prints findings.
    Always exits 0 in this mode (reporting only).

Exit codes:
    0  — all supplied files pass (or --scan mode)
    1  — at least one FAIL found (staged-file mode only)
    2  — configuration error (bad root in --scan mode)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Fixed-name pages that are structural, not cluster-derived topic pages.
_SKIP_STEMS: frozenset[str] = frozenset({
    "_index", "features", "installation", "license", "quickstart",
})

# Long English words that are legitimate single-word docs slugs (not leaks).
_ALLOWED_LONG_SLUGS: frozenset[str] = frozenset({
    "linearization",   # pdf/java: linearization is a single real English word (14 chars)
    "configuration",   # generic structural term (13 chars)
    "authentication",  # common auth topic (14 chars)
    "authorization",   # common auth topic (13 chars)
})

# ---------------------------------------------------------------------------
# Check logic
# ---------------------------------------------------------------------------

def check_slug(stem: str) -> tuple[str, str] | None:
    """Return (check_id, message) if the docs slug is defective, else None.

    ``stem`` is the filename without the ``.md`` extension, e.g.
    ``javascriptextensions`` or ``logical-structure``.
    Fixed structural pages (_index, features, etc.) are always skipped.
    """
    if stem in _SKIP_STEMS or stem.startswith("_"):
        return None

    # D1: single-token slug > 12 chars without hyphens → CamelCase/concat leak
    if "-" not in stem and len(stem) > 12 and stem not in _ALLOWED_LONG_SLUGS:
        return (
            "D1",
            f"slug '{stem}' is a single word > 12 chars — "
            "likely an unsplit CamelCase namespace or package name. "
            "Rename to a hyphenated form (e.g. 'javascript-extensions') "
            "and add an alias for the old URL.",
        )

    return None


# ---------------------------------------------------------------------------
# Path utilities
# ---------------------------------------------------------------------------

def _is_developer_guide_page(path: str | Path) -> bool:
    """True if the path is a docs developer-guide topic page."""
    parts = Path(path).parts
    return "developer-guide" in parts


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------

def check_files(paths: list[str]) -> int:
    """Staged-file mode: check the given file paths. Return 1 if any fail."""
    failures: list[tuple[str, str, str]] = []
    for p in paths:
        if not _is_developer_guide_page(p):
            continue
        stem = Path(p).stem
        result = check_slug(stem)
        if result is not None:
            check_id, msg = result
            failures.append((p, check_id, msg))

    if not failures:
        return 0

    for path, check_id, msg in failures:
        print(f"FAIL [{check_id}] {path}")
        print(f"       {msg}")

    print(
        f"\n{len(failures)} defective docs developer-guide slug(s). "
        "Rename the file to a hyphenated form and add an alias for the old URL."
    )
    return 1


def scan_root(docs_root: Path) -> list[tuple[Path, str, str]]:
    """Return (path, check_id, message) for all failing slugs under docs_root."""
    failures: list[tuple[Path, str, str]] = []
    for md in sorted(docs_root.rglob("*.md")):
        if not _is_developer_guide_page(md):
            continue
        stem = md.stem
        result = check_slug(stem)
        if result is not None:
            check_id, msg = result
            failures.append((md, check_id, msg))
    return failures


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "files",
        nargs="*",
        metavar="FILE",
        help="Files to check (staged-file mode). Pass no files to run --scan.",
    )
    p.add_argument(
        "--scan",
        action="store_true",
        help="Full-repo scan mode (report only, always exits 0).",
    )
    p.add_argument(
        "--root",
        default="content",
        help="Content root directory used in --scan mode (default: content).",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.scan or not args.files:
        root = Path(args.root)
        docs_root = root / "docs.aspose.org"
        if not docs_root.exists():
            print(f"ERROR: docs root not found: {docs_root}", file=sys.stderr)
            return 2
        failures = scan_root(docs_root)
        if failures:
            print(f"Docs slug quality scan — {len(failures)} finding(s):")
            for path, check_id, msg in failures:
                print(f"  [{check_id}] {path.relative_to(root)}")
                print(f"         {msg}")
        else:
            print("Docs slug quality scan — 0 findings. All clear.")
        return 0

    return check_files(args.files)


if __name__ == "__main__":
    sys.exit(main())
