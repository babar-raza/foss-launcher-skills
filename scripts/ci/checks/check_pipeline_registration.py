# Adapted from aspose.org scripts/ci/checks/ for standalone use
#!/usr/bin/env python3
"""check_pipeline_registration.py — Registry-backed pipeline script governance.

Five check categories:

  CHECK 1 — Completeness (BLOCKING):
    Every root .py file in scripts/pipeline/ (excl. __init__.py) has a registry entry.
    Every registry entry file exists on disk.

  CHECK 2 — Entrypoint backing (BLOCKING):
    Every entry with kind=entrypoint has backing.kind in {skill, workflow, internal}.
    If backing.kind=skill: skills/{ref}.md exists.

  CHECK 3 — Shim integrity (BLOCKING if any shims exist):
    Every entry with kind=shim has a non-null canonical_impl_path that exists on disk.

  CHECK 4 — Test coverage (two tiers):
    a) ALWAYS BLOCKING: entries with requires_test=true that have no existing test_target.
       This covers new scripts explicitly opted in to mandatory test coverage.
    b) ADVISORY by default: active entrypoints without requires_test=true that lack tests.
       Pass --fail-test-gaps to make (b) blocking as well.

  CHECK 5 — Deprecation hygiene (WARNING):
    Every entry with lifecycle=deprecated is noted; caller can review manually.

Usage:
    python scripts/ci/checks/check_pipeline_registration.py
    python scripts/ci/checks/check_pipeline_registration.py --dry-run        # exit 0 always
    python scripts/ci/checks/check_pipeline_registration.py --fail-test-gaps # CHECK 4b blocking
    python scripts/ci/checks/check_pipeline_registration.py --warn-test-gaps # CHECK 4b warns (default)

Exit codes:
    0 — all blocking checks pass
    1 — one or more blocking checks fail
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(os.environ.get("REPO_ROOT", str(Path(__file__).resolve().parents[3])))
REGISTRY_PATH = REPO_ROOT / "scripts" / "pipeline" / "config" / "registry.yaml"


def load_registry() -> list[dict]:
    try:
        import yaml
    except ImportError:
        print("ERROR: PyYAML not installed. Run: pip install pyyaml", file=sys.stderr)
        sys.exit(1)
    with open(REGISTRY_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("scripts", [])


def run_checks(dry_run: bool, fail_test_gaps: bool) -> int:
    if not REGISTRY_PATH.exists():
        print(f"ERROR: registry not found at {REGISTRY_PATH}", file=sys.stderr)
        return 1

    entries = load_registry()
    errors: list[str] = []
    warnings: list[str] = []

    registry_paths = {e.get("path", "") for e in entries}
    pipeline_root = REPO_ROOT / "scripts" / "pipeline"

    # CHECK 1 — Completeness
    # Every .py file in commands/, lib/, and root must be in registry
    disk_scripts = set()
    # Root scripts (only _bootstrap.py expected post-migration)
    for p in pipeline_root.glob("*.py"):
        if p.name != "__init__.py":
            disk_scripts.add(f"scripts/pipeline/{p.name}")
    # commands/ subdirectories
    # Dual-use files exist in both commands/ and lib/ — registry tracks the lib/ re-export
    lib_basenames = set()
    lib_dir_tmp = pipeline_root / "lib"
    if lib_dir_tmp.exists():
        lib_basenames = {p.name for p in lib_dir_tmp.glob("*.py") if p.name != "__init__.py"}
    commands_dir = pipeline_root / "commands"
    if commands_dir.exists():
        for p in commands_dir.rglob("*.py"):
            if p.name == "__init__.py":
                continue
            # Skip dual-use files tracked via lib/ re-export
            if p.name in lib_basenames:
                continue
            rel = p.relative_to(pipeline_root).as_posix()
            disk_scripts.add(f"scripts/pipeline/{rel}")
    # lib/ modules
    lib_dir = pipeline_root / "lib"
    if lib_dir.exists():
        for p in lib_dir.glob("*.py"):
            if p.name == "__init__.py":
                continue
            rel = p.relative_to(pipeline_root).as_posix()
            disk_scripts.add(f"scripts/pipeline/{rel}")
    # core/knowledge.py (registered individually; other core/ modules are internal)
    core_knowledge = pipeline_root / "core" / "knowledge.py"
    if core_knowledge.exists():
        disk_scripts.add("scripts/pipeline/core/knowledge.py")
    for unregistered in sorted(disk_scripts - registry_paths):
        errors.append(f"  [CHECK 1] UNREGISTERED: {unregistered} exists on disk but has no registry entry")

    # Every registry entry must exist on disk
    for entry in entries:
        path_str = entry.get("path", "")
        if path_str and not (REPO_ROOT / path_str).exists():
            errors.append(f"  [CHECK 1] MISSING: registry entry {path_str!r} not found on disk")

    # CHECK 2 — Entrypoint backing
    valid_backing_kinds = {"skill", "workflow", "internal"}
    for entry in entries:
        if entry.get("kind") != "entrypoint":
            continue
        path_str = entry.get("path", "<unknown>")
        backing = entry.get("backing") or {}
        bk = backing.get("kind", "")
        if bk not in valid_backing_kinds:
            errors.append(
                f"  [CHECK 2] {path_str}: invalid backing.kind={bk!r}; "
                f"must be one of {sorted(valid_backing_kinds)}"
            )
        elif bk == "skill":
            ref = backing.get("ref")
            if ref:
                skill_file = REPO_ROOT / "skills" / f"{ref}.md"
                if not skill_file.exists():
                    errors.append(
                        f"  [CHECK 2] {path_str}: backing skill skills/{ref}.md not found"
                    )

    # CHECK 3 — Shim integrity
    for entry in entries:
        if entry.get("kind") != "shim":
            continue
        path_str = entry.get("path", "<unknown>")
        canonical = entry.get("canonical_impl_path")
        if not canonical:
            errors.append(f"  [CHECK 3] {path_str}: kind=shim but canonical_impl_path is null")
        elif not (REPO_ROOT / canonical).exists():
            errors.append(
                f"  [CHECK 3] {path_str}: canonical_impl_path={canonical!r} not found on disk"
            )

    # CHECK 4 — Test coverage (two tiers)
    for entry in entries:
        if entry.get("lifecycle") not in ("active", "maintenance"):
            continue
        path_str = entry.get("path", "<unknown>")
        test_targets = entry.get("test_targets") or []
        has_test = any((REPO_ROOT / t).exists() for t in test_targets)
        requires_test = bool(entry.get("requires_test"))

        if not has_test:
            if requires_test:
                # CHECK 4a — ALWAYS BLOCKING: requires_test=true but no test found
                errors.append(
                    f"  [CHECK 4a] {path_str}: requires_test=true but no test_target exists on disk"
                )
            elif entry.get("kind") in ("entrypoint", "library") and entry.get("lifecycle") == "active":
                # CHECK 4b — advisory for active entrypoints/libraries without explicit opt-in
                msg = f"  [CHECK 4b] {path_str}: active entrypoint/library has no test_target"
                exempt_reason = entry.get("test_exempt_reason")
                if exempt_reason:
                    pass  # documented exemption — suppress warning
                elif fail_test_gaps:
                    errors.append(msg)
                else:
                    warnings.append(msg)

    # CHECK 5 — Deprecation hygiene
    for entry in entries:
        if entry.get("lifecycle") == "deprecated":
            path_str = entry.get("path", "<unknown>")
            warnings.append(f"  [CHECK 5] DEPRECATED: {path_str} (lifecycle=deprecated)")

    # Report
    if warnings:
        print(f"WARN: {len(warnings)} advisory issue(s):", file=sys.stderr)
        for w in warnings:
            print(w, file=sys.stderr)

    if errors:
        print(f"\nFAIL: {len(errors)} blocking issue(s):", file=sys.stderr)
        for e in errors:
            print(e, file=sys.stderr)
        if dry_run:
            print("\n(dry-run: exiting 0 despite failures)")
            return 0
        return 1

    total = len(entries)
    req_test_count = sum(1 for e in entries if e.get("requires_test"))
    print(f"OK: registration valid ({total} entries, 5 checks, 0 blocking issues; {req_test_count} require_test entries)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Report issues but always exit 0")
    parser.add_argument("--fail-test-gaps", action="store_true",
                        help="Make CHECK 4 (test coverage) blocking instead of advisory")
    parser.add_argument("--warn-test-gaps", action="store_true",
                        help="CHECK 4 is advisory (default, explicit flag for clarity)")
    args = parser.parse_args()
    return run_checks(dry_run=args.dry_run, fail_test_gaps=args.fail_test_gaps)


if __name__ == "__main__":
    sys.exit(main())
