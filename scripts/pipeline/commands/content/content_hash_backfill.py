#!/usr/bin/env python3
"""content_hash_backfill.py — Idempotently write content_hash to provenance blocks.

Scans all eligible .md files under a content directory and writes a
``content_hash`` field into the provenance block for any file that has a
provenance block but is missing ``content_hash``.

Usage:
    python content_hash_backfill.py [--apply] [--path PATH]

    --dry-run  (default) Show what would be changed, no writes
    --apply    Write changes to disk
    --path     Directory to scan (default: content/)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE.parent.parent))  # scripts/pipeline/
    _LIB_DIR = str(Path(_HERE) / "lib") if isinstance(_HERE, str) else str(_HERE / "lib")
    if _LIB_DIR not in sys.path:
        sys.path.insert(0, _LIB_DIR)

from provenance import read_provenance, compute_content_hash, write_provenance  # noqa: E402


def _has_provenance_block(filepath: Path) -> bool:
    """Return True if file has a provenance block (has auto_updatable field)."""
    prov = read_provenance(filepath)
    if prov is None:
        return False
    # Eligibility check: must have auto_updatable field per task spec
    return "auto_updatable" in prov


def process_file(filepath: Path, apply: bool) -> str:
    """Process a single file.

    Returns one of: 'skipped' (already has hash), 'updated', 'error'.
    """
    try:
        prov = read_provenance(filepath)
    except Exception as exc:
        print(f"  ERROR reading {filepath}: {exc}")
        return "error"

    if prov is None:
        return "no-provenance"

    if "auto_updatable" not in prov:
        return "no-provenance"

    if "content_hash" in prov:
        return "skipped"

    # Eligible: needs content_hash
    try:
        content_hash = compute_content_hash(filepath)
    except Exception as exc:
        print(f"  ERROR computing hash for {filepath}: {exc}")
        return "error"

    if not content_hash:
        print(f"  ERROR empty hash for {filepath}")
        return "error"

    if apply:
        prov["content_hash"] = content_hash
        try:
            ok = write_provenance(filepath, prov)
            if not ok:
                print(f"  ERROR writing provenance to {filepath}")
                return "error"
        except Exception as exc:
            print(f"  ERROR writing {filepath}: {exc}")
            return "error"
        print(f"  UPDATED  {filepath}  hash={content_hash}")
    else:
        print(f"  WOULD UPDATE  {filepath}  hash={content_hash}")

    return "updated"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Idempotently backfill content_hash into provenance blocks."
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

    apply = args.apply  # False → dry-run

    # Resolve scan root
    if args.path:
        scan_root = Path(args.path).resolve()
    else:
        # Default: content/ relative to repo root (two levels up from this script)
        scan_root = (_HERE / ".." / ".." / ".." / ".." / "content").resolve()

    if not scan_root.exists():
        print(f"ERROR: scan path does not exist: {scan_root}", file=sys.stderr)
        sys.exit(1)

    mode_label = "APPLY" if apply else "DRY-RUN"
    print(f"content_hash_backfill — mode={mode_label}  root={scan_root}")
    print()

    total = 0
    skipped = 0
    updated = 0
    errors = 0
    no_provenance = 0

    for md_file in sorted(scan_root.rglob("*.md")):
        total += 1
        result = process_file(md_file, apply=apply)
        if result == "skipped":
            skipped += 1
        elif result == "updated":
            updated += 1
        elif result == "error":
            errors += 1
        elif result == "no-provenance":
            no_provenance += 1

    print()
    print("=" * 60)
    print(f"Files scanned   : {total}")
    print(f"No provenance   : {no_provenance}")
    print(f"Skipped (ok)    : {skipped}  (already had content_hash)")
    if apply:
        print(f"Updated         : {updated}")
    else:
        print(f"Would update    : {updated}  (run --apply to write)")
    print(f"Errors          : {errors}")
    print("=" * 60)

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()