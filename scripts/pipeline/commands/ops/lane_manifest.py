"""lane_manifest.py — Lane manifest JSON schema and validator.

Validates lane manifest files used by the lane-owned commit model.
Each lane declares owned_path_prefixes, dependencies, and lifecycle status.

Usage (CLI):
  python scripts/pipeline/commands/ops/lane_manifest.py validate --file path/to/manifest.json
  python scripts/pipeline/commands/ops/lane_manifest.py validate --dir path/to/lanes/

Exit codes:
  0  All manifests valid
  1  Validation errors found
  2  File not found or I/O error
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

VALID_STATUSES = frozenset({
    "PROPOSED",
    "PREFLIGHT_PENDING",
    "PREFLIGHT_PASSED",
    "ACTIVE",
    "VERIFYING",
    "VERIFIED",
    "COMMIT_ELIGIBLE",
    "COMMITTED",
    "INTEGRATION_VERIFIED",
    "BLOCKED",
    "REJECTED",
    "REVERT_REQUIRED",
    "REVERTED",
})

REQUIRED_FIELDS = (
    "lane_id",
    "sprint_id",
    "owned_path_prefixes",
    "shared_path_prefixes",
    "skills_expected",
    "depends_on_lanes",
    "status",
    "created_at",
    "committed_at",
    "commit_sha",
    "revert_sha",
)

LANE_ID_PATTERN_PREFIX = "LANE-"


def validate_manifest(data: dict, *, filename: str = "<unknown>") -> list[str]:
    """Validate a lane manifest dict. Returns list of error strings (empty = valid)."""
    errors: list[str] = []

    # Check required fields
    for field in REQUIRED_FIELDS:
        if field not in data:
            errors.append(f"[{filename}] Missing required field: {field}")

    if errors:
        # If required fields are missing, many checks below will fail
        return errors

    # lane_id format
    lane_id = data["lane_id"]
    if not isinstance(lane_id, str) or not lane_id:
        errors.append(f"[{filename}] lane_id must be a non-empty string")
    elif not lane_id.startswith(LANE_ID_PATTERN_PREFIX):
        errors.append(
            f"[{filename}] lane_id '{lane_id}' must start with '{LANE_ID_PATTERN_PREFIX}'"
        )

    # lane_id vs filename consistency (if filename looks like a lane manifest)
    if filename != "<unknown>" and filename.endswith(".json"):
        stem = Path(filename).stem.upper().replace("-", "-")
        expected_stem = lane_id.upper() if isinstance(lane_id, str) else ""
        # Allow flexible naming: LANE-A.json or lane-a.json
        if expected_stem and stem.upper() != expected_stem.upper():
            errors.append(
                f"[{filename}] lane_id '{lane_id}' does not match filename stem '{stem}'"
            )

    # sprint_id
    if not isinstance(data["sprint_id"], str) or not data["sprint_id"]:
        errors.append(f"[{filename}] sprint_id must be a non-empty string")

    # status
    status = data["status"]
    if status not in VALID_STATUSES:
        errors.append(
            f"[{filename}] Invalid status '{status}'. Must be one of: {sorted(VALID_STATUSES)}"
        )

    # owned_path_prefixes
    owned = data["owned_path_prefixes"]
    if not isinstance(owned, list):
        errors.append(f"[{filename}] owned_path_prefixes must be a list")
    elif len(owned) == 0:
        errors.append(f"[{filename}] owned_path_prefixes must not be empty")
    else:
        seen_owned = set()
        for i, prefix in enumerate(owned):
            if not isinstance(prefix, str):
                errors.append(f"[{filename}] owned_path_prefixes[{i}] must be a string")
                continue
            if not prefix:
                errors.append(f"[{filename}] owned_path_prefixes[{i}] must not be empty")
                continue
            # No absolute paths
            if prefix.startswith("/") or (len(prefix) > 1 and prefix[1] == ":"):
                errors.append(
                    f"[{filename}] owned_path_prefixes[{i}] '{prefix}' must be relative, not absolute"
                )
            # No parent-directory escapes
            if ".." in prefix:
                errors.append(
                    f"[{filename}] owned_path_prefixes[{i}] '{prefix}' must not contain '..'"
                )
            # No duplicates
            if prefix in seen_owned:
                errors.append(
                    f"[{filename}] owned_path_prefixes[{i}] '{prefix}' is duplicated"
                )
            seen_owned.add(prefix)

    # shared_path_prefixes
    shared = data["shared_path_prefixes"]
    if not isinstance(shared, list):
        errors.append(f"[{filename}] shared_path_prefixes must be a list")
    else:
        for i, prefix in enumerate(shared):
            if not isinstance(prefix, str):
                errors.append(f"[{filename}] shared_path_prefixes[{i}] must be a string")
            elif ".." in prefix:
                errors.append(
                    f"[{filename}] shared_path_prefixes[{i}] '{prefix}' must not contain '..'"
                )

    # skills_expected
    if not isinstance(data["skills_expected"], list):
        errors.append(f"[{filename}] skills_expected must be a list")

    # depends_on_lanes
    deps = data["depends_on_lanes"]
    if not isinstance(deps, list):
        errors.append(f"[{filename}] depends_on_lanes must be a list")
    else:
        for i, dep in enumerate(deps):
            if not isinstance(dep, str):
                errors.append(f"[{filename}] depends_on_lanes[{i}] must be a string")

    # created_at must be a string (ISO-8601)
    if not isinstance(data["created_at"], str) or not data["created_at"]:
        errors.append(f"[{filename}] created_at must be a non-empty ISO-8601 string")

    # committed_at and commit_sha can be null
    # revert_sha can be null

    return errors


def validate_file(filepath: Path) -> list[str]:
    """Load and validate a single lane manifest JSON file."""
    if not filepath.exists():
        return [f"File not found: {filepath}"]
    try:
        data = json.loads(filepath.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [f"Invalid JSON in {filepath}: {e}"]
    if not isinstance(data, dict):
        return [f"{filepath}: Root must be a JSON object"]
    return validate_manifest(data, filename=filepath.name)


def validate_directory(dirpath: Path) -> list[str]:
    """Validate all .json lane manifest files in a directory."""
    if not dirpath.is_dir():
        return [f"Directory not found: {dirpath}"]
    errors: list[str] = []
    manifests = sorted(dirpath.glob("*.json"))
    if not manifests:
        errors.append(f"No .json files found in {dirpath}")
        return errors
    for f in manifests:
        errors.extend(validate_file(f))
    return errors


def main(argv: list[str] | None = None) -> int:
    # Backward-compatible shim: strip leading 'validate' subcommand if present.
    # Allows both old-style  (--file X) and documented-style (validate --file X).
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] == "validate":
        argv = list(argv[1:])

    parser = argparse.ArgumentParser(
        description="Validate lane manifest JSON files."
    )
    parser.add_argument(
        "--file", type=Path, help="Path to a single lane manifest JSON file"
    )
    parser.add_argument(
        "--dir", type=Path, help="Path to a directory of lane manifest JSON files"
    )
    args = parser.parse_args(argv)

    if not args.file and not args.dir:
        parser.error("Must specify --file or --dir")

    errors: list[str] = []
    if args.file:
        errors.extend(validate_file(args.file))
    if args.dir:
        errors.extend(validate_directory(args.dir))

    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print("PASS: All manifests valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
