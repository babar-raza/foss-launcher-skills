#!/usr/bin/env python3
"""check_knowledge_stats_consistency.py — Cross-artifact class-count reconciliation.

MT067-2026-09-10, TC-06. See docs/reference/knowledge-stats.md for the full history: a
portfolio scan found 15 of 32 launched products with `merged/model.yaml` and
`merged/index.json` disagreeing on "how many classes" a product has, plus a universal
mislabeling bug in `merge_report.md`'s "Classes" row -- both caused by independently
reimplemented formulas with zero reconciliation between them.

`lib/class_stats.py`'s `compute_class_stats()` is now the single source of truth: every
writer (outputs.py, promote.py, index.py) calls it against the same `api_surface.json`.
Given that, `model.yaml`'s and `index.json`'s `stats.classes` blocks should ALWAYS agree
with a fresh computation from `api_surface.json` -- this check recomputes the ground truth
directly and compares every artifact against it. A mismatch now means one of two things,
distinguished in the finding text:
  - `model.yaml` is STALE (api_surface.json/claims.json were regenerated after the last
    `promote()` run) -- expected, fixable by rerunning promote.py, not a code bug.
  - `index.json` disagrees despite index.py recomputing live on every run (HARDEN-A13) --
    NOT expected; this indicates an actual regression (e.g. a reintroduced inline formula),
    not staleness.
A product with no `stats.classes` block yet (not backfilled since this fix landed) is
reported separately, not conflated with a real mismatch.

Usage:
    python scripts/ci/checks/check_knowledge_stats_consistency.py {family} {platform}
    python scripts/ci/checks/check_knowledge_stats_consistency.py --all
    python scripts/ci/checks/check_knowledge_stats_consistency.py --staged
    python scripts/ci/checks/check_knowledge_stats_consistency.py --all --advisory

Exit codes:
    0 — consistent (or --advisory was passed)
    1 — inconsistency found and --advisory was not passed
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
KNOWLEDGE_ROOT = REPO_ROOT / "knowledge"

_PIPELINE_ROOT = str(REPO_ROOT / "scripts" / "pipeline")
if _PIPELINE_ROOT not in sys.path:
    sys.path.insert(0, _PIPELINE_ROOT)
from lib.class_stats import compute_class_stats  # noqa: E402


def discover_products() -> list[tuple[str, str]]:
    # model.yaml path parts end ..., family, platform, "merged", "model.yaml" -- family/
    # platform are [-4]/[-3], not [-3]/[-2] (that pair is platform/"merged").
    return sorted(
        (p.parts[-4], p.parts[-3]) for p in KNOWLEDGE_ROOT.glob("*/*/merged/model.yaml")
    )


def staged_products() -> list[tuple[str, str]]:
    """Products touched by currently-staged files, for pre-commit scoping."""
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=REPO_ROOT, capture_output=True, text=True, check=True,
            encoding="utf-8", errors="replace",
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    found: set[tuple[str, str]] = set()
    for line in out.splitlines():
        parts = Path(line.strip()).parts
        if len(parts) >= 3 and parts[0] == "knowledge":
            found.add((parts[1], parts[2]))
    return sorted(found)


def _load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _load_yaml(path: Path):
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None


def check_product(family: str, platform: str) -> list[str]:
    """Return finding strings for one product; [] if consistent (or nothing to check)."""
    merged = KNOWLEDGE_ROOT / family / platform / "merged"
    findings: list[str] = []

    api_surface = _load_json(merged / "api_surface.json")
    if not isinstance(api_surface, list):
        return findings  # no ground truth available -- nothing to reconcile against
    ground_truth = compute_class_stats(api_surface)

    model = _load_yaml(merged / "model.yaml") or {}
    model_classes = model.get("stats", {}).get("classes")
    if model_classes is None:
        findings.append(
            f"{family}/{platform}: model.yaml has no stats.classes block yet "
            f"(not backfilled) -- rerun promote.py"
        )
    elif model_classes != ground_truth:
        findings.append(
            f"{family}/{platform}: model.yaml stats.classes {model_classes} != live "
            f"api_surface.json {ground_truth} (stale -- rerun promote.py)"
        )

    index = _load_json(merged / "index.json")
    index_classes = (index or {}).get("stats", {}).get("classes")
    if index_classes is None:
        findings.append(
            f"{family}/{platform}: index.json has no stats.classes block yet "
            f"(not backfilled) -- rerun index.py"
        )
    elif index_classes != ground_truth:
        findings.append(
            f"{family}/{platform}: index.json stats.classes {index_classes} != live "
            f"api_surface.json {ground_truth} (unexpected -- index.py recomputes live "
            f"every run, so this is a real regression, not staleness)"
        )

    report_path = merged / "merge_report.md"
    if report_path.exists():
        for line in report_path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("| Classes"):
                cells = [p.strip() for p in line.split("|")]
                if len(cells) >= 3:
                    try:
                        reported = int(cells[2])
                    except ValueError:
                        break
                    if reported != ground_truth["total_declared"]:
                        findings.append(
                            f"{family}/{platform}: merge_report.md 'Classes' row = "
                            f"{reported}, expected {ground_truth['total_declared']} "
                            f"(total_declared) -- rerun promote.py"
                        )
                break

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("family", nargs="?", help="Product family (requires platform)")
    parser.add_argument("platform", nargs="?", help="Product platform (requires family)")
    parser.add_argument("--all", action="store_true", help="Check every launched product")
    parser.add_argument("--staged", action="store_true",
                        help="Check only products touched by currently-staged files")
    parser.add_argument("--advisory", action="store_true",
                        help="Report issues but always exit 0 (WARN-mode rollout)")
    args = parser.parse_args()

    if args.all:
        products = discover_products()
    elif args.staged:
        products = staged_products()
    elif args.family and args.platform:
        products = [(args.family, args.platform)]
    else:
        parser.error("specify family + platform, --all, or --staged")
        return 2

    all_findings: list[str] = []
    for family, platform in products:
        all_findings.extend(check_product(family, platform))

    if all_findings:
        label = "WARN" if args.advisory else "FAIL"
        print(f"{label}: {len(all_findings)} knowledge-stats consistency issue(s) across "
              f"{len(products)} product(s) checked:", file=sys.stderr)
        for f in all_findings:
            print(f"  {f}", file=sys.stderr)
        if args.advisory:
            print("\n(advisory mode — exit 0)")
            return 0
        return 1

    print(f"OK: {len(products)} product(s) consistent (model.yaml / index.json / "
          f"merge_report.md all agree with a live api_surface.json recomputation)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
