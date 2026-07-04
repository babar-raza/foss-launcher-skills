#!/usr/bin/env python3
"""check_staged_deletions.py — Detect staged file deletions and renames without a DGR.

Scans staged changes for D (deleted) and R (renamed-source) statuses and
classifies each path into a tier. Tier 0 paths are always blocked. Tier 1
paths require a valid Deletion Governance Record (DGR) stored in
``deletion-approvals/``.

Usage:
    # Pre-commit mode (reads git diff --cached):
    python scripts/ci/checks/check_staged_deletions.py --check-staged

    # PR mode (reads deleted/renamed files from a base ref):
    python scripts/ci/checks/check_staged_deletions.py --base origin/main

Exit codes:
    0   No violations (or all violations are advisory T-02)
    2   T-00 or T-01 deletion without a valid DGR — blocks commit/PR

Mode control:
    DELETION_GATE_PHASE=1 (default): warn-only, exit 0 for all tiers
    DELETION_GATE_PHASE=2: blocking, exit 2 for T-00 and T-01 without DGR
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

REPO_ROOT = Path(__file__).resolve().parents[3]

# ---------------------------------------------------------------------------
# Tier classification — mirrors path_guard.py logic
# ---------------------------------------------------------------------------

_FORBIDDEN_EXACT: frozenset[str] = frozenset({
    "AGENTS.md",
    "CODEX.md",
    "CLAUDE.md",
    "docs/OPERATOR_BYPASSES.md",
    "scripts/pipeline/commands/governance/path_guard.py",
    "scripts/ci/hooks/check_session_gate.sh",
    "scripts/ci/hooks/bootstrap_session_gate.sh",
    "scripts/ci/hooks/check_content_edit_hook.sh",
    "scripts/ci/hooks/check_content_write_hook.sh",
    "scripts/ci/hooks/check_py_write_hook.sh",
    "scripts/ci/hooks/check_write_path_hook.sh",
    "scripts/ci/hooks/check_skill_context_hook.sh",
    "scripts/ci/hooks/check_venv_bash_hook.sh",
    "scripts/ci/hooks/check_destructive_bash_hook.sh",
    "scripts/ci/hooks/find_python.sh",
    "scripts/ci/hooks/check_venv.sh",
})

_FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "themes/",
    "layouts/",
    "configs/",
    ".claude/",
    ".agents/",
    ".kilocode/",
    "skills/",
    "docs/governance/",
    "docs/workflows/",
    "docs/registries/",
    ".github/workflows/",
)

_ALLOWED_PREFIXES: tuple[str, ...] = (
    "content/",
    "knowledge/",
    "data/",
    "patches/",
    "keywords/",
    "scripts/pipeline/",
    "scripts/ci/",
    "scripts/maintenance/",
    "scripts/gap-eval/",
    "scripts/generator/",
    "scripts/seo/",
    "tests/",
    "backlog/",
    "plans/",
    "docs/",
    "deletion-approvals/",
)

# T-02: advisory-only subtrees within allowed prefixes
_T02_PREFIXES: tuple[str, ...] = (
    "docs/",
    "scripts/maintenance/",
    "scripts/generator/",
    "scripts/seo/",
    "scripts/gap-eval/",
)

DGR_DIR = REPO_ROOT / "deletion-approvals"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class DeletedPath(NamedTuple):
    path: str
    status: str  # "D" or "R" (rename source)
    tier: str    # "T-00", "T-01", "T-02", "T-03"


# ---------------------------------------------------------------------------
# Tier classification
# ---------------------------------------------------------------------------

def _normalize(path_str: str) -> str:
    path_str = path_str.replace("\\", "/")
    while path_str.startswith("./"):
        path_str = path_str[2:]
    return path_str


def classify_tier(path_str: str) -> str:
    """Return 'T-00', 'T-01', 'T-02', or 'T-03' for a given path."""
    norm = _normalize(path_str)

    if norm in _FORBIDDEN_EXACT:
        return "T-00"

    for prefix in _FORBIDDEN_PREFIXES:
        if norm.startswith(prefix):
            return "T-00"

    for prefix in _T02_PREFIXES:
        if norm.startswith(prefix):
            return "T-02"

    for prefix in _ALLOWED_PREFIXES:
        if norm.startswith(prefix):
            return "T-01"

    return "T-03"


# ---------------------------------------------------------------------------
# DGR validation (fail-closed: missing dir or malformed YAML -> not valid)
# ---------------------------------------------------------------------------

def _is_expired(dgr: dict) -> bool:
    expires_at = dgr.get("expires_at", "")
    if not expires_at:
        return False
    try:
        ts = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
        return datetime.now(tz=timezone.utc) > ts
    except (ValueError, TypeError):
        return True  # malformed -> treat as expired


def _load_yaml_safe(path: Path) -> "dict | None":
    """Load a YAML file without requiring PyYAML — minimal parser for DGR format."""
    try:
        try:
            import yaml  # type: ignore
            with open(path, encoding="utf-8") as f:
                return yaml.safe_load(f)
        except ImportError:
            pass
        # Minimal fallback line-based parser
        data: dict = {}
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                if ":" not in line or line.lstrip().startswith("#"):
                    continue
                k, _, v = line.partition(":")
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k and v:
                    data[k] = v
        return data
    except OSError:
        return None


def find_valid_dgr(path_str: str) -> "tuple[bool, str]":
    """Return (is_valid, reason) for whether a DGR covers the given path."""
    norm = _normalize(path_str)

    if not DGR_DIR.exists():
        return False, "deletion-approvals/ directory does not exist"

    for dgr_file in sorted(DGR_DIR.glob("*.yaml")):
        dgr = _load_yaml_safe(dgr_file)
        if dgr is None:
            print(f"  WARNING: could not read DGR {dgr_file.name}", file=sys.stderr)
            continue
        if not isinstance(dgr, dict):
            continue

        files = dgr.get("files", [])
        if not isinstance(files, list):
            continue

        covered = any(
            isinstance(entry, dict)
            and _normalize(str(entry.get("path", ""))) == norm
            for entry in files
        )
        if not covered:
            continue

        if _is_expired(dgr):
            return False, f"DGR {dgr.get('dgr_id', dgr_file.stem)} is expired"

        return True, f"DGR {dgr.get('dgr_id', dgr_file.stem)} is valid"

    return False, f"No valid DGR covers path '{norm}'"


# ---------------------------------------------------------------------------
# Staged / PR change detection
# ---------------------------------------------------------------------------

def _parse_name_status(output: str) -> "list[DeletedPath]":
    paths: list[DeletedPath] = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if not parts:
            continue
        status_raw = parts[0].rstrip()
        if status_raw.startswith("R") and len(parts) >= 2:
            src = parts[1]
            if src:
                paths.append(DeletedPath(path=src, status="R", tier=classify_tier(src)))
        elif status_raw == "D" and len(parts) >= 2:
            path = parts[1]
            if path:
                paths.append(DeletedPath(path=path, status="D", tier=classify_tier(path)))
    return paths


def _get_staged_deletions() -> "list[DeletedPath]":
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-status", "--diff-filter=DR"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=15,
        )
    except (subprocess.TimeoutExpired, OSError):
        return []
    if result.returncode != 0:
        return []
    return _parse_name_status(result.stdout)


def _get_pr_deletions(base_ref: str) -> "list[DeletedPath]":
    try:
        result = subprocess.run(
            ["git", "diff", "--name-status", "--diff-filter=DR",
             f"{base_ref}...HEAD"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
        )
    except (subprocess.TimeoutExpired, OSError):
        return []
    if result.returncode != 0:
        return []
    return _parse_name_status(result.stdout)


# ---------------------------------------------------------------------------
# Reporting and gate logic
# ---------------------------------------------------------------------------

_STATUS_LABEL = {"D": "deleted", "R": "renamed-source"}


def check_paths(deleted_paths: "list[DeletedPath]") -> int:
    """Evaluate all deleted/renamed paths. Returns exit code (0 or 2)."""
    phase = int(os.environ.get("DELETION_GATE_PHASE", "1"))

    if not deleted_paths:
        print("Deletion gate: OK -- no staged deletions or renames detected.")
        return 0

    any_t00 = False
    any_t01_ungoverned = False

    for dp in deleted_paths:
        label = _STATUS_LABEL.get(dp.status, dp.status)

        if dp.tier == "T-00":
            print(f"  BLOCKED [T-00] {label}: {dp.path}", file=sys.stderr)
            print(
                "    Tier 0 -- no DGR authorizes this. T-00 paths can never be deleted.",
                file=sys.stderr,
            )
            any_t00 = True

        elif dp.tier == "T-01":
            valid, reason = find_valid_dgr(dp.path)
            if valid:
                print(f"  OK     [T-01] {label}: {dp.path} -- {reason}")
            else:
                print(f"  BLOCKED [T-01] {label}: {dp.path}", file=sys.stderr)
                print(f"    No valid DGR for T-01 path: {reason}", file=sys.stderr)
                any_t01_ungoverned = True

        elif dp.tier == "T-02":
            print(
                f"  ADVISORY [T-02] {label}: {dp.path} "
                "(T-02 -- review recommended, not blocked)"
            )

        # T-03: silent pass

    if phase >= 2 and (any_t00 or any_t01_ungoverned):
        print("", file=sys.stderr)
        print(
            "BLOCKED: Staged deletion requires a Deletion Governance Record (DGR).",
            file=sys.stderr,
        )
        print(
            "  Create:  python scripts/pipeline/commands/governance/"
            "deletion_governance_manager.py create \\",
            file=sys.stderr,
        )
        print(
            "             --files <path> --reason '...' --plan '<plan>' --class T-01",
            file=sys.stderr,
        )
        print(
            "  Commit DGR to deletion-approvals/ BEFORE staging the deletion.",
            file=sys.stderr,
        )
        print("  See docs/DELETION_GOVERNANCE.md", file=sys.stderr)
        return 2

    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: "list[str] | None" = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    if "--check-staged" in argv:
        paths = _get_staged_deletions()
    elif "--base" in argv:
        idx = argv.index("--base")
        if idx + 1 >= len(argv):
            print("ERROR: --base requires a ref argument", file=sys.stderr)
            return 1
        paths = _get_pr_deletions(argv[idx + 1])
    else:
        print(
            "Usage: check_staged_deletions.py --check-staged | --base <ref>",
            file=sys.stderr,
        )
        return 1

    return check_paths(paths)


if __name__ == "__main__":
    sys.exit(main())
