#!/usr/bin/env python3
"""backlink_validate_migration.py — Validate evidence bundle against manifest.

Part of the BL-DEEP-EXEC sprint evidence chain (V26).
"""
from __future__ import annotations

import argparse
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path


def validate_bundle(bundle_path: Path, manifest_path: Path, output_path: Path, dry_run: bool = False) -> bool:
    """Validate that all manifest required_entries are present in the ZIP bundle."""
    if not bundle_path.exists():
        print(f"ERROR: Bundle not found: {bundle_path}", file=sys.stderr)
        return False
    if not manifest_path.exists():
        print(f"ERROR: Manifest not found: {manifest_path}", file=sys.stderr)
        return False

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        print("ERROR: Manifest must be a JSON object", file=sys.stderr)
        return False

    required = manifest.get("required_entries", [])

    with zipfile.ZipFile(bundle_path, "r") as zf:
        zip_names = set(zf.namelist())

    missing = [r for r in required if r not in zip_names]
    actual = sorted(zip_names)

    result = {
        "bundle": str(bundle_path),
        "manifest": str(manifest_path),
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "total_files_in_bundle": len(zip_names),
        "required_entries_count": len(required),
        "actual_entries": actual,
        "missing_entries": missing,
        "pass": len(missing) == 0,
    }

    if missing:
        print(f"FAIL  V26-EvidenceBundleManifest: {len(missing)} missing entries")
        for m in missing:
            print(f"  MISSING: {m}")
    else:
        print(f"PASS  V26-EvidenceBundleManifest: All {len(required)} required entries present ({len(zip_names)} total files)")

    if not dry_run:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"Written: {output_path}")

    return result["pass"]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate evidence bundle against manifest (V26)"
    )
    parser.add_argument("--validate-bundle", required=True, help="Path to evidence bundle ZIP")
    parser.add_argument("--manifest", required=True, help="Path to evidence_bundle_manifest.json")
    parser.add_argument("--output", default="reports/backlinks/sprint-BL-DEEP-EXEC-v3.1/v26_evidence_bundle.json")
    parser.add_argument("--dry-run", action="store_true", help="Report only; do not write output file")
    args = parser.parse_args()

    ok = validate_bundle(
        Path(args.validate_bundle),
        Path(args.manifest),
        Path(args.output),
        dry_run=args.dry_run,
    )
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
