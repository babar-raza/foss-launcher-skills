#!/usr/bin/env python3
"""provenance_normalize_hash.py — Normalize content_hash in provenance blocks.

Computes the current SHA-256 body hash for each file and updates the stored
``content_hash`` in the provenance block if it differs.  Designed to be called
both from the pre-commit hook (--files-from, --auto-stage) and as a standalone
CLI tool (--all, --files, --dry-run).

This script calls ``write_provenance()`` to update only ``content_hash``,
preserving all other provenance fields including ``last_mechanism``.

Usage:
    python provenance_normalize_hash.py --all                # all English content
    python provenance_normalize_hash.py --files f1.md f2.md  # specific files
    python provenance_normalize_hash.py --files-from list.txt --auto-stage
    python provenance_normalize_hash.py --dry-run --all      # report only
    python provenance_normalize_hash.py --path content/blog.aspose.org/en/
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PIPELINE_ROOT = _HERE.parent.parent  # scripts/pipeline/commands/diagnostics/ -> scripts/pipeline/
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")  # scripts/pipeline/lib/
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from provenance import (  # noqa: E402
    compute_content_hash,
    read_provenance,
    write_provenance,
)


def normalize_file(
    filepath: Path, *, apply: bool = True, auto_stage: bool = False
) -> str:
    """Normalize content_hash for a single file.

    Returns: 'updated', 'skipped', 'no-provenance', or 'error'.
    """
    prov = read_provenance(filepath)
    if prov is None:
        return "no-provenance"

    stored = prov.get("content_hash", "")
    computed = compute_content_hash(filepath)
    if not computed:
        return "error"

    if stored == computed:
        return "skipped"

    if not apply:
        action = "absent" if not stored else "stale"
        print(f"  WOULD UPDATE ({action})  {filepath}")
        return "updated"

    prov["content_hash"] = computed
    try:
        ok = write_provenance(filepath, prov)
        if not ok:
            print(f"  ERROR writing {filepath}")
            return "error"
    except Exception as exc:
        print(f"  ERROR {filepath}: {exc}")
        return "error"

    action = "added" if not stored else "normalized"
    print(f"  {action.upper()}  {filepath}  hash={computed}")

    if auto_stage:
        subprocess.run(
            ["git", "add", str(filepath)],
            check=False,
            capture_output=True,
        )

    return "updated"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Normalize content_hash in provenance blocks."
    )
    parser.add_argument(
        "--all", dest="scan_all", action="store_true",
        help="Scan all English content directories",
    )
    parser.add_argument(
        "--path", default=None,
        help="Directory to scan",
    )
    parser.add_argument(
        "--files", nargs="*", default=None,
        help="Specific files to normalize",
    )
    parser.add_argument(
        "--files-from", dest="files_from", default=None,
        help="Read file paths from FILE (one per line), use - for stdin",
    )
    parser.add_argument(
        "--dry-run", dest="dry_run", action="store_true",
        help="Report only, do not write (default when no --apply)",
    )
    parser.add_argument(
        "--apply", action="store_true", default=False,
        help="Write changes to disk",
    )
    parser.add_argument(
        "--auto-stage", dest="auto_stage", action="store_true",
        help="git add files after updating (for pre-commit hook use)",
    )
    args = parser.parse_args(argv)

    apply = args.apply and not args.dry_run

    # Collect file list
    files: list[Path] = []
    if args.files:
        files = [Path(f) for f in args.files]
    elif args.files_from:
        if args.files_from == "-":
            lines = sys.stdin.read().splitlines()
        else:
            lines = Path(args.files_from).read_text(encoding="utf-8").splitlines()
        files = [Path(line.strip()) for line in lines if line.strip()]
    elif args.path:
        root = Path(args.path)
        files = sorted(root.rglob("*.md"))
    elif args.scan_all:
        repo_root = _HERE.parent.parent.parent.parent
        content_root = repo_root / "content"
        for site_dir in sorted(content_root.iterdir()):
            en_dir = site_dir / "en"
            if en_dir.is_dir():
                files.extend(sorted(en_dir.rglob("*.md")))
    else:
        parser.print_help()
        return 0

    mode = "APPLY" if apply else "DRY-RUN"
    print(f"provenance_normalize_hash — mode={mode}  files={len(files)}")

    updated = 0
    skipped = 0
    no_prov = 0
    errors = 0

    for filepath in files:
        result = normalize_file(
            filepath, apply=apply, auto_stage=args.auto_stage and apply
        )
        if result == "updated":
            updated += 1
        elif result == "skipped":
            skipped += 1
        elif result == "no-provenance":
            no_prov += 1
        elif result == "error":
            errors += 1

    print()
    label = "Updated" if apply else "Would update"
    print(f"{label}: {updated}  |  Skipped (ok): {skipped}  |  No provenance: {no_prov}  |  Errors: {errors}")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())