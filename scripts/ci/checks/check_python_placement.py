#!/usr/bin/env python3
"""check_python_placement.py — Python file placement governance.

Enforces that .py files are only created in sanctioned locations.
Run this check before committing new Python files, in CI, and via
the PreToolUse Write hook.

Four rules:

  RULE 1 (BLOCKING): No .py files at repo root.
  RULE 2 (BLOCKING): No .py files directly at scripts/ root.
  RULE 3 (BLOCKING): No .py files in scripts/one-shot/ (retired directory).
  RULE 4 (BLOCKING for new files / ADVISORY for existing):
         .py files in scripts/maintenance/ must be registered
         in scripts/maintenance/registry.yaml.
         A newly-added file (not yet in HEAD) blocks the commit.
         A modification to an existing file prints an advisory only.

Sanctioned locations:
  scripts/pipeline/     Operational pipeline scripts (8-step registration required)
  scripts/ci/           CI-only validators (standalone; no content writes)
  scripts/maintenance/  Operator-run one-off mutations (registry.yaml entry required)
  scripts/translator/   Translation subsystem package
  scripts/gap-eval/     Gap evaluation tool
  scripts/seo/          Optional SEO analysis
  scripts/generator/    Reference page generator
  tests/                Test fixtures and integration tests

Usage:
    python scripts/ci/checks/check_python_placement.py
    python scripts/ci/checks/check_python_placement.py --dry-run
    python scripts/ci/checks/check_python_placement.py --check-staged
    python scripts/ci/checks/check_python_placement.py --check-baseline
    python scripts/ci/checks/check_python_placement.py --propose scripts/bad_script.py

Exit codes:
    0  All blocking rules pass (advisory warnings may still be printed)
    1  One or more blocking violations found (including RULE 4 for new files)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
BASELINE_PATH = REPO_ROOT / "scripts" / "ci" / "fixtures" / "python_placement_baseline.json"
MAINTENANCE_REGISTRY = REPO_ROOT / "scripts" / "maintenance" / "registry.yaml"

# Directories excluded from all scans
EXCLUDED_PREFIXES = (
    ".venv/",
    ".git/",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rel(path: Path) -> str:
    """Return forward-slash relative path from repo root."""
    return path.relative_to(REPO_ROOT).as_posix()


def _is_excluded(rel: str) -> bool:
    for prefix in EXCLUDED_PREFIXES:
        if rel.startswith(prefix):
            return True
    # Also exclude __pycache__ anywhere
    if "__pycache__" in rel:
        return True
    return False


def _load_baseline() -> set[str]:
    """Return set of baseline violation paths (forward-slash relative)."""
    if not BASELINE_PATH.exists():
        return set()
    data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    return {v["path"] for v in data.get("violations", [])}


def _load_maintenance_registry_paths() -> set[str]:
    """Return set of paths registered in scripts/maintenance/registry.yaml."""
    if not MAINTENANCE_REGISTRY.exists():
        return set()
    try:
        import yaml  # type: ignore
    except ImportError:
        return set()
    data = yaml.safe_load(MAINTENANCE_REGISTRY.read_text(encoding="utf-8")) or {}
    return {entry["path"] for entry in data.get("scripts", []) if "path" in entry}


def _staged_py_files() -> list[str]:
    """Return list of staged .py file paths (relative, forward-slash)."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        paths = [p.strip() for p in result.stdout.splitlines() if p.strip().endswith(".py")]
        return paths
    except FileNotFoundError:
        return []


def _newly_added_staged_files() -> set[str]:
    """Return set of staged files that are newly added (not in HEAD)."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=A"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        return {p.strip() for p in result.stdout.splitlines() if p.strip()}
    except FileNotFoundError:
        return set()


def _all_repo_py_files() -> list[str]:
    """Return all .py files in the repo (relative, forward-slash), excluding venv etc."""
    results = []
    for p in REPO_ROOT.rglob("*.py"):
        try:
            rel = _rel(p)
        except ValueError:
            continue
        if not _is_excluded(rel):
            results.append(rel)
    return sorted(results)


# ---------------------------------------------------------------------------
# Rule evaluation
# ---------------------------------------------------------------------------

def classify(rel: str) -> tuple[int | None, str]:
    """Return (rule_number, violation_message) or (None, '') if clean."""
    parts = Path(rel).parts  # ('scripts', 'pipeline', 'audit.py') etc.

    # RULE 1: .py at repo root — parent has no parts beyond filename
    if len(parts) == 1:
        return (
            1,
            f"PLACEMENT VIOLATION [RULE 1]: {rel}\n"
            f"  .py files are forbidden at repo root.\n"
            f"  Correct locations:\n"
            f"    scripts/maintenance/  (operator one-off; add to scripts/maintenance/registry.yaml)\n"
            f"    scripts/pipeline/     (pipeline-integrated; follow PIPELINE.md New File Protocol)\n"
            f"  path_guard.py will block staging this file.",
        )

    # RULE 2: .py directly at scripts/ root
    if len(parts) == 2 and parts[0] == "scripts":
        return (
            2,
            f"PLACEMENT VIOLATION [RULE 2]: {rel}\n"
            f"  .py files are forbidden at scripts/ root.\n"
            f"  Correct locations:\n"
            f"    scripts/maintenance/  (operator one-off; add to scripts/maintenance/registry.yaml)\n"
            f"    scripts/pipeline/     (operational; follow PIPELINE.md New File Protocol)\n"
            f"    scripts/ci/           (CI-only validator)\n"
            f"  path_guard.py will block staging this file.",
        )

    # RULE 3: .py in scripts/one-shot/
    if len(parts) >= 2 and parts[0] == "scripts" and parts[1] == "one-shot":
        return (
            3,
            f"PLACEMENT VIOLATION [RULE 3]: {rel}\n"
            f"  scripts/one-shot/ is retired. No new files allowed here.\n"
            f"  If this is a completed operation: move to scripts/maintenance/ with status: done.\n"
            f"  If obsolete: delete.",
        )

    return (None, "")


def check_maintenance_registration(
    rel: str,
    registered_paths: set[str],
    newly_added: set[str] | None = None,
) -> tuple[str, bool] | None:
    """Check if a scripts/maintenance/ .py file is registered.

    Returns (message, is_blocking) if unregistered, else None.
    A newly-added file (not yet in HEAD) is blocking; an existing file is advisory.
    """
    parts = Path(rel).parts
    if len(parts) >= 2 and parts[0] == "scripts" and parts[1] == "maintenance" and rel.endswith(".py"):
        # Skip __init__.py
        if parts[-1] == "__init__.py":
            return None
        if rel not in registered_paths:
            is_new = newly_added is not None and rel in newly_added
            severity = "BLOCKING" if is_new else "ADVISORY"
            label = "VIOLATION" if is_new else "ADVISORY"
            msg = (
                f"{label} [RULE 4]: {rel}\n"
                f"  scripts/maintenance/ file has no entry in scripts/maintenance/registry.yaml.\n"
                f"  Add: path: {rel}, kind: <one-shot|repair|migration>, purpose: '...', "
                f"created: '<date>', status: pending"
            )
            return (msg, is_new)
    return None


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------

def run_propose(proposed_path: str) -> int:
    """--propose mode: check a single proposed path and give guidance. Returns exit code."""
    rel = proposed_path.replace("\\", "/").lstrip("./")
    rule, msg = classify(rel)
    if rule is not None:
        print(msg, file=sys.stderr)
        return 1
    # Check RULE 4 — proposed files are always "new" (blocking)
    registered = _load_maintenance_registry_paths()
    result = check_maintenance_registration(rel, registered, newly_added={rel})
    if result:
        msg, is_blocking = result
        print(msg, file=sys.stderr)
        if is_blocking:
            return 1
    return 0


def run_check(paths: list[str], check_baseline: bool, dry_run: bool) -> int:
    """Check a list of relative paths. Returns exit code."""
    baseline = _load_baseline() if check_baseline else set()
    registered = _load_maintenance_registry_paths()
    newly_added = _newly_added_staged_files()

    blocking: list[str] = []
    advisories: list[str] = []
    new_violations: list[str] = []

    for rel in paths:
        rule, msg = classify(rel)
        if rule is not None:
            blocking.append(msg)
            if check_baseline and rel not in baseline:
                new_violations.append(rel)
        else:
            result = check_maintenance_registration(rel, registered, newly_added)
            if result:
                msg, is_blocking = result
                if is_blocking:
                    blocking.append(msg)
                else:
                    advisories.append(msg)

    # Print advisories
    if advisories:
        print(f"ADVISORY: {len(advisories)} unregistered scripts/maintenance/ file(s):",
              file=sys.stderr)
        for a in advisories:
            print(a, file=sys.stderr)
            print(file=sys.stderr)

    if check_baseline:
        # In baseline mode: only fail on violations NOT in baseline
        if new_violations:
            print(
                f"\nFAIL: {len(new_violations)} new Python placement violation(s) "
                f"(not in baseline):",
                file=sys.stderr,
            )
            for rel in new_violations:
                _, msg = classify(rel)
                print(msg, file=sys.stderr)
                print(file=sys.stderr)
            if dry_run:
                print("(dry-run: exiting 0 despite failures)")
                return 0
            return 1
        known_count = len([r for _, r in [(classify(p)) for p in paths] if r])
        # Count actual blocking ones in baseline
        in_baseline = sum(1 for p in paths if classify(p)[0] is not None and p in baseline)
        print(
            f"OK: Python placement check passed ({len(paths)} files scanned, "
            f"{in_baseline} known baseline violation(s) excluded, 0 new violations)."
        )
        return 0

    # Normal mode: fail on any blocking violation
    if blocking:
        print(f"\nFAIL: {len(blocking)} Python placement violation(s):", file=sys.stderr)
        for msg in blocking:
            print(msg, file=sys.stderr)
            print(file=sys.stderr)
        if dry_run:
            print("(dry-run: exiting 0 despite failures)")
            return 0
        return 1

    print(
        f"OK: Python placement check passed ({len(paths)} files scanned, "
        f"{len(advisories)} advisory warning(s))."
    )
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report violations but always exit 0.",
    )
    parser.add_argument(
        "--check-staged",
        action="store_true",
        help="Only check currently staged .py files (for pre-commit hook use).",
    )
    parser.add_argument(
        "--check-baseline",
        action="store_true",
        help=(
            "Compare violations against baseline JSON; exit 1 only on NEW violations "
            "(for CI use during cleanup period)."
        ),
    )
    parser.add_argument(
        "--propose",
        metavar="PATH",
        help=(
            "Check a single proposed file path and print guidance. "
            "Exit 1 if placement is wrong (for PreToolUse Write hook)."
        ),
    )
    args = parser.parse_args()

    if args.propose:
        return run_propose(args.propose)

    if args.check_staged:
        paths = _staged_py_files()
        if not paths:
            print("OK: No staged .py files to check.")
            return 0
    else:
        paths = _all_repo_py_files()

    return run_check(paths, check_baseline=args.check_baseline, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
