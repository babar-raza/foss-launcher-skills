# Adapted from aspose.org
#!/usr/bin/env python3
"""cleanup_reviewed_field.py — Remove deprecated 'reviewed' field from provenance blocks.

TC-5 removed the write path for 'reviewed:' from provenance_backfill.py, but
28,077 files still carry the legacy 'reviewed: false' value in their provenance
block. This script removes the field to eliminate data noise.

Usage:
    python scripts/pipeline/commands/migration/cleanup_reviewed_field.py [--apply] [--site SITE]

    --apply     Actually write changes (default: dry-run)
    --site      Limit to one site (e.g. blog)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE.parent.parent))  # scripts/pipeline/  # scripts/pipeline/
    _LIB_DIR = str(Path(_HERE) / "lib") if isinstance(_HERE, str) else str(_HERE / "lib")
    if _LIB_DIR not in sys.path:
        sys.path.insert(0, _LIB_DIR)

from lib.provenance import read_provenance, write_provenance  # noqa: E402

_REPO_ROOT = (_HERE / ".." / ".." / ".." / "..").resolve()
_CONTENT_ROOT = _REPO_ROOT / "content"


def run(site: str | None, apply: bool) -> dict:
    scan_root = _CONTENT_ROOT / site if site else _CONTENT_ROOT
    removed = 0
    skipped = 0
    errors = 0

    for md_file in sorted(scan_root.rglob("*.md")):
        prov = read_provenance(md_file)
        if prov is None:
            continue
        if "reviewed" not in prov:
            continue

        # Field present — remove it
        new_prov = {k: v for k, v in prov.items() if k != "reviewed"}

        if not apply:
            print(f"  WOULD REMOVE  {md_file.relative_to(_REPO_ROOT)}")
            removed += 1
            continue

        ok = write_provenance(md_file, new_prov)
        if ok:
            removed += 1
        else:
            print(f"  ERROR  {md_file.relative_to(_REPO_ROOT)}", file=sys.stderr)
            errors += 1

    print(f"\nResults ({'DRY RUN' if not apply else 'LIVE'}):")
    print(f"  {'Would remove' if not apply else 'Removed'}: {removed}")
    print(f"  Skipped (no field): (everything else)")
    print(f"  Errors: {errors}")

    return {"removed": removed, "skipped": skipped, "errors": errors}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Remove deprecated 'reviewed' field from provenance blocks"
    )
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry-run)")
    parser.add_argument("--site", help="Limit to one site directory (e.g. blog)")
    args = parser.parse_args()

    stats = run(site=args.site, apply=args.apply)
    if stats["errors"]:
        sys.exit(1)


if __name__ == "__main__":
    main()