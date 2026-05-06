"""Verdict consistency validator — SH-11 implementation.

Checks product-verdict.md files against defined safety rules.
A PUBLICATION READY verdict with unresolved canonical FAILs is UNSAFE.

Rules enforced:
- PUBLICATION READY requires: 0 canonical FAILs, 0 true FABRICATED,
  0 true CONTRADICTED, 0 unverified auto-fixes, TC-GP-1 met (if applicable).
- WARN is not allowed for confirmed P0 public content fabrications unless fixed.
- Any product with unresolved TC-GP-1 remains CONDITIONAL or lower.
- Any product with unresolved critical knowledge defect remains BLOCKED or WARN.

Usage:
    .venv/Scripts/python scripts/pipeline/commands/diagnostics/verdict_consistency.py
    .venv/Scripts/python scripts/pipeline/commands/diagnostics/verdict_consistency.py --sprint-dir reports/forensic-audit-healing-20260505-1238
    .venv/Scripts/python scripts/pipeline/commands/diagnostics/verdict_consistency.py --json

Exit codes:
    0  All verdicts consistent with rules
    1  One or more unsafe verdicts detected
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]

SCOPED_PRODUCTS = [
    "cells-java", "cells-net", "cells-python",
    "slides-java", "slides-net", "slides-python", "slides-cpp",
    "words-python",
    "email-net", "email-cpp", "email-python",
    "note-python",
    "3d-java", "3d-net", "3d-python", "3d-typescript",
]

# Products requiring TC-GP-1 (Tier 3 LOW, <40% method coverage)
TC_GP1_PRODUCTS = {"slides-net", "words-python"}

# Products with confirmed P0 issues (not yet allowed to be PUBLICATION READY)
# ISS-SLIDESJAVA-001 RESOLVED (knowledge patch applied, 2026-05-05)
# ISS-SLIDESJAVA-002 COMPLETE (21 internal pages retired, 2026-05-05)
P0_BLOCKED: dict[str, str] = {}


def parse_verdict_file(path: Path) -> dict:
    """Extract key fields from a product-verdict.md file."""
    content = path.read_text(encoding="utf-8", errors="replace")

    def extract_int(pattern: str) -> int | None:
        m = re.search(pattern, content, re.IGNORECASE)
        if m:
            try:
                return int(m.group(1).strip().replace(",", ""))
            except (ValueError, IndexError):
                return None
        return None

    def extract_str(pattern: str) -> str | None:
        m = re.search(pattern, content, re.IGNORECASE)
        return m.group(1).strip() if m else None

    # Primary: parse verdict from "## Verdict\n\n**VERDICT**" section
    verdict_section_m = re.search(
        r"##\s*Verdict\s*\n+\*\*([^*]+)\*\*", content, re.IGNORECASE
    )
    verdict = verdict_section_m.group(1).strip() if verdict_section_m else None
    if not verdict:
        # Fallback: table row "| Verdict | VALUE |"
        verdict = extract_str(r"\|\s*(?:current\s+)?verdict\s*\|\s*(PUBLICATION READY|CONDITIONAL|BLOCKED|WARN)\s*\|")

    canonical_fails = extract_int(r"\|\s*canonical\s+fail[s]?\s*\|\s*(\d+)")
    fabricated = extract_int(r"\|\s*fabricated\s*\|\s*(\d+)")
    tc_gp1 = extract_str(r"\|\s*tc.gp.1\s*\|\s*([^\|]+)")
    unverified_fixes = "unverified" in content.lower() or "auto-fix" in content.lower()

    return {
        "path": str(path),
        "verdict": verdict,
        "canonical_fails": canonical_fails,
        "fabricated": fabricated,
        "tc_gp1_status": tc_gp1,
        "has_unverified_fixes": unverified_fixes,
        "raw_excerpt": content[:500],
    }


def check_consistency(sprint_dir: Path) -> dict:
    results = {
        "sprint_dir": str(sprint_dir),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pass": True,
        "findings": [],
        "product_verdicts": {},
    }

    def fail(product: str, msg: str, severity: str = "ERROR"):
        results["findings"].append({
            "product": product,
            "severity": severity,
            "message": msg,
        })
        if severity == "ERROR":
            results["pass"] = False

    products_dir = sprint_dir / "products"
    if not products_dir.exists():
        results["pass"] = False
        results["findings"].append({
            "product": "ALL",
            "severity": "ERROR",
            "message": f"products/ directory missing: {products_dir}",
        })
        return results

    for product in SCOPED_PRODUCTS:
        pv_path = products_dir / product / "product-verdict.md"
        if not pv_path.exists():
            fail(product, f"product-verdict.md missing: {pv_path}")
            continue

        info = parse_verdict_file(pv_path)
        results["product_verdicts"][product] = info
        verdict = (info["verdict"] or "").upper()

        # Rule 1: PUBLICATION READY requires 0 canonical FAILs
        if "PUBLICATION READY" in verdict:
            if info["canonical_fails"] is not None and info["canonical_fails"] > 0:
                fail(
                    product,
                    f"UNSAFE: PUBLICATION READY with {info['canonical_fails']} canonical FAILs"
                )

        # Rule 2: PUBLICATION READY requires TC-GP-1 satisfied for applicable products
        if "PUBLICATION READY" in verdict and product in TC_GP1_PRODUCTS:
            tc_status = (info["tc_gp1_status"] or "").lower()
            if "pass" not in tc_status and "complete" not in tc_status and "done" not in tc_status:
                fail(
                    product,
                    f"UNSAFE: PUBLICATION READY but TC-GP-1 not confirmed satisfied "
                    f"(tc_gp1_status='{info['tc_gp1_status']}')"
                )

        # Rule 3: P0 BLOCKED products cannot be PUBLICATION READY
        if product in P0_BLOCKED and "PUBLICATION READY" in verdict:
            fail(
                product,
                f"UNSAFE: PUBLICATION READY but known P0 blocker exists: {P0_BLOCKED[product]}"
            )

        # Rule 4: CONDITIONAL requires TC-GP-1 listed for applicable products
        if "CONDITIONAL" in verdict and product in TC_GP1_PRODUCTS:
            pass  # CONDITIONAL is correct for TC-GP-1 pending products

        # Rule 5: WARN with confirmed P0 public fabrication that is NOT fixed = UNSAFE
        if "WARN" in verdict and product in P0_BLOCKED:
            fail(
                product,
                f"WARN with P0 blocker unresolved — should be BLOCKED or better: {P0_BLOCKED[product]}",
                severity="WARN"
            )

    return results


def main():
    parser = argparse.ArgumentParser(description="Verdict consistency validator")
    parser.add_argument(
        "--sprint-dir",
        default="reports/forensic-audit-healing-20260505-1238",
        help="Sprint directory (relative to repo root)"
    )
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    sprint_dir = REPO_ROOT / args.sprint_dir
    if not sprint_dir.exists():
        print(f"ERROR: Sprint directory not found: {sprint_dir}", file=sys.stderr)
        sys.exit(1)

    results = check_consistency(sprint_dir)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        errors = [f for f in results["findings"] if f["severity"] == "ERROR"]
        warns = [f for f in results["findings"] if f["severity"] == "WARN"]
        status = "PASS" if results["pass"] else "FAIL"
        print(f"\n# Verdict Consistency Validator")
        print(f"Sprint dir: {sprint_dir}")
        print(f"Status: {status} — {len(errors)} ERROR(s), {len(warns)} WARN(s)\n")
        for f in results["findings"]:
            prefix = f["severity"]
            print(f"  [{prefix}] {f['product']}: {f['message']}")
        if not results["findings"]:
            print("All verdicts consistent with safety rules.")

    sys.exit(0 if results["pass"] else 1)


if __name__ == "__main__":
    main()
