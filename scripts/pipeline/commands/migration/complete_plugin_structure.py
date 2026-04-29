#!/usr/bin/env python3
"""complete_plugin_structure.py — Deterministic structural completion for plugin pages.

Inserts missing boilerplate display-control sections into layout: plugin product
pages without touching LLM-generated content sections.  Uses text-level surgery
(no full YAML round-trip) to preserve scalar styles.

Usage:
    python scripts/pipeline/complete_plugin_structure.py --files path/to/file.md
    python scripts/pipeline/complete_plugin_structure.py --dry-run --files path/to/file.md

Idempotent: running twice produces identical output.
"""
from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path

import yaml

_PIPELINE_ROOT = Path(__file__).resolve().parent.parent.parent  # commands/{domain}/ -> commands/ -> pipeline/
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from core.fs import atomic_write  # noqa: E402
from core.markdown import split_frontmatter, parse_frontmatter  # noqa: E402

# Boilerplate sections that must be present on every English plugin page.
# These are display-control toggles read by the Hugo plugin.html template.
# Order matters: they are inserted in this order before the provenance block.
_BOILERPLATE_SECTIONS = [
    ("supportandlearning", "  enable: true"),
    ("more_formats", "  enable: true"),
    ("back_to_top", "  enable: true"),
]

# Insertion anchor: boilerplate sections are inserted immediately before the
# provenance: or evidence: block (whichever comes first), or appended at the
# end of frontmatter if neither exists.
_ANCHOR_KEYS = ("provenance:", "evidence:", "grade:")


def complete_file(filepath: Path, dry_run: bool = False) -> bool:
    """Insert missing boilerplate sections. Returns True if file was modified."""
    text = filepath.read_text(encoding="utf-8")
    parts = split_frontmatter(text)
    if parts is None:
        return False

    open_fence, fm_text, close_fence = parts
    body = text[len(open_fence) + len(fm_text) + len(close_fence):]

    # Only process layout: plugin pages
    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError:
        return False

    if fm.get("layout") != "plugin":
        return False

    # Determine which sections are missing
    missing = []
    for key, value in _BOILERPLATE_SECTIONS:
        if key not in fm:
            missing.append((key, value))

    if not missing:
        return False  # Nothing to do — idempotent

    # Build the insertion block
    lines_to_insert = []
    for key, value in missing:
        lines_to_insert.append(f"{key}:")
        lines_to_insert.append(value)
    insert_block = "\n".join(lines_to_insert)

    # Find the insertion point: just before provenance/evidence/grade
    fm_lines = fm_text.split("\n")
    insert_idx = None
    for i, line in enumerate(fm_lines):
        for anchor in _ANCHOR_KEYS:
            if line.startswith(anchor):
                insert_idx = i
                break
        if insert_idx is not None:
            break

    if insert_idx is not None:
        fm_lines.insert(insert_idx, insert_block)
    else:
        # Append at end of frontmatter
        fm_lines.append(insert_block)

    new_fm = "\n".join(fm_lines)
    new_text = f"{open_fence}{new_fm}{close_fence}{body}"

    if dry_run:
        rel = filepath.name
        for key, _ in missing:
            print(f"  WOULD ADD  {rel}: {key}")
        return True

    atomic_write(filepath, new_text)
    rel = filepath.name
    for key, _ in missing:
        print(f"  ADDED  {rel}: {key}")
    return True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=textwrap.dedent(__doc__ or ""),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--files", nargs="+", required=True, help="Files to complete")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no writes")
    args = parser.parse_args(argv)

    modified = 0
    for p in args.files:
        path = Path(p)
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.exists():
            print(f"  SKIP  {p}: file not found")
            continue
        if complete_file(path, dry_run=args.dry_run):
            modified += 1

    mode = "dry-run" if args.dry_run else "applied"
    print(f"\ncomplete_plugin_structure — {mode}: {modified} file(s) modified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
