"""
SEO-SCHEMA-A-QUARANTINE-STALE-ENTRIES quarantine_stale_entries.py
===================================================================
Consumes audit_schema_a.py's report (reports/seo/schema_a_stale_audit.json)
and moves only the "drifted_title_mismatch" orphans -- entries whose family
HAS launched content today, but whose specific pageTitle matches nothing
currently on disk -- into keywords/_stale/{family}.json.

"prospective_no_launched_content" orphans (the family has zero launched
pages at all) are deliberately left untouched in the live keywords/{family}.json.
These are exactly the signal the mission's own Context section names as
"Schema A's only keyword signal" for stub-tier families (cad, imaging, ocr,
psd, tasks, zip) -- quarantining them would destroy the one piece of
legitimate demand signal those families have, not clean up dead data. This
is a deliberate refinement of the plan's original coarser "quarantine
everything flagged" framing, based on what the audit actually found: 341 of
731 orphan candidates are prospective, not stale, and moving them out of the
normal read path would be a regression, not a cleanup.

Quarantined entries are appended (not overwritten) to keywords/_stale/{family}.json,
deduplicated by (pageTitle, tuple(sorted(keywords))) against whatever is
already quarantined there, so re-running this script after a later audit
never double-quarantines the same entry.

Safety: --dry-run by default (prints what WOULD move, changes nothing).
Pass --execute to actually mutate keywords/*.json and keywords/_stale/*.json.

No LLM calls. No network calls. stdlib + pathlib only.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
KEYWORDS_DIR = REPO_ROOT / "keywords"
STALE_DIR = KEYWORDS_DIR / "_stale"
REPORTS_DIR = REPO_ROOT / "reports" / "seo"
AUDIT_REPORT_PATH = REPORTS_DIR / "schema_a_stale_audit.json"


def _entry_key(entry: dict) -> tuple:
    return (entry.get("pageTitle"), tuple(sorted(entry.get("keywords", []))))


def plan_quarantine(audit_report: dict) -> dict[str, list[int]]:
    """Return {family: [entry_index, ...]} for indices to quarantine.

    Only drifted_title_mismatch families contribute indices; prospective
    families are never included.
    """
    plan: dict[str, list[int]] = {}
    for fam in audit_report.get("families", []):
        if fam.get("orphan_classification") != "drifted_title_mismatch":
            continue
        indices = [o["index"] for o in fam.get("orphans", [])]
        if indices:
            plan[fam["family"]] = indices
    return plan


def apply_quarantine(family: str, indices: list[int], execute: bool) -> dict:
    """Move `indices` from keywords/{family}.json to keywords/_stale/{family}.json.

    Returns a summary dict. When execute=False, computes and returns the
    same summary without writing anything.
    """
    live_path = KEYWORDS_DIR / f"{family}.json"
    stale_path = STALE_DIR / f"{family}.json"

    live_data = json.loads(live_path.read_text(encoding="utf-8"))
    index_set = set(indices)
    to_quarantine = [e for i, e in enumerate(live_data) if i in index_set]
    remaining = [e for i, e in enumerate(live_data) if i not in index_set]

    existing_stale = []
    if stale_path.exists():
        existing_stale = json.loads(stale_path.read_text(encoding="utf-8"))
    seen = {_entry_key(e) for e in existing_stale}
    newly_added = [e for e in to_quarantine if _entry_key(e) not in seen]
    skipped_dupe = len(to_quarantine) - len(newly_added)
    merged_stale = existing_stale + newly_added

    summary = {
        "family": family,
        "moved": len(to_quarantine),
        "newly_added_to_stale": len(newly_added),
        "already_quarantined_skipped": skipped_dupe,
        "remaining_live": len(remaining),
    }

    if execute:
        STALE_DIR.mkdir(parents=True, exist_ok=True)
        live_path.write_text(json.dumps(remaining, indent=4, ensure_ascii=False), encoding="utf-8")
        stale_path.write_text(json.dumps(merged_stale, indent=4, ensure_ascii=False), encoding="utf-8")

    return summary


def run(audit_report: dict, execute: bool) -> list[dict]:
    plan = plan_quarantine(audit_report)
    return [apply_quarantine(family, indices, execute) for family, indices in sorted(plan.items())]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--execute", action="store_true", help="Actually mutate keywords/*.json (default: dry-run)")
    args = parser.parse_args()

    if not AUDIT_REPORT_PATH.exists():
        raise SystemExit(f"Missing {AUDIT_REPORT_PATH} -- run audit_schema_a.py first")
    audit_report = json.loads(AUDIT_REPORT_PATH.read_text(encoding="utf-8"))

    summaries = run(audit_report, execute=args.execute)

    mode = "EXECUTE" if args.execute else "DRY-RUN"
    print(f"=== Schema A Quarantine ({mode}) ===")
    total_moved = 0
    for s in summaries:
        print(
            f"  {s['family']:<12} moved={s['moved']:>4}  "
            f"new_to_stale={s['newly_added_to_stale']:>4}  "
            f"dupe_skipped={s['already_quarantined_skipped']:>3}  "
            f"remaining_live={s['remaining_live']:>4}"
        )
        total_moved += s["moved"]
    print(f"\nTotal entries moved: {total_moved}")
    if not args.execute:
        print("(dry-run -- pass --execute to actually write changes)")


if __name__ == "__main__":
    main()
