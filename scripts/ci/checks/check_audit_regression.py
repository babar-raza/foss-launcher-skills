# Adapted from aspose.org scripts/ci/checks/ for standalone use
"""CI gate: block PRs that introduce new audit FAILs beyond the committed baseline.

Usage:
    python scripts/ci/checks/check_audit_regression.py <audit-results.json> <baseline-fail-counts.json>

Exit codes:
    0 — no regressions (all FAIL counts are within baseline)
    1 — regression detected (one or more products have more FAILs than baseline)
    2 — usage error or missing file

The baseline file (reports/audit/baseline-fail-counts.json) documents known pre-existing
FAILs per product. Update it when FAILs are deliberately resolved or accepted.
"""
import json
import sys
from pathlib import Path


def main() -> int:
    # Ensure stdout uses UTF-8 on all platforms (Windows cp1252 would crash on non-ASCII)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    if len(sys.argv) < 3:
        print(
            "Usage: check_audit_regression.py <audit-results.json> <baseline-fail-counts.json>",
            file=sys.stderr,
        )
        return 2

    current_path = Path(sys.argv[1])
    baseline_path = Path(sys.argv[2])

    for p in (current_path, baseline_path):
        if not p.exists():
            print(f"ERROR: file not found: {p}", file=sys.stderr)
            return 2

    current_text = current_path.read_text(encoding="utf-8").strip()
    if not current_text:
        print("audit-results.json is empty — no files audited; no regressions possible.")
        return 0

    try:
        current = json.loads(current_text)
    except json.JSONDecodeError as e:
        print(f"ERROR: malformed JSON in {current_path}: {e}", file=sys.stderr)
        return 2

    try:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"ERROR: malformed JSON in {baseline_path}: {e}", file=sys.stderr)
        return 2

    # Build per-product FAIL counts from current audit results
    # audit-results.json findings list: each finding has level + file path
    # Products are identified from findings by extracting family/platform from the file path
    current_counts: dict[str, int] = {}
    products_checked = current.get("products_checked", [])
    findings = current.get("findings", [])

    # Tally FAILs per product using the products_checked list as the key set
    for product in products_checked:
        current_counts[product] = 0

    for finding in findings:
        if finding.get("level") != "FAIL":
            continue
        file_path = finding.get("file", "").replace("\\", "/")
        # Determine which product this file belongs to
        for product in products_checked:
            family, platform = product.split("/", 1)
            # Match against content paths like .../en/{family}/{platform}/...
            if f"/en/{family}/{platform}/" in file_path:
                current_counts[product] = current_counts.get(product, 0) + 1
                break

    # Compare against baseline
    regressions: list[str] = []
    for product, count in current_counts.items():
        baseline_entry = baseline.get(product, {})
        # Support both {"fail_count": N} and bare integer formats
        if isinstance(baseline_entry, dict):
            baseline_count = baseline_entry.get("fail_count", 0)
        elif isinstance(baseline_entry, int):
            baseline_count = baseline_entry
        else:
            baseline_count = 0

        if count > baseline_count:
            delta = count - baseline_count
            reason = baseline_entry.get("reason", "not documented") if isinstance(baseline_entry, dict) else "not documented"
            regressions.append(
                f"  {product}: {count} FAILs (baseline: {baseline_count}, +{delta} new)"
            )

    total_current = sum(current_counts.values())
    total_baselined = sum(
        (v.get("fail_count", 0) if isinstance(v, dict) else v)
        for k, v in baseline.items()
        if not k.startswith("_") and k in current_counts
    )

    if regressions:
        print(
            f"AUDIT REGRESSION DETECTED — new FAILs introduced beyond baseline:",
            file=sys.stderr,
        )
        for r in regressions:
            print(r, file=sys.stderr)
        print(
            f"\nBaseline reference: {baseline_path}",
            file=sys.stderr,
        )
        print(
            "To accept new FAILs as known, update baseline-fail-counts.json and document the reason.",
            file=sys.stderr,
        )
        return 1

    print(
        f"OK: No audit regressions. "
        f"{total_current} total FAILs across {len([p for p, c in current_counts.items() if c > 0])} products "
        f"(all within baseline of {total_baselined})."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
