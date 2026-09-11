"""check_no_raw_stale_since_gating.py — regression guard closing out the
FRESH-001 migration (H3, 2026-09-11).

`freshness_guard.py`'s 10-state model (FRESH-001) replaced the old, narrow
"read model.yaml['stale_since'], gate on `is not None`" pattern across
batch_reference.py, refresh_run.py, launch_gate.py, and readiness_gate.py.
`site_planner.py` was the one known call site never migrated: it kept a raw
`stale_since is not None` gate that missed 9 of the 10 states
freshness_guard exists to catch (corrupt cross-source disagreement, an
orphaned baseline, a failed-refresh marker, ...) -- confirmed live while
bootstrapping imaging/net knowledge
(reports/skill-gaps/2026-09-11-imaging-net-pipeline-hardening-prerequisites.md).
Fixed by migrating both of its call sites onto
`freshness_guard.is_generation_allowed(mode="degraded")`.

This check asserts no OTHER file reintroduces the same raw gating pattern
(a literal `stale_since is not None` / `stale_since is None` conditional)
outside freshness_guard.py itself (the one legitimate owner of that check)
and scan_stale.py (S-12, the script that originally COMPUTES stale_since --
reading its own freshly-derived value is not the anti-pattern this guards
against). No baseline/ratchet file: as of 2026-09-11 the codebase has zero
other occurrences, so this starts clean rather than grandfathering anything.

Usage:
    python scripts/ci/checks/check_no_raw_stale_since_gating.py
    python scripts/ci/checks/check_no_raw_stale_since_gating.py --json

Exit codes:
    0  no raw stale_since gating pattern found outside the allowed files
    1  at least one file reintroduced the pattern
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[3]
_cfg_repo_root = _DEFAULT_REPO_ROOT

# Files legitimately allowed to gate on a raw stale_since None-check:
# freshness_guard.py IS the shared implementation; scan_stale.py (S-12) is
# the script that originally computes/sets stale_since, not a consumer
# gating generation on someone else's already-computed value.
_ALLOWED_FILES = frozenset({
    "scripts/pipeline/lib/freshness_guard.py",
    "scripts/pipeline/commands/knowledge/scan_stale.py",
})

_GATING_PATTERN_RE = re.compile(r"stale_since\s+is\s+(not\s+)?None")


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing."""
    global _cfg_repo_root
    _cfg_repo_root = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT


def find_violations(pipeline_dir: "Path | None" = None) -> "dict[str, list[int]]":
    """relative file path -> list of 1-indexed line numbers containing the
    raw `stale_since is (not) None` gating pattern, excluding _ALLOWED_FILES
    and test files."""
    pipeline_dir = pipeline_dir or (_cfg_repo_root / "scripts" / "pipeline")
    violations: "dict[str, list[int]]" = {}
    if not pipeline_dir.is_dir():
        return violations
    for py_file in sorted(pipeline_dir.rglob("*.py")):
        rel = str(py_file.relative_to(_cfg_repo_root)).replace("\\", "/")
        if rel in _ALLOWED_FILES:
            continue
        if "/tests/" in rel or py_file.name.startswith("test_"):
            continue
        try:
            text = py_file.read_text(encoding="utf-8")
        except OSError:
            continue
        lines = [i + 1 for i, line in enumerate(text.splitlines()) if _GATING_PATTERN_RE.search(line)]
        if lines:
            violations[rel] = lines
    return violations


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args(argv)

    violations = find_violations()

    if args.json:
        print(json.dumps({"violations": violations}, indent=2))
        return 1 if violations else 0

    if not violations:
        print("OK: no raw stale_since gating pattern found outside freshness_guard.py/scan_stale.py.")
        return 0

    print("BROKEN: raw stale_since gating pattern found (bypasses freshness_guard.py's 10-state model):")
    for rel, lines in sorted(violations.items()):
        for line_no in lines:
            print(f"  {rel}:{line_no}")
    print("Fix: migrate to freshness_guard.is_generation_allowed(family, platform, mode=\"degraded\").")
    return 1


if __name__ == "__main__":
    sys.exit(main())
