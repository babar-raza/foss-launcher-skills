# Adapted from aspose.org scripts/ci/checks/ for standalone use
"""check_pr_override_compliance.py — Verify that PR changes to forbidden paths have archived override proofs.

Called by content-audit.yml for any PR that touches forbidden paths.
Checks reports/overrides/archived/ for an entry whose scope covers the modified forbidden path.

Usage:
  python scripts/ci/checks/check_pr_override_compliance.py [file1 file2 ...]
  # Files are the PR diff (git diff --name-only origin/main...HEAD)

Exit codes:
  0  All forbidden-path changes have archived override proofs
  1  One or more forbidden-path changes lack override proof
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(os.environ.get("REPO_ROOT", Path(__file__).resolve().parent.parent.parent.parent))
# override_manager.py stores archived tokens here:
ARCHIVE_DIR = REPO_ROOT / "reports" / "overrides" / "archived"
# Legacy archive from simple overrides design:
LEGACY_ARCHIVE_DIR = REPO_ROOT / "overrides" / "archive"

sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline" / "commands" / "governance"))
from path_guard import check_path


def _normalize(path_str: str) -> str:
    p = path_str.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def load_archived_scopes() -> list[tuple[str, list[str]]]:
    """Return list of (filename, [normalized_paths]) from all archived override tokens."""
    result = []
    for archive_dir in (ARCHIVE_DIR, LEGACY_ARCHIVE_DIR):
        if not archive_dir.exists():
            continue
        for f in sorted(archive_dir.glob("*.json")):
            try:
                with f.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
                # override_manager tokens use 'paths' key; simple overrides used 'scope'
                paths = data.get("paths") or data.get("scope") or []
                normalized = [_normalize(p) for p in paths]
                result.append((f.name, normalized))
            except (json.JSONDecodeError, OSError):
                pass  # Corrupt archive entry — skip
    return result


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("No files provided — nothing to check.")
        return 0

    archive_scopes = load_archived_scopes()
    violations = []
    forbidden_checked = []

    for path_str in args:
        normalized = _normalize(path_str)
        decision, _ = check_path(normalized)
        if decision != "DENY":
            continue  # Allowed path — no override needed
        forbidden_checked.append(normalized)

        # Forbidden path — look for archived override covering it
        covered = any(
            normalized == p or normalized.startswith(p.rstrip("/") + "/")
            for _, scope in archive_scopes
            for p in scope
        )
        if not covered:
            violations.append(normalized)

    if violations:
        print(f"\nBLOCKED: {len(violations)} forbidden-path change(s) have no archived override proof:")
        for v in violations:
            print(f"  - {v}")
        print("\nEach forbidden-path write requires a human override token.")
        print("Create a token before committing:")
        print("  python scripts/pipeline/commands/governance/override_manager.py create \\")
        print("    --paths <path> --reason '...' --plan '...'")
        print("Then stage the token file (reports/overrides/pending/*.json) with your commit.")
        print("See governance docs §4 for the override policy.")
        return 1

    if forbidden_checked:
        print(f"All {len(forbidden_checked)} forbidden-path change(s) have valid archived override proofs.")
    else:
        print("No forbidden-path changes in this PR.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
