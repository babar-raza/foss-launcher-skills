#!/usr/bin/env python3
"""structural_lock.py — KR-2: write-lock Class 3 structural pages.

Sets auto_updatable: false and adds provenance_recovery_note: structural-page
on all Class 3 files (no grade, no evidence, structural navigation pages).
Does NOT change content_origin — leaves it as unknown.

Usage:
    python scripts/pipeline/commands/governance/structural_lock.py [--dry-run] [--csv PATH]

    --dry-run   Print what would change without writing
    --csv       Path to review queue CSV (default: reports/content_origin_review_queue.csv)
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parents[2]  # commands/governance/ -> commands/ -> pipeline/
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
_LIB_DIR = str(Path(_HERE) / "lib") if isinstance(_HERE, str) else str(_HERE / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from provenance import read_provenance, write_provenance  # noqa: E402

_DEFAULT_REPO_ROOT = (_HERE / ".." / ".." / ".." / "..").resolve()  # commands/governance/ -> commands/ -> pipeline/ -> scripts/ -> repo
_REPO_ROOT = _DEFAULT_REPO_ROOT
_DEFAULT_CSV = _REPO_ROOT / "reports" / "content_origin_review_queue.csv"


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing."""
    global _REPO_ROOT
    _REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT


def run(csv_path: Path, dry_run: bool) -> dict:
    if not csv_path.exists():
        print(f"ERROR: CSV not found: {csv_path}", file=sys.stderr)
        sys.exit(1)

    with open(csv_path, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    class3 = [r for r in rows if r.get("assigned_class") == "3"]
    print(f"Structural lock: {'DRY RUN' if dry_run else 'LIVE'}")
    print(f"Class 3 files to process: {len(class3)}\n")

    updated = 0
    skipped = 0
    errors = 0

    for row in class3:
        filepath = _REPO_ROOT / row["filepath"]
        if not filepath.exists():
            print(f"  MISSING  {row['filepath']}")
            errors += 1
            continue

        prov = read_provenance(filepath)
        if prov is None:
            print(f"  NO_PROV  {row['filepath']}")
            errors += 1
            continue

        already_locked = (
            prov.get("auto_updatable") is False
            and prov.get("provenance_recovery_note") == "structural-page"
        )
        if already_locked:
            skipped += 1
            continue

        if dry_run:
            print(f"  WOULD LOCK  {row['filepath']}")
            updated += 1
            continue

        prov["auto_updatable"] = False
        prov["provenance_recovery_note"] = "structural-page"
        # Explicitly preserve content_origin: unknown — do not change it
        prov.setdefault("content_origin", "unknown")

        ok = write_provenance(filepath, prov)
        if ok:
            print(f"  LOCKED  {row['filepath']}")
            updated += 1
        else:
            print(f"  ERROR   {row['filepath']}")
            errors += 1

    print(f"\nResults:")
    print(f"  {'Would lock' if dry_run else 'Locked'}  : {updated}")
    print(f"  Already locked : {skipped}")
    print(f"  Errors         : {errors}")

    return {"updated": updated, "skipped": skipped, "errors": errors}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="KR-2: Write-lock Class 3 structural pages"
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    parser.add_argument(
        "--csv",
        default=str(_DEFAULT_CSV),
        help=f"Review queue CSV (default: {_DEFAULT_CSV})",
    )
    args = parser.parse_args()

    stats = run(csv_path=Path(args.csv), dry_run=args.dry_run)
    if stats["errors"]:
        sys.exit(1)


if __name__ == "__main__":
    main()