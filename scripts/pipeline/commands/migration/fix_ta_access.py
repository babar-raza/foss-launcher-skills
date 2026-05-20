# Adapted from aspose.org
"""Fix type-accuracy Access column defects in reference pages.

For each reference page where api_surface.json marks a property as
writable (has a setter), but the Properties table shows "Read" in the
Access column, this script changes "Read" to "Read/Write".

Usage
-----
  # Dry-run (no file writes):
  python fix_ta_access.py --family cells --platform python --dry-run

  # Apply:
  python fix_ta_access.py --family cells --platform python

  # Target specific files:
  python fix_ta_access.py --family cells --platform python \
      --files content/reference/en/cells/python/AutoFilter.md

Exit codes
----------
  0  Success (or dry-run complete)
  1  Error (bad args, missing knowledge, etc.)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Pattern: property table row — | `PropName` | type | Read | description |
# Captures the full match plus named groups for prop and the access cell.
# We match only rows whose access cell is exactly "Read" (case-sensitive).
# ---------------------------------------------------------------------------
_PROP_ROW_RE = re.compile(
    r"(\|\s*`(?P<prop>[^`]+)`\s*\|[^|]*\|)\s*(?P<access>Read)\s*(\|)",
    re.MULTILINE,
)

KNOWLEDGE_ROOT = Path("knowledge")
REFERENCE_ROOT = Path(os.environ.get("REFERENCE_ROOT", "content/reference/en"))


def _load_writable_map(family: str, platform: str) -> dict[str, set[str]]:
    """Return {class_name: {prop_name, ...}} for all writable properties."""
    api_path = KNOWLEDGE_ROOT / family / platform / "merged" / "api_surface.json"
    if not api_path.exists():
        raise FileNotFoundError(f"api_surface.json not found: {api_path}")
    surface = json.loads(api_path.read_text(encoding="utf-8"))
    result: dict[str, set[str]] = {}
    for entry in surface:
        cls = entry.get("name", "")
        if not cls:
            continue
        writable_props = {
            p["name"]
            for p in entry.get("properties", [])
            if p.get("writable") is True and p.get("name")
        }
        if writable_props:
            result[cls] = writable_props
    return result


def _fix_file(
    filepath: Path,
    writable_map: dict[str, set[str]],
    dry_run: bool,
) -> list[str]:
    """Fix Access column in one file. Returns list of changed property names."""
    class_name = filepath.stem
    writable_props = writable_map.get(class_name)
    if not writable_props:
        return []

    raw = filepath.read_text(encoding="utf-8", errors="replace")
    changed: list[str] = []

    def _replace(m: re.Match) -> str:  # type: ignore[type-arg]
        prop = m.group("prop")
        if prop not in writable_props:
            return m.group(0)  # not writable → leave unchanged
        # Replace the Access cell value "Read" with "Read/Write"
        changed.append(prop)
        prefix = m.group(1)
        suffix = m.group(4)
        return f"{prefix} Read/Write {suffix}"

    new_raw = _PROP_ROW_RE.sub(_replace, raw)

    if changed and not dry_run:
        filepath.write_text(new_raw, encoding="utf-8")

    return changed


def _collect_files(family: str, platform: str, files: list[str] | None) -> list[Path]:
    if files:
        return [Path(f) for f in files]
    ref_dir = REFERENCE_ROOT / family / platform
    if not ref_dir.exists():
        raise FileNotFoundError(f"Reference directory not found: {ref_dir}")
    return sorted(ref_dir.glob("*.md"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fix type_accuracy Access column defects in reference pages."
    )
    parser.add_argument("--family", required=True, help="Product family, e.g. cells")
    parser.add_argument("--platform", required=True, help="Platform, e.g. python")
    parser.add_argument(
        "--files",
        nargs="+",
        metavar="FILE",
        help="Explicit file list; defaults to all *.md in the reference dir",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would change without writing files",
    )
    args = parser.parse_args(argv)

    try:
        writable_map = _load_writable_map(args.family, args.platform)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    try:
        target_files = _collect_files(args.family, args.platform, args.files)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    total_props = 0
    total_files = 0

    for filepath in target_files:
        changed = _fix_file(filepath, writable_map, dry_run=args.dry_run)
        if changed:
            total_files += 1
            total_props += len(changed)
            prefix = "[DRY-RUN] " if args.dry_run else ""
            print(f"{prefix}{filepath}: {len(changed)} propert{'y' if len(changed)==1 else 'ies'} -> Read/Write")
            for prop in changed:
                print(f"    {prop}")

    if total_files == 0:
        print("No Access column changes needed.")
    else:
        mode = "Would fix" if args.dry_run else "Fixed"
        print(
            f"\n{mode} {total_props} propert{'y' if total_props==1 else 'ies'} "
            f"across {total_files} file{'s' if total_files!=1 else ''}."
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
