#!/usr/bin/env python3
"""Launch Hardening Dashboard — aggregate readiness state for all products.

Checks that every registered product has:
  1. A phase_state entry
  2. A readiness report
  3. H-gate sign-off files (or documented BLOCKED status)

Usage:
    python scripts/pipeline/commands/diagnostics/launch_dashboard.py
    python scripts/pipeline/commands/diagnostics/launch_dashboard.py --ci  # exit 1 if gaps
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
PRODUCTS_PATH = REPO_ROOT / "data" / "products.json"
PHASE_STATE_PATH = REPO_ROOT / "reports" / "phase_state.json"
HREVIEW_DIR = REPO_ROOT / "reports" / "human-review"
KNOWLEDGE_DIR = REPO_ROOT / "knowledge"

HGATES = ("h01", "h02", "h03", "h04", "h05")


def _load_products() -> list[dict]:
    return json.loads(PRODUCTS_PATH.read_text(encoding="utf-8"))


def _load_phase_state() -> dict:
    if not PHASE_STATE_PATH.exists():
        return {}
    return json.loads(PHASE_STATE_PATH.read_text(encoding="utf-8"))


def _check_hgates(family: str, platform: str) -> dict[str, str]:
    slug = f"{family}-{platform}"
    results = {}
    for gate in HGATES:
        path = HREVIEW_DIR / f"{slug}-{gate}-sample.md"
        if not path.is_file():
            results[gate] = "MISSING"
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"^result:\s*\"?(PASS|FAIL|CONDITIONAL)\"?\s*$",
                      text, re.MULTILINE | re.IGNORECASE)
        results[gate] = m.group(1).upper() if m else "UNPARSEABLE"
    return results


def _check_knowledge(family: str, platform: str) -> dict:
    model_path = KNOWLEDGE_DIR / family / platform / "merged" / "model.yaml"
    if not model_path.exists():
        return {"exists": False, "stale": None}
    text = model_path.read_text(encoding="utf-8", errors="replace")
    stale_m = re.search(r"stale_since:\s*(\S+)", text)
    stale = stale_m.group(1) if stale_m else "null"
    return {"exists": True, "stale": stale if stale != "null" else None}


def _readiness_verdict(family: str, platform: str) -> str:
    path = REPO_ROOT / "reports" / family / platform / "readiness.md"
    if not path.is_file():
        return "NO_REPORT"
    text = path.read_text(encoding="utf-8", errors="replace")
    if "READY TO SHIP" in text:
        return "READY"
    return "NOT_READY"


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch Hardening Dashboard")
    parser.add_argument("--ci", action="store_true",
                        help="Exit 1 if coverage gaps exist")
    args = parser.parse_args()

    products = _load_products()
    phase_state = _load_phase_state()

    rows = []
    gaps = 0

    for p in products:
        family, platform = p["family"], p["platform"]
        key = f"{family}/{platform}"

        has_phase = key in phase_state
        knowledge = _check_knowledge(family, platform)
        hgates = _check_hgates(family, platform)
        hgate_pass = sum(1 for v in hgates.values() if v == "PASS")
        hgate_cond = sum(1 for v in hgates.values() if v == "CONDITIONAL")
        hgate_missing = sum(1 for v in hgates.values() if v == "MISSING")
        verdict = _readiness_verdict(family, platform)

        row_gaps = []
        if not has_phase:
            row_gaps.append("no phase_state")
        if hgate_missing > 0:
            row_gaps.append(f"{hgate_missing} H-gates missing")
        if verdict == "NO_REPORT":
            row_gaps.append("no readiness report")
        if knowledge.get("stale"):
            row_gaps.append(f"stale since {knowledge['stale']}")

        gaps += len(row_gaps)

        rows.append({
            "product": key,
            "phase_state": "YES" if has_phase else "NO",
            "knowledge": "STALE" if knowledge.get("stale") else ("OK" if knowledge["exists"] else "MISSING"),
            "hgates": f"{hgate_pass}P/{hgate_cond}C/{hgate_missing}M",
            "verdict": verdict,
            "gaps": "; ".join(row_gaps) if row_gaps else "",
        })

    # Print dashboard
    print("=" * 90)
    print("LAUNCH HARDENING DASHBOARD")
    print("=" * 90)
    print(f"{'Product':<22} {'Phase':<6} {'Knowledge':<10} {'H-Gates':<10} {'Verdict':<12} {'Gaps'}")
    print("-" * 90)
    for r in rows:
        print(f"{r['product']:<22} {r['phase_state']:<6} {r['knowledge']:<10} "
              f"{r['hgates']:<10} {r['verdict']:<12} {r['gaps']}")
    print("-" * 90)
    ready = sum(1 for r in rows if r["verdict"] == "READY")
    not_ready = sum(1 for r in rows if r["verdict"] == "NOT_READY")
    no_report = sum(1 for r in rows if r["verdict"] == "NO_REPORT")
    print(f"Total: {len(rows)} products | READY: {ready} | NOT READY: {not_ready} | "
          f"NO REPORT: {no_report} | Gaps: {gaps}")

    if args.ci and gaps > 0:
        print(f"\nCI FAIL: {gaps} coverage gap(s) found", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
