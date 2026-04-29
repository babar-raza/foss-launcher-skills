#!/usr/bin/env python3
"""audit_content_hash.py — Report files where stored content_hash != computed hash.

Read-only audit: scans English content files and reports mismatches between
the stored ``content_hash`` in the provenance block and the actual SHA-256
of the page body.

Usage:
    python audit_content_hash.py                      # scan all English content
    python audit_content_hash.py --path content/blog.aspose.org/
    python audit_content_hash.py --files file1.md file2.md
    python audit_content_hash.py --json               # JSON output
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE.parent.parent))  # scripts/pipeline/
    _LIB_DIR = str(Path(_HERE) / "lib") if isinstance(_HERE, str) else str(_HERE / "lib")
    if _LIB_DIR not in sys.path:
        sys.path.insert(0, _LIB_DIR)

from provenance import read_provenance, compute_content_hash  # noqa: E402


def audit_file(filepath: Path) -> dict | None:
    """Check a single file. Returns a mismatch dict or None if OK/skipped."""
    prov = read_provenance(filepath)
    if prov is None:
        return None
    stored = prov.get("content_hash", "")
    if not stored:
        return None  # no hash to compare — not a mismatch, just absent
    computed = compute_content_hash(filepath)
    if not computed:
        return None
    if stored != computed:
        return {
            "path": str(filepath),
            "stored": stored,
            "computed": computed,
        }
    return None


def scan_directory(root: Path) -> list[dict]:
    """Scan all .md files under root for stale hashes."""
    mismatches = []
    for md_file in sorted(root.rglob("*.md")):
        result = audit_file(md_file)
        if result:
            mismatches.append(result)
    return mismatches


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Report files where stored content_hash != computed hash."
    )
    parser.add_argument(
        "--path", default=None,
        help="Directory to scan (default: content/*/en/)",
    )
    parser.add_argument(
        "--files", nargs="*", default=None,
        help="Specific files to check",
    )
    parser.add_argument(
        "--json", dest="json_output", action="store_true",
        help="Output results as JSON",
    )
    args = parser.parse_args(argv)

    mismatches: list[dict] = []

    if args.files:
        for f in args.files:
            result = audit_file(Path(f))
            if result:
                mismatches.append(result)
    elif args.path:
        mismatches = scan_directory(Path(args.path))
    else:
        # Default: scan all English content directories
        repo_root = _HERE.parent.parent.parent.parent
        content_root = repo_root / "content"
        for site_dir in sorted(content_root.iterdir()):
            en_dir = site_dir / "en"
            if en_dir.is_dir():
                mismatches.extend(scan_directory(en_dir))

    if args.json_output:
        print(json.dumps(mismatches, indent=2))
    else:
        if mismatches:
            print(f"STALE: {len(mismatches)} file(s) with mismatched content_hash:")
            for m in mismatches:
                print(f"  {m['path']}")
                print(f"    stored:   {m['stored']}")
                print(f"    computed: {m['computed']}")
        else:
            print("OK: all content_hash values match computed hashes.")

    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(main())