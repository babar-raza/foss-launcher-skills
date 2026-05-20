# Adapted from aspose.org scripts/ci/checks/ for standalone use
"""check_proof_bundles.py — CI gate: verify compliance observations have proof bundles.

For every .md file in reports/compliance/, check that a corresponding proof bundle
exists in reports/proofs/ with a valid manifest.json.

A proof bundle is "corresponding" if:
  - Its manifest.json "related_observation" field points to the compliance observation, OR
  - The bundle_id or directory name contains the base name of the compliance observation.

Usage:
    python scripts/ci/checks/check_proof_bundles.py [--strict]

Flags:
    --strict   Exit 1 if any compliance observation lacks a proof bundle (default: warning only)

Exit codes:
    0  all observations have corresponding bundles (or --strict not set)
    1  one or more observations lack bundles (only if --strict)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(os.environ.get("REPO_ROOT", Path(os.environ.get("REPO_ROOT", str(Path(__file__).resolve().parent.parent.parent.parent)))))

# Make shared pipeline utilities importable when this script is run directly.
_PIPELINE_DIR = _REPO_ROOT / "scripts" / "pipeline"
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))
_LIB_DIR = _PIPELINE_DIR / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from path_utils import repo_rel  # noqa: E402
_COMPLIANCE_DIR = _REPO_ROOT / "reports" / "compliance"
_PROOFS_DIR = _REPO_ROOT / "reports" / "proofs"
_INDEX_FILE = _REPO_ROOT / "reports" / "proofs" / "INDEX.json"


def _load_json(path: Path) -> dict | list | None:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _find_bundle_for_observation(obs_path: Path) -> Path | None:
    """Return the proof bundle directory for a compliance observation, if it exists."""
    obs_name = obs_path.stem  # e.g. "2026-03-31-family-sync-observation"

    # Method 1: check INDEX.json
    index = _load_json(_INDEX_FILE)
    if isinstance(index, list):
        for entry in index:
            related = entry.get("related_observation", "")
            if obs_path.name in related or obs_name in entry.get("bundle_id", ""):
                bundle_path = _REPO_ROOT / entry.get("path", "")
                if bundle_path.exists():
                    return bundle_path

    # Method 2: scan all bundle directories for matching manifest
    if not _PROOFS_DIR.exists():
        return None
    for bundle_dir in _PROOFS_DIR.iterdir():
        if not bundle_dir.is_dir():
            continue
        manifest_path = bundle_dir / "manifest.json"
        manifest = _load_json(manifest_path)
        if not isinstance(manifest, dict):
            continue
        related = manifest.get("related_observation", "")
        if obs_path.name in related or obs_name in related:
            return bundle_dir

        # Also match by directory name similarity
        if obs_name in bundle_dir.name or bundle_dir.name in obs_name:
            return bundle_dir

    return None


def _validate_bundle(bundle_dir: Path) -> list[str]:
    """Return a list of validation errors for a proof bundle directory."""
    errors = []
    required_files = ["manifest.json", "commands.log"]
    for fname in required_files:
        if not (bundle_dir / fname).exists():
            errors.append(f"missing {fname}")

    manifest_path = bundle_dir / "manifest.json"
    manifest = _load_json(manifest_path)
    if not isinstance(manifest, dict):
        errors.append("manifest.json is not valid JSON")
        return errors

    for field in ("bundle_id", "created_at", "repo_sha"):
        if not manifest.get(field):
            errors.append(f"manifest.json missing required field: {field}")

    return errors


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    strict = "--strict" in args

    if not _COMPLIANCE_DIR.exists():
        print("No reports/compliance/ directory found. Nothing to check.")
        return 0

    observations = sorted(_COMPLIANCE_DIR.rglob("*.md"))
    if not observations:
        print("No compliance observations found in reports/compliance/.")
        return 0

    missing: list[str] = []
    invalid: list[tuple[str, list[str]]] = []
    valid: list[str] = []

    for obs_path in observations:
        bundle_dir = _find_bundle_for_observation(obs_path)
        obs_rel = repo_rel(obs_path)

        if bundle_dir is None:
            missing.append(obs_rel)
            continue

        errors = _validate_bundle(bundle_dir)
        bundle_rel = repo_rel(bundle_dir)
        if errors:
            invalid.append((f"{obs_rel} -- {bundle_rel}", errors))
        else:
            retro = ""
            manifest = _load_json(bundle_dir / "manifest.json")
            if isinstance(manifest, dict) and manifest.get("retroactive"):
                retro = " [retroactive]"
            valid.append(f"{obs_rel} -- {bundle_rel}{retro}")

    if valid:
        print(f"Observations with valid proof bundles ({len(valid)}):")
        for v in valid:
            print(f"  OK: {v}")

    if invalid:
        print(f"\nObservations with INVALID proof bundles ({len(invalid)}):")
        for obs, errors in invalid:
            print(f"  INVALID: {obs}")
            for e in errors:
                print(f"    - {e}")

    if missing:
        print(f"\nObservations WITHOUT proof bundles ({len(missing)}):")
        for m in missing:
            print(f"  MISSING: {m}")
        print()
        print("To create a proof bundle:")
        print("  bash scripts/ci/hooks/capture_proof_bundle.sh <slug> <command1> ...")

    if (missing or invalid) and strict:
        return 1

    if missing or invalid:
        print("\nWarning: some observations lack proof bundles (use --strict to fail CI).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
