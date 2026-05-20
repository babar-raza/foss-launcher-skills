# Adapted from aspose.org
#!/usr/bin/env python3
"""apply_origin_decisions.py — KR-6: Apply human review decisions from decisions CSV.

Reads reports/content_origin_review_queue_class2.csv (with reviewer_decision filled in)
and writes content_origin to each file based on the reviewer's classification.

Allowed reviewer_decision values:
  skill-generated-confirmed  → writes content_origin: skill-generated
  human-authored-confirmed   → writes content_origin: human-authored
  mixed-modified             → writes content_origin: agent-drafted + auto_updatable: false
  deferred                   → no change (file remains content_origin: unknown)
  (blank)                    → BLOCKED — all decisions must be filled before apply

Safety guards:
  - Refuses to run if any reviewer_decision is blank
  - Refuses to change content_origin on a file that is not currently 'unknown'
  - Writes provenance fields only — never touches content body
  - Idempotent: running twice produces the same result

Usage:
    python scripts/pipeline/commands/migration/apply_origin_decisions.py [--dry-run] [--csv PATH]

    --dry-run   Print what would change without writing
    --csv       Path to decisions CSV (default: reports/content_origin_review_queue_class2.csv)
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE.parent.parent))  # scripts/pipeline/  # scripts/pipeline/
    _LIB_DIR = str(Path(_HERE) / "lib") if isinstance(_HERE, str) else str(_HERE / "lib")
    if _LIB_DIR not in sys.path:
        sys.path.insert(0, _LIB_DIR)

from lib.provenance import read_provenance, write_provenance  # noqa: E402

_DEFAULT_REPO_ROOT = (_HERE / ".." / ".." / ".." / "..").resolve()
_REPO_ROOT = _DEFAULT_REPO_ROOT
_DEFAULT_CSV = _REPO_ROOT / "reports" / "content_origin_review_queue_class2.csv"


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing."""
    global _REPO_ROOT
    _REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT

_ALLOWED_DECISIONS = frozenset({
    "skill-generated-confirmed",
    "human-authored-confirmed",
    "mixed-modified",
    "deferred",
})

_DECISION_TO_ORIGIN = {
    "skill-generated-confirmed": "skill-generated",
    "human-authored-confirmed": "human-authored",
    "mixed-modified": "agent-drafted",
}


def run(csv_path: Path, dry_run: bool) -> dict:
    if not csv_path.exists():
        print(f"ERROR: CSV not found: {csv_path}", file=sys.stderr)
        sys.exit(1)

    with open(csv_path, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    if not rows:
        print("ERROR: CSV is empty.", file=sys.stderr)
        sys.exit(1)

    # Guard: all reviewer_decision must be filled
    blank = [r["filepath"] for r in rows if not r.get("reviewer_decision", "").strip()]
    if blank:
        print(
            f"BLOCKED: {len(blank)} rows have blank reviewer_decision. "
            "Fill all decisions before running --apply.",
            file=sys.stderr,
        )
        for fp in blank[:10]:
            print(f"  {fp}", file=sys.stderr)
        if len(blank) > 10:
            print(f"  ... and {len(blank) - 10} more", file=sys.stderr)
        sys.exit(1)

    # Guard: all decisions must be in allowed set
    invalid = [
        (r["filepath"], r["reviewer_decision"])
        for r in rows
        if r.get("reviewer_decision", "") not in _ALLOWED_DECISIONS
    ]
    if invalid:
        print(f"BLOCKED: {len(invalid)} rows have invalid reviewer_decision values:", file=sys.stderr)
        for fp, dec in invalid[:10]:
            print(f"  {fp}: '{dec}'", file=sys.stderr)
        sys.exit(1)

    print(f"Apply origin decisions: {'DRY RUN' if dry_run else 'LIVE'}")
    print(f"Total rows: {len(rows)}\n")

    updated = 0
    skipped_deferred = 0
    skipped_already = 0
    skipped_missing = 0
    errors = 0

    for row in rows:
        decision = row["reviewer_decision"].strip()
        filepath = _REPO_ROOT / row["filepath"]

        if decision == "deferred":
            skipped_deferred += 1
            continue

        if not filepath.exists():
            print(f"  MISSING   {row['filepath']}")
            skipped_missing += 1
            continue

        prov = read_provenance(filepath)
        if prov is None:
            print(f"  NO_PROV   {row['filepath']}")
            errors += 1
            continue

        current_origin = prov.get("content_origin", "")
        if current_origin != "unknown":
            # Already recovered by another path (e.g. content_origin_recover) — skip
            skipped_already += 1
            continue

        new_origin = _DECISION_TO_ORIGIN[decision]

        if dry_run:
            note = " + auto_updatable: false" if decision == "mixed-modified" else ""
            print(f"  WOULD SET  {row['filepath']}")
            print(f"             {current_origin} -> {new_origin}{note}")
            updated += 1
            continue

        prov["content_origin"] = new_origin
        if decision == "mixed-modified":
            prov["auto_updatable"] = False

        ok = write_provenance(filepath, prov)
        if ok:
            note = " + auto_updatable: false" if decision == "mixed-modified" else ""
            print(f"  SET  {row['filepath']}  -> {new_origin}{note}")
            updated += 1
        else:
            print(f"  ERROR  {row['filepath']}")
            errors += 1

    print(f"\nResults:")
    print(f"  {'Would set' if dry_run else 'Set'}    : {updated}")
    print(f"  Deferred        : {skipped_deferred}")
    print(f"  Already set     : {skipped_already}")
    print(f"  Missing files   : {skipped_missing}")
    print(f"  Errors          : {errors}")

    return {
        "updated": updated,
        "deferred": skipped_deferred,
        "already_set": skipped_already,
        "missing": skipped_missing,
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="KR-6: Apply human review decisions to content_origin"
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    parser.add_argument(
        "--csv",
        default=str(_DEFAULT_CSV),
        help=f"Decisions CSV (default: {_DEFAULT_CSV})",
    )
    args = parser.parse_args()

    stats = run(csv_path=Path(args.csv), dry_run=args.dry_run)
    if stats["errors"]:
        sys.exit(1)


if __name__ == "__main__":
    main()