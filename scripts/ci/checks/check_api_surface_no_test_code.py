#!/usr/bin/env python3
"""check_api_surface_no_test_code.py — HRD-11 (MT076-2026-10-07-PSD-NET-PYTHON-LAUNCH), Layer 3.

Fail-closed portfolio guard: no committed `knowledge/{family}/{platform}/merged/api_surface.json`
may contain an entry whose `file` is test-like (a test-project directory by name/suffix/prefix,
a pytest-convention file, or .NET build output) -- the exact defect class HRD-04 fixed at
extraction time (`extraction.tree_helpers._is_non_public_path`; found live on psd/python: 13
test classes in a 77-entry surface, because a manifest-less Python package root falls back to
the whole repo). HRD-04 removed the cause; this check makes a future regression impossible to
miss, independent of whether Layer 1 (`validate_scout_output.check_no_test_entries`) or Layer 2
(`batch_reference.py`'s refusal) are ever exercised on the path that produced it.

Reuses the SAME predicate as the extraction fix and as Layer 1/2 (one shared implementation,
never a reimplementation that could silently drift from it).

Usage:
    python scripts/ci/checks/check_api_surface_no_test_code.py
    python scripts/ci/checks/check_api_surface_no_test_code.py --family psd --platform python

Exit codes:
    0 — no test-like entries in any scanned api_surface.json
    1 — at least one test-like entry found
    2 — configuration error (knowledge/ missing, a file unreadable)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
KNOWLEDGE_ROOT = REPO_ROOT / "knowledge"

_PIPELINE_ROOT = str(REPO_ROOT / "scripts" / "pipeline")
if _PIPELINE_ROOT not in sys.path:
    sys.path.insert(0, _PIPELINE_ROOT)
from extraction.validate_scout_output import check_no_test_entries  # noqa: E402


def _tracked_api_surface_paths() -> set[Path]:
    """Git-tracked `knowledge/*/*/merged/api_surface.json` paths only -- this check's job is
    "no committed product's knowledge regresses", not "every file lying in the working tree
    right now" (a product mid-launch can have an untracked, pre-commit scout artifact that is
    expected to still be test-contaminated; that is not yet a committed regression)."""
    try:
        out = subprocess.run(
            ["git", "ls-files", "--", "knowledge/*/*/merged/api_surface.json"],
            cwd=REPO_ROOT, capture_output=True, text=True, check=True,
            encoding="utf-8", errors="replace",
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return set()
    return {(REPO_ROOT / line).resolve() for line in out.splitlines() if line.strip()}


def discover_api_surfaces() -> list[tuple[str, str, Path]]:
    # path parts end ..., family, platform, "merged", "api_surface.json"
    tracked = _tracked_api_surface_paths()
    return sorted(
        (p.parts[-4], p.parts[-3], p)
        for p in KNOWLEDGE_ROOT.glob("*/*/merged/api_surface.json")
        if p.resolve() in tracked
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family", help="Scope to one family")
    parser.add_argument("--platform", help="Scope to one platform (requires --family)")
    args = parser.parse_args(argv)

    if not KNOWLEDGE_ROOT.is_dir():
        print(f"ERROR: {KNOWLEDGE_ROOT} does not exist", file=sys.stderr)
        return 2

    surfaces = discover_api_surfaces()
    if args.family:
        surfaces = [s for s in surfaces if s[0] == args.family]
    if args.platform:
        surfaces = [s for s in surfaces if s[1] == args.platform]

    violations: list[tuple[str, str, dict]] = []
    for family, platform, path in surfaces:
        try:
            api_surface = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"ERROR: could not read {path}: {exc}", file=sys.stderr)
            return 2
        if not isinstance(api_surface, list):
            # A handful of legacy artifacts wrap the list under a top-level key.
            api_surface = api_surface.get("classes", api_surface.get("entries", []))
        result = check_no_test_entries(api_surface)
        if result["verdict"] == "FAIL":
            violations.append((family, platform, result))

    if not violations:
        print(f"OK: 0 test-like api_surface.json entries across {len(surfaces)} product(s).")
        return 0

    print(f"FAIL: {len(violations)} product(s) have test-like entries in api_surface.json:")
    for family, platform, result in violations:
        print(f"  {family}/{platform}: {result['test_like_count']} entr(y/ies)")
        for f in result["test_like_files"][:5]:
            print(f"    - {f}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
