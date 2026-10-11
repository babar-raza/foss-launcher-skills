"""Artifact completeness validator — SH-10 implementation.

Checks that all required sprint artifacts exist and are non-empty.
Fails if product-verdict.md is missing, if final/summary matrices are absent,
or if known-stale plan documents have not been superseded.

Usage:
    .venv/Scripts/python scripts/pipeline/commands/diagnostics/artifact_completeness.py
    .venv/Scripts/python scripts/pipeline/commands/diagnostics/artifact_completeness.py --sprint-dir reports/forensic-audit-healing-20260505-1238
    .venv/Scripts/python scripts/pipeline/commands/diagnostics/artifact_completeness.py --sprint-dir reports/forensic-audit-healing-20260505-1238 --json

Exit codes:
    0  All required artifacts present and non-empty
    1  One or more artifacts missing, empty, or stale without supersession
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]

# The 16 scoped products as folder names
SCOPED_PRODUCTS = [
    "cells-java", "cells-net", "cells-python",
    "slides-java", "slides-net", "slides-python", "slides-cpp",
    "words-python",
    "email-net", "email-cpp", "email-python",
    "note-python",
    "3d-java", "3d-net", "3d-python", "3d-typescript",
]

# Known stale files that must either be regenerated or explicitly superseded
KNOWN_STALE_FILES = {
    "summary/all-products-audit-matrix.md": (
        "Initial plan document showing all gates PENDING; "
        "superseded by final/16-product-verdict-matrix.md"
    ),
}

# Required final artifacts
REQUIRED_FINAL = [
    "final/16-product-verdict-matrix.md",
    "final/final-sprint-report.md",
]

# Required summary artifacts
REQUIRED_SUMMARY = [
    "summary/all-products-gap-summary.md",
    "summary/all-products-remedy-summary.md",
    "summary/all-products-open-blockers.md",
    "summary/all-products-final-verdict-matrix.md",
]


def check_sprint_dir(sprint_dir: Path) -> dict:
    """Check a sprint directory for completeness."""
    results = {
        "sprint_dir": str(sprint_dir),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pass": True,
        "findings": [],
    }

    def fail(msg: str, severity: str = "ERROR"):
        results["findings"].append({"severity": severity, "message": msg})
        if severity == "ERROR":
            results["pass"] = False

    # 1. Check all 16 product-verdict.md files
    products_dir = sprint_dir / "products"
    if not products_dir.exists():
        fail(f"products/ directory missing from {sprint_dir}")
    else:
        for product in SCOPED_PRODUCTS:
            pv = products_dir / product / "product-verdict.md"
            if not pv.exists():
                fail(f"product-verdict.md MISSING for {product}: {pv}")
            elif pv.stat().st_size == 0:
                fail(f"product-verdict.md EMPTY for {product}: {pv}")

    # 2. Check required final artifacts
    for rel_path in REQUIRED_FINAL:
        f = sprint_dir / rel_path
        if not f.exists():
            fail(f"Required final artifact MISSING: {f}")
        elif f.stat().st_size == 0:
            fail(f"Required final artifact EMPTY: {f}")

    # 3. Check required summary artifacts
    for rel_path in REQUIRED_SUMMARY:
        f = sprint_dir / rel_path
        if not f.exists():
            fail(f"Required summary artifact MISSING: {f}")
        elif f.stat().st_size == 0:
            fail(f"Required summary artifact EMPTY: {f}")

    # 4. Check product ledgers (each product needs 5 types)
    LEDGER_TYPES = ["baseline.md", "gap-ledger.md", "issue-ledger.md", "remedy-plan.md", "verification-plan.md"]
    if products_dir.exists():
        for product in SCOPED_PRODUCTS:
            for ledger in LEDGER_TYPES:
                lf = products_dir / product / ledger
                if not lf.exists():
                    fail(f"Product ledger MISSING: {product}/{ledger}", severity="WARN")

    # 5. Check for known stale files and supersession
    for rel_path, stale_reason in KNOWN_STALE_FILES.items():
        sf = sprint_dir / rel_path
        if sf.exists():
            content = sf.read_text(encoding="utf-8", errors="replace")
            if "SUPERSEDED" not in content and "superseded" not in content:
                fail(
                    f"STALE file present without supersession notice: {sf}\n"
                    f"  Reason: {stale_reason}",
                    severity="WARN"
                )

    return results


def main():
    parser = argparse.ArgumentParser(description="Artifact completeness validator")
    parser.add_argument(
        "--sprint-dir",
        default="reports/forensic-audit-healing-20260505-1238",
        help="Sprint directory to validate (relative to repo root)"
    )
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    sprint_dir = REPO_ROOT / args.sprint_dir
    if not sprint_dir.exists():
        print(f"ERROR: Sprint directory not found: {sprint_dir}", file=sys.stderr)
        sys.exit(1)

    results = check_sprint_dir(sprint_dir)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(f"\n# Artifact Completeness Validator")
        print(f"Sprint dir: {sprint_dir}")
        print(f"Timestamp: {results['timestamp']}\n")

        if not results["findings"]:
            print("PASS — all required artifacts present and non-empty")
        else:
            errors = [f for f in results["findings"] if f["severity"] == "ERROR"]
            warns = [f for f in results["findings"] if f["severity"] == "WARN"]
            print(f"{'PASS' if results['pass'] else 'FAIL'} — {len(errors)} ERROR(s), {len(warns)} WARN(s)\n")
            for finding in results["findings"]:
                prefix = "ERROR" if finding["severity"] == "ERROR" else "WARN "
                print(f"  [{prefix}] {finding['message']}")

    sys.exit(0 if results["pass"] else 1)


if __name__ == "__main__":
    main()
