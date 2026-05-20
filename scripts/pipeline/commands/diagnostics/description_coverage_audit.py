# Adapted from aspose.org
# CONTRACT: scripts/pipeline/commands/diagnostics/description_coverage_audit.py
#   purpose: per-product member-doc description coverage audit against ERC api-kind claims
#   inputs: knowledge/{family}/{platform}/merged/claims.json + api_surface.json (all products)
#   outputs: stdout coverage table + knowledge/description_coverage_report.json
#   exit code: 0 = all products pass threshold; 1 = one or more products below threshold or skipped
#   idempotent: yes — read-only scan; report file overwritten on each run

"""description_coverage_audit.py — Per-product member-doc description coverage report.

Scans knowledge/{family}/{platform}/merged/claims.json and api_surface.json for
each registered product, counts ERC api-kind member-doc claims vs total public
members, and emits a per-product coverage table to stdout plus a JSON report.

The JSON report is written to knowledge/description_coverage_report.json by default.
Exit code 1 if any product is below the minimum threshold (--min-coverage, default 20%).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

KNOWLEDGE_ROOT = Path(os.environ.get("FOSS_KNOWLEDGE_ROOT", "knowledge"))

_LOAD_WARNINGS: list[str] = []

_MEMBER_PREFIX_RE = re.compile(
    r"^(?:The |Calling )?([A-Za-z]\w+)\.([A-Za-z_]\w*)\b"
)


def _load_json(path: Path) -> list | dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _LOAD_WARNINGS.append(f"JSON parse error in {path}: {exc}")
        return None
    except OSError as exc:
        _LOAD_WARNINGS.append(f"Cannot read {path}: {exc}")
        return None


def _count_public_members(api_surface: list[dict]) -> int:
    """Count total public methods + properties + enum_members across all classes."""
    total = 0
    for cls in api_surface:
        for m in cls.get("methods", []):
            if isinstance(m, dict) and not m.get("is_constructor"):
                total += 1
        for p in cls.get("properties", []):
            total += 1
        for e in cls.get("enum_members", []):
            total += 1
    return total


def _count_erc_member_claims(claims: list[dict]) -> int:
    """Count ERC api-kind claims matching the ClassName.MemberName pattern."""
    count = 0
    for claim in claims:
        if not claim.get("claim_id", "").startswith("ERC-"):
            continue
        if claim.get("kind", "") != "api":
            continue
        text = (claim.get("text") or "").strip().lstrip("`")
        if _MEMBER_PREFIX_RE.match(text):
            count += 1
    return count


def audit(min_coverage: float = 0.20) -> tuple[list[dict], bool, list[str]]:
    """Run coverage audit across all products."""
    rows: list[dict] = []
    all_pass = True
    skipped: list[str] = []

    for family_dir in sorted(KNOWLEDGE_ROOT.iterdir()):
        if not family_dir.is_dir():
            continue
        family = family_dir.name
        for platform_dir in sorted(family_dir.iterdir()):
            if not platform_dir.is_dir():
                continue
            platform = platform_dir.name
            merged = platform_dir / "merged"

            claims_data = _load_json(merged / "claims.json")
            surface_data = _load_json(merged / "api_surface.json")

            if claims_data is None or surface_data is None:
                skipped.append(f"{family}/{platform}")
                continue

            if not isinstance(claims_data, list):
                continue
            classes = surface_data if isinstance(surface_data, list) else surface_data.get("classes", [])

            total_members = _count_public_members(classes)
            erc_claims = _count_erc_member_claims(claims_data)
            coverage = erc_claims / total_members if total_members > 0 else 0.0
            meets_threshold = coverage >= min_coverage

            if not meets_threshold:
                all_pass = False

            rows.append({
                "family": family,
                "platform": platform,
                "total_members": total_members,
                "erc_member_claims": erc_claims,
                "coverage_pct": round(coverage * 100, 1),
                "meets_threshold": meets_threshold,
            })

    return rows, all_pass, skipped


def _print_table(rows: list[dict], min_coverage: float) -> None:
    print(f"\n{'Product':<25} {'Members':>8} {'ERC Claims':>11} {'Coverage':>9} {'Status':>7}")
    print("-" * 66)
    for r in rows:
        product = f"{r['family']}/{r['platform']}"
        status = "OK" if r["meets_threshold"] else "LOW"
        print(
            f"{product:<25} {r['total_members']:>8} {r['erc_member_claims']:>11} "
            f"{r['coverage_pct']:>8.1f}% {status:>7}"
        )
    total_members = sum(r["total_members"] for r in rows)
    total_claims = sum(r["erc_member_claims"] for r in rows)
    total_pct = 100.0 * total_claims / total_members if total_members else 0.0
    print("-" * 66)
    print(f"{'TOTAL':<25} {total_members:>8} {total_claims:>11} {total_pct:>8.1f}%")
    failing = [r for r in rows if not r["meets_threshold"]]
    if failing:
        print(f"\n  Products below {min_coverage*100:.0f}% threshold:")
        for r in failing:
            print(f"    {r['family']}/{r['platform']}: {r['coverage_pct']}%")
    else:
        print(f"\n  All products meet the {min_coverage*100:.0f}% threshold.")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit member-doc description coverage across all products."
    )
    parser.add_argument(
        "--report",
        default=str(KNOWLEDGE_ROOT / "description_coverage_report.json"),
        help="Path to write JSON report (default: knowledge/description_coverage_report.json)",
    )
    parser.add_argument(
        "--min-coverage",
        type=float,
        default=20.0,
        metavar="PCT",
        help="Minimum ERC member-doc coverage %% per product (default: 20)",
    )
    args = parser.parse_args()

    min_cov = args.min_coverage / 100.0
    rows, all_pass, skipped = audit(min_coverage=min_cov)

    _print_table(rows, min_cov)

    if _LOAD_WARNINGS:
        for w in _LOAD_WARNINGS:
            print(f"  WARNING: {w}", file=sys.stderr)

    if skipped:
        print(f"\n  SKIPPED (missing/malformed data): {', '.join(skipped)}", file=sys.stderr)

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "min_coverage_threshold_pct": args.min_coverage,
        "all_pass": all_pass,
        "products": rows,
        "skipped_products": skipped,
        "warnings": _LOAD_WARNINGS,
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Report written to {report_path}")

    if not all_pass or skipped:
        sys.exit(1)


if __name__ == "__main__":
    main()
