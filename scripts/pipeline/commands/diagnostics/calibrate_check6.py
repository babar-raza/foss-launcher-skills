#!/usr/bin/env python3
"""Calibration scan for Check 6 (static/abstract class instantiation).

Scans all content pages for a given family/platform through the
TypeAccuracyEvaluator and reports any TA-category findings.  Writes
results to ``reports/calibration/check6-{family}-{platform}.json``.

Usage:
    PYTHONPATH=scripts/pipeline python scripts/pipeline/commands/diagnostics/calibrate_check6.py pdf net
    PYTHONPATH=scripts/pipeline python scripts/pipeline/commands/diagnostics/calibrate_check6.py --all
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Products with C#/Java knowledge that Check 6 applies to
# ---------------------------------------------------------------------------
CSHARP_JAVA_PRODUCTS = [
    ("3d", "net"), ("cells", "net"), ("email", "net"),
    ("pdf", "net"), ("slides", "net"),
    ("3d", "java"), ("cells", "java"), ("pdf", "java"),
    ("slides", "java"),
]

REPORT_DIR = Path("reports/calibration")


def _scan_product(family: str, platform: str) -> dict:
    """Scan all content pages for one product.  Returns a result dict."""
    from content_eval.evaluators.type_accuracy import TypeAccuracyEvaluator
    from content_eval.models import Page

    ev = TypeAccuracyEvaluator()

    # Discover content pages across all subdomains
    content_root = Path("content")
    pages_scanned = 0
    ta_findings: list[dict] = []
    errors: list[str] = []

    for subdir in sorted(content_root.iterdir()):
        if not subdir.is_dir():
            continue
        product_dir = subdir / "en" / family / platform
        if not product_dir.is_dir():
            continue
        for md in sorted(product_dir.rglob("*.md")):
            try:
                page = Page.load(md)
                if page is None:
                    continue
            except Exception as exc:
                errors.append(f"{md}: load error: {exc}")
                continue

            try:
                findings = ev.evaluate(page, None)
            except Exception as exc:
                errors.append(f"{md}: evaluate error: {exc}")
                continue

            pages_scanned += 1
            for f in findings:
                cat = getattr(f, "category", "")
                if cat == "TA":
                    ta_findings.append({
                        "file": str(md),
                        "line": f.line_no,
                        "level": f.level,
                        "message": f.message,
                    })

    return {
        "family": family,
        "platform": platform,
        "scan_date": datetime.now(timezone.utc).isoformat(),
        "pages_scanned": pages_scanned,
        "ta_finding_count": len(ta_findings),
        "ta_findings": ta_findings,
        "error_count": len(errors),
        "errors": errors[:20],  # cap to avoid huge reports
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="calibrate_check6",
        description="Calibration scan for type-accuracy Check 6.",
    )
    parser.add_argument("family", nargs="?", help="Product family (e.g. pdf)")
    parser.add_argument("platform", nargs="?", help="Platform (e.g. net)")
    parser.add_argument("--all", action="store_true",
                        help="Scan all 9 C#/Java products")
    args = parser.parse_args(argv)

    if args.all:
        products = CSHARP_JAVA_PRODUCTS
    elif args.family and args.platform:
        products = [(args.family, args.platform)]
    else:
        parser.error("Provide family and platform, or --all")
        return 1

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    total_pages = 0
    total_findings = 0

    for family, platform in products:
        print(f"Scanning {family}/{platform}...", end=" ", flush=True)
        result = _scan_product(family, platform)
        total_pages += result["pages_scanned"]
        total_findings += result["ta_finding_count"]

        report_path = REPORT_DIR / f"check6-{family}-{platform}.json"
        report_path.write_text(
            json.dumps(result, indent=2), encoding="utf-8"
        )
        print(
            f"{result['pages_scanned']} pages, "
            f"{result['ta_finding_count']} TA findings"
            + (f", {result['error_count']} errors" if result['error_count'] else "")
        )

    # Write summary
    summary = {
        "scan_date": datetime.now(timezone.utc).isoformat(),
        "products_scanned": len(products),
        "total_pages": total_pages,
        "total_ta_findings": total_findings,
    }
    (REPORT_DIR / "check6-summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(f"\nSummary: {total_pages} pages, {total_findings} TA findings")
    print(f"Reports: {REPORT_DIR.resolve()}")

    return 0 if total_findings == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
