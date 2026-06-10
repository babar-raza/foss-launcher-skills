#!/usr/bin/env python3
"""Deterministically complete layout: plugin product-page boilerplate."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.pipeline.core.fs import atomic_write  # noqa: E402

_FRONTMATTER_RE = re.compile(r"^(---\s*\n)(.*?)(\n---\s*(?:\n|$))", re.DOTALL)
_BOILERPLATE_SECTIONS = [
    ("supportandlearning", "  enable: true"),
    ("more_formats", "  enable: true"),
    ("back_to_top", "  enable: true"),
]
_ANCHOR_KEYS = ("provenance:", "evidence:", "grade:")


def _split_frontmatter(text: str) -> tuple[str, str, str, str] | None:
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return None
    return match.group(1), match.group(2), match.group(3), text[match.end():]


def complete_file(filepath: Path, dry_run: bool = False) -> bool:
    text = filepath.read_text(encoding="utf-8")
    parts = _split_frontmatter(text)
    if parts is None:
        return False
    open_fence, fm_text, close_fence, body = parts

    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError:
        return False
    if fm.get("layout") != "plugin":
        return False

    missing = [(key, value) for key, value in _BOILERPLATE_SECTIONS if key not in fm]
    if not missing:
        return False

    insert_block = "\n".join(line for key, value in missing for line in (f"{key}:", value))
    fm_lines = fm_text.split("\n")
    insert_at = None
    for index, line in enumerate(fm_lines):
        if any(line.startswith(anchor) for anchor in _ANCHOR_KEYS):
            insert_at = index
            break
    if insert_at is None:
        fm_lines.append(insert_block)
    else:
        fm_lines.insert(insert_at, insert_block)

    if dry_run:
        for key, _ in missing:
            print(f"  WOULD ADD  {filepath.name}: {key}")
        return True

    newline = chr(10)
    joined_fm = newline.join(fm_lines)
    atomic_write(filepath, f"{open_fence}{joined_fm}{close_fence}{body}")
    for key, _ in missing:
        print(f"  ADDED  {filepath.name}: {key}")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files", nargs="+", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    modified = 0
    for raw in args.files:
        path = Path(raw)
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.exists():
            print(f"  SKIP  {raw}: file not found")
            continue
        if complete_file(path, dry_run=args.dry_run):
            modified += 1
    mode = "dry-run" if args.dry_run else "applied"
    print(f"\ncomplete_plugin_structure - {mode}: {modified} file(s) modified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
