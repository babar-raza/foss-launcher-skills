"""CI gate: block on newly-introduced backlink compliance violations beyond
a committed baseline (TC14, backlink-governance-redesign).

Ratchet pattern, mirroring check_audit_regression.py's own mechanics: never
allowed to get worse, allowed to improve. The repo currently carries a
known, uncorrected backlog of non-compliant pages (pending TC15's staged
backfill) -- this gate's job is to stop that backlog from silently growing
via the scheduled full-site audit, not to demand it be zero immediately.

Usage:
    python scripts/ci/checks/check_backlink_regression.py <backlink-audit.json> <baseline-compliance-counts.json>

Exit codes:
    0 — no regressions (all per-family blocking-status counts are within baseline)
    1 — regression detected (one or more families have more blocking-status
        records than baseline)
    2 — usage error, missing file, or malformed/empty input

The baseline file (reports/backlinks/baseline-compliance-counts.json) documents
known pre-existing violation counts per family. Update it by hand only when a
regression is deliberately accepted, or after TC15's backfill genuinely
reduces the count (never auto-updated).
"""
import json
import sys
from pathlib import Path

# The same "confidently wrong" statuses check_backlink_compliance.py blocks
# on -- MISSING/SKIPPED/FAMILY_FALLBACK/COMPLIANT are deliberately excluded
# (see that script's own module docstring for why).
BLOCKING_KEYS = (
    "wrong_target", "over_limit", "blocked_target",
    "wrong_anchor_text", "duplicate_link", "duplicate_subdomain",
)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    if len(sys.argv) < 3:
        print(
            "Usage: check_backlink_regression.py <backlink-audit.json> <baseline-compliance-counts.json>",
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
        # backlink_audit.py writes its JSON report only once, after the
        # whole scan completes (build_report() is the sole write) -- an
        # empty file means the tool crashed before finishing, never that
        # zero content was scanned. Mirrors check_audit_regression.py's own
        # guard against a false-green PR gate from a silently crashed tool.
        print(
            f"ERROR: {current_path} is empty. This means backlink_audit.py crashed "
            "before completing its run -- not that zero files were audited. "
            "Treating this as a failure.",
            file=sys.stderr,
        )
        return 2

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

    by_family = current.get("by_family", {})
    current_counts: dict[str, int] = {
        family: sum(counts.get(key, 0) for key in BLOCKING_KEYS)
        for family, counts in by_family.items()
    }

    regressions: list[str] = []
    for family, count in current_counts.items():
        baseline_entry = baseline.get(family, {})
        if isinstance(baseline_entry, dict):
            baseline_count = baseline_entry.get("count", 0)
        elif isinstance(baseline_entry, int):
            baseline_count = baseline_entry
        else:
            baseline_count = 0

        if count > baseline_count:
            delta = count - baseline_count
            reason = baseline_entry.get("reason", "not documented") if isinstance(baseline_entry, dict) else "not documented"
            regressions.append(
                f"  {family}: {count} violations (baseline: {baseline_count}, +{delta} new) [{reason}]"
            )

    total_current = sum(current_counts.values())
    total_baselined = sum(
        (v.get("count", 0) if isinstance(v, dict) else v)
        for k, v in baseline.items()
        if not k.startswith("_") and k in current_counts
    )

    if regressions:
        print(
            "BACKLINK COMPLIANCE REGRESSION DETECTED — new violations introduced beyond baseline:",
            file=sys.stderr,
        )
        for r in regressions:
            print(r, file=sys.stderr)
        print(f"\nBaseline reference: {baseline_path}", file=sys.stderr)
        print(
            "To accept new violations as known, update baseline-compliance-counts.json "
            "and document the reason. To fix them for real, run backlink_backfill.py.",
            file=sys.stderr,
        )
        return 1

    print(
        f"OK: No backlink compliance regressions. "
        f"{total_current} total violations across "
        f"{len([f for f, c in current_counts.items() if c > 0])} families "
        f"(all within baseline of {total_baselined})."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
