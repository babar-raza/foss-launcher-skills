# Adapted from aspose.org
"""manifest_restore.py — Restore freshness manifest from Gate 3 pre-write backup.

Restores the pre-Gate-3 backup file (freshness-manifest.pre-gate3.json) to the
live manifest path (freshness-manifest.json) using an atomic os.replace().

Usage:
  python scripts/pipeline/commands/ops/manifest_restore.py \\
    --product cells/java --subdomain reference

Exit codes:
  0  Restore succeeded
  1  Backup not found or restore failed
  2  Configuration error (bad --product format)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(os.environ.get("FOSS_REPO_ROOT", str(Path(__file__).resolve().parents[4])))
_STATE_ROOT = _REPO_ROOT / "runs" / "state"


def restore_manifest(
    product: str,
    subdomain: str,
    state_root: Path = _STATE_ROOT,
) -> int:
    """Restore freshness manifest from the pre-Gate-3 backup.

    Args:
        product: Product slug "family/platform".
        subdomain: Surface name (e.g. "reference").
        state_root: Override for manifest state directory (for testing).

    Returns:
        0 on success, 1 on failure.
    """
    family, platform = product.split("/", 1)
    manifest_dir = state_root / family / platform / subdomain
    manifest_path = manifest_dir / "freshness-manifest.json"
    backup_path = manifest_dir / "freshness-manifest.pre-gate3.json"

    if not backup_path.is_file():
        print(
            f"ERROR: No pre-Gate-3 backup found at {backup_path}",
            file=sys.stderr,
        )
        return 1

    # Read current manifest status (before-state for reporting).
    before_status = "NOT_PRESENT"
    before_run_id = "N/A"
    if manifest_path.is_file():
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            before_status = data.get("manifest_status", "UNKNOWN")
            before_run_id = data.get("run_id", "UNKNOWN")
        except (json.JSONDecodeError, OSError):
            before_status = "UNREADABLE"

    # Read backup content for after-state reporting.
    try:
        backup_data = json.loads(backup_path.read_text(encoding="utf-8"))
        after_status = backup_data.get("manifest_status", "UNKNOWN")
        after_run_id = backup_data.get("run_id", "UNKNOWN")
    except (json.JSONDecodeError, OSError) as exc:
        print(f"ERROR: Cannot read backup file: {exc}", file=sys.stderr)
        return 1

    # Perform atomic restore using os.replace.
    try:
        os.replace(str(backup_path), str(manifest_path))
    except OSError as exc:
        print(f"ERROR: os.replace failed during restore: {exc}", file=sys.stderr)
        return 1

    print(f"Restored manifest for {product}/{subdomain}")
    print(f"  Before: manifest_status={before_status!r}  run_id={before_run_id!r}")
    print(f"  After:  manifest_status={after_status!r}   run_id={after_run_id!r}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="manifest_restore",
        description="Restore freshness manifest from Gate 3 pre-write backup.",
    )
    parser.add_argument(
        "--product",
        required=True,
        help="Product slug 'family/platform' (e.g. cells/java)",
    )
    parser.add_argument(
        "--subdomain",
        required=True,
        help="Surface name (e.g. reference)",
    )
    args = parser.parse_args(argv)

    if "/" not in args.product:
        print(
            f"ERROR: --product must be 'family/platform', got {args.product!r}",
            file=sys.stderr,
        )
        return 2

    return restore_manifest(args.product, args.subdomain)


if __name__ == "__main__":
    raise SystemExit(main())
