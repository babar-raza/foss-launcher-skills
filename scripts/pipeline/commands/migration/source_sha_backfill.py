# Adapted from aspose.org
#!/usr/bin/env python3
"""source_sha_backfill.py — Recompute source_sha to 24 hex chars for locale files.

Previously compute_source_sha() returned hexdigest()[:12]; it was updated to
return hexdigest()[:24] (TM-06).  Existing locale files still have the old
12-char value, which causes is_stale() to always return True via direct string
comparison.  This script recomputes source_sha for any locale file whose stored
value is shorter than 24 chars.

Eligibility criteria for a file to be processed:
  - Has a provenance block (auto_updatable present)
  - Has source_file in provenance
  - Has source_sha in provenance
  - len(source_sha) < 24

Usage:
    python source_sha_backfill.py [--apply] [--path PATH]

    --dry-run  (default) Show what would be changed, no writes
    --apply    Write changes to disk
    --path     Directory to scan (default: content/ relative to repo root)
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

from lib.provenance import read_provenance, compute_source_sha, write_provenance  # noqa: E402


def process_file(filepath: Path, repo_root: Path, apply: bool) -> str:
    """Process a single file.

    Returns one of: 'skipped-no-prov', 'skipped-no-source-file',
    'skipped-no-sha', 'skipped-ok', 'skipped-missing-source',
    'updated', 'error'.
    """
    try:
        prov = read_provenance(filepath)
    except Exception as exc:
        print(f"  ERROR reading {filepath}: {exc}")
        return "error"

    if prov is None or "auto_updatable" not in prov:
        return "skipped-no-prov"

    source_file = prov.get("source_file")
    if not source_file:
        return "skipped-no-source-file"

    current_sha = prov.get("source_sha")
    if not current_sha:
        return "skipped-no-sha"

    # Already correct length — skip
    if len(str(current_sha)) >= 24:
        return "skipped-ok"

    # source_file is relative to content/ directory
    content_root = repo_root / "content"
    source_path = (content_root / source_file).resolve()
    if not source_path.exists():
        print(f"  WARN     {filepath}: source not found: {source_path}")
        return "skipped-missing-source"

    try:
        new_sha = compute_source_sha(source_path)
    except Exception as exc:
        print(f"  ERROR computing sha for {filepath}: {exc}")
        return "error"

    if apply:
        prov["source_sha"] = new_sha
        try:
            ok = write_provenance(filepath, prov)
            if not ok:
                print(f"  ERROR writing provenance to {filepath}")
                return "error"
        except Exception as exc:
            print(f"  ERROR writing {filepath}: {exc}")
            return "error"
        print(f"  UPDATED  {filepath}  {current_sha} -> {new_sha}")
    else:
        print(f"  WOULD UPDATE  {filepath}  {current_sha} -> {new_sha}")

    return "updated"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Recompute source_sha to 24 hex chars for locale files."
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

    # Repo root is two levels up from this script (scripts/pipeline/)
    repo_root = (_HERE / ".." / ".." / ".." / "..").resolve()

    if args.path:
        scan_root = Path(args.path).resolve()
    else:
        scan_root = (repo_root / "content").resolve()

    if not scan_root.exists():
        print(f"ERROR: scan path does not exist: {scan_root}", file=sys.stderr)
        sys.exit(1)

    mode_label = "APPLY" if apply else "DRY-RUN"
    print(f"source_sha_backfill — mode={mode_label}  root={scan_root}")
    print()

    total = 0
    skipped_ok = 0
    skipped_no_prov = 0
    skipped_no_source = 0
    skipped_missing = 0
    updated = 0
    errors = 0

    for md_file in sorted(scan_root.rglob("*.md")):
        total += 1
        result = process_file(md_file, repo_root=repo_root, apply=apply)
        if result == "skipped-ok":
            skipped_ok += 1
        elif result in ("skipped-no-prov", "skipped-no-source-file", "skipped-no-sha"):
            skipped_no_prov += 1
        elif result == "skipped-missing-source":
            skipped_missing += 1
        elif result == "updated":
            updated += 1
        elif result == "error":
            errors += 1

    print()
    print("=" * 60)
    print(f"Files scanned         : {total}")
    print(f"No provenance/source  : {skipped_no_prov}")
    print(f"Skipped (already 24+) : {skipped_ok}")
    print(f"Skipped (source miss) : {skipped_missing}")
    if apply:
        print(f"Updated               : {updated}")
    else:
        print(f"Would update          : {updated}  (run --apply to write)")
    print(f"Errors                : {errors}")
    print("=" * 60)

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()