# Adapted from aspose.org scripts/ci/checks/ for standalone use
"""check_proof_matrix.py — verify operator proof matrix completeness (TC-SR-13).

Checks that reports/proofs/INDEX.json contains at least one proof bundle tagged
with each of the 6 required operator scenarios. This is a LOCAL governance check
(reports/ is gitignored) run before claiming production readiness.

Required operator scenarios:
    1 - first-time setup
    2 - launch product
    3 - refresh / update content
    4 - audit content
    5 - repair content
    6 - failure recovery

A bundle is tagged for a scenario when its INDEX.json entry has:
    "operator_scenario": <int 1-6>

Usage:
    python scripts/ci/checks/check_proof_matrix.py [--json]

Exit codes:
    0  all 6 operator scenarios have at least one tagged proof bundle
    1  one or more scenarios are uncovered
    2  INDEX.json missing or unreadable (local-only — not an error in CI)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(os.environ.get("REPO_ROOT", Path(__file__).resolve().parent.parent.parent.parent))
_INDEX_FILE = _REPO_ROOT / "reports" / "proofs" / "INDEX.json"

REQUIRED_SCENARIOS: dict[int, str] = {
    1: "first-time setup",
    2: "launch product",
    3: "refresh / update content",
    4: "audit content",
    5: "repair content",
    6: "failure recovery",
}


def configure(*, index_file: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing."""
    global _INDEX_FILE
    if index_file is not None:
        _INDEX_FILE = Path(index_file)


def check(index_file: "Path | None" = None) -> tuple[int, dict[int, list[str]]]:
    """Check scenario coverage.

    Returns (exit_code, coverage) where coverage maps scenario_id → list of bundle_ids.
    exit_code 0 = all covered, 1 = gaps, 2 = INDEX.json unreadable.
    """
    target = index_file or _INDEX_FILE
    try:
        with open(target, encoding="utf-8") as f:
            entries = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"WARN: Cannot read {target}: {exc}", file=sys.stderr)
        return 2, {}

    if not isinstance(entries, list):
        print(f"WARN: {target} is not a JSON array", file=sys.stderr)
        return 2, {}

    coverage: dict[int, list[str]] = {s: [] for s in REQUIRED_SCENARIOS}

    for entry in entries:
        scenario = entry.get("operator_scenario")
        if isinstance(scenario, int) and scenario in coverage:
            coverage[scenario].append(entry.get("bundle_id", "(unknown)"))

    gaps = [s for s in REQUIRED_SCENARIOS if not coverage[s]]
    return (1 if gaps else 0), coverage


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    as_json = "--json" in args

    exit_code, coverage = check()

    if exit_code == 2:
        # INDEX.json not present — local-only artifact, not a hard failure
        print("Proof matrix: INDEX.json not found (local-only artifact — run locally, not in CI).")
        return 0  # advisory — do not block CI on missing local artifact

    if as_json:
        output = {
            "scenarios": {
                str(sid): {
                    "label": label,
                    "covered": bool(coverage.get(sid)),
                    "bundles": coverage.get(sid, []),
                }
                for sid, label in REQUIRED_SCENARIOS.items()
            },
            "overall": "PASS" if exit_code == 0 else "FAIL",
        }
        print(json.dumps(output, indent=2))
    else:
        print("Operator proof matrix coverage:")
        all_ok = True
        for sid, label in REQUIRED_SCENARIOS.items():
            bundles = coverage.get(sid, [])
            if bundles:
                print(f"  OK  scenario {sid} ({label}): {', '.join(bundles)}")
            else:
                print(f"  MISSING  scenario {sid} ({label}): no tagged bundle in INDEX.json")
                all_ok = False

        if all_ok:
            print("\nPASS: All 6 operator scenarios have proof bundle coverage.")
        else:
            print(
                "\nFAIL: One or more operator scenarios lack proof bundle coverage.\n"
                "Tag a bundle by adding 'operator_scenario': <1-6> to its INDEX.json entry."
            )

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
