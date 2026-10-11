#!/usr/bin/env python3
"""
backlog_reconcile.py — cross-check backlog/BACKLOG.md's Cat=knowledge rows
against the durable data/knowledge_state.json projection.

CONTRACT: scripts/pipeline/commands/ops/backlog_reconcile.py
  purpose: MT030-2026-08-13's deep assessment on PDF-JAVA-REFRESH-003 found that
           backlog rows had no programmatic link back to pipeline state at all --
           closure was a pure hand-edit an agent had to remember to keep current.
           This tool is the read-only advisory half of the fix (the enforcement
           half is scripts/ci/checks/check_backlog_reconciliation_gate.py, wired
           into scripts/pre-commit-audit.sh as Step 32). Both consume the same
           reconcile_row() decision function so the advisory report and the
           blocking gate can never silently diverge in what they consider "stale".
  inputs:  backlog/BACKLOG.md (via backlog_parser), data/knowledge_state.json
           (via knowledge_state.read_state)
  outputs: reports/discovery/backlog_reconciliation.json (ephemeral, same tier as
           S-94's sweep_report.json -- advisory output, not a source of truth)
  idempotent: yes (pure read + report; --report-only never mutates anything)

Usage::
    .venv/Scripts/python scripts/pipeline/commands/ops/backlog_reconcile.py
    .venv/Scripts/python scripts/pipeline/commands/ops/backlog_reconcile.py --report-only
    .venv/Scripts/python scripts/pipeline/commands/ops/backlog_reconcile.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
_PIPELINE_LIB_DIR = _REPO_ROOT / "scripts" / "pipeline" / "lib"
if str(_PIPELINE_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_LIB_DIR))

from backlog_parser import parse_backlog_file, extract_product_key  # noqa: E402
from knowledge_state import read_state  # noqa: E402

BACKLOG_PATH = _REPO_ROOT / "backlog" / "BACKLOG.md"
REPORT_PATH = _REPO_ROOT / "reports" / "discovery" / "backlog_reconciliation.json"

# Statuses that mean "this row claims the underlying work is done".
_CLOSED_STATUSES = {"CLOSED", "CLOSED/INVALID", "ACCEPTED", "ACCEPTED_CEILING"}


def reconcile_row(row: dict, state: "dict | None") -> dict:
    """Decide one Cat=knowledge row's reconciliation disposition.

    Returns a dict: {id, product_key, disposition, reason}. `disposition` is one
    of: "insufficient_data" (fail-open — no knowledge_state entry yet, never
    punish a product nothing has recorded), "ok" (nothing to flag), or
    "stale_closure" (row claims CLOSED but knowledge_state shows no clean,
    on-record truth-audit for it — the exact PDF-JAVA-REFRESH-003 pattern).

    Pure decision logic, no I/O — shared by the advisory report (this module's
    main()) and the enforcement gate (check_backlog_reconciliation_gate.py) so
    they can never silently diverge on what counts as stale.
    """
    row_id = row.get("id", "")
    title = row.get("title", "")
    status = (row.get("status") or "").upper().strip()
    product_key = extract_product_key(title)

    if product_key is None:
        return {
            "id": row_id, "product_key": None, "disposition": "unresolvable_product",
            "reason": "Title does not start with a recognizable family/platform key",
        }

    if state is None:
        return {
            "id": row_id, "product_key": product_key, "disposition": "insufficient_data",
            "reason": (
                f"No data/knowledge_state.json entry for {product_key} yet "
                "-- nothing recorded, not a red flag"
            ),
        }

    is_claimed_closed = any(s in status for s in _CLOSED_STATUSES)
    if not is_claimed_closed:
        return {
            "id": row_id, "product_key": product_key, "disposition": "ok",
            "reason": f"Row status '{status}' does not claim closure",
        }

    truth_audit = state.get("truth_audit")
    if truth_audit is None:
        return {
            "id": row_id, "product_key": product_key, "disposition": "stale_closure",
            "reason": (
                f"{row_id} claims closure but knowledge_state has no truth-audit "
                f"record for {product_key} at all"
            ),
        }
    if truth_audit.get("verdict") != "PASS":
        return {
            "id": row_id, "product_key": product_key, "disposition": "stale_closure",
            "reason": (
                f"{row_id} claims closure but the last recorded truth-audit for "
                f"{product_key} is {truth_audit.get('verdict')} "
                f"(fail_count={truth_audit.get('fail_count')}), "
                f"report: {truth_audit.get('report_path')}"
            ),
        }
    return {
        "id": row_id, "product_key": product_key, "disposition": "ok",
        "reason": f"Closure confirmed: truth-audit PASS on record for {product_key}",
    }


def reconcile(backlog_path: "Path | str" = BACKLOG_PATH) -> list[dict]:
    """Reconcile every Cat=knowledge row in Active+Queued against knowledge_state."""
    rows = parse_backlog_file(backlog_path)
    results = []
    for row in rows:
        if (row.get("cat") or "").strip().lower() != "knowledge":
            continue
        product_key = extract_product_key(row.get("title", ""))
        state = None
        if product_key is not None:
            family, platform = product_key.split("/", 1)
            state = read_state(family, platform)
        results.append(reconcile_row(row, state))
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-only", action="store_true",
                        help="Print findings, write the report, never affects exit code beyond 0")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of a text summary")
    parser.add_argument("--backlog", default=str(BACKLOG_PATH), help="Path to BACKLOG.md")
    args = parser.parse_args(argv)

    results = reconcile(args.backlog)
    stale = [r for r in results if r["disposition"] == "stale_closure"]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps({"results": results, "stale_count": len(stale)}, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps({"results": results, "stale_count": len(stale)}, indent=2))
    else:
        print(f"backlog_reconcile: {len(results)} Cat=knowledge row(s) checked, {len(stale)} stale_closure finding(s)")
        for r in stale:
            print(f"  [{r['id']}] {r['reason']}")

    return 0  # always advisory from the CLI; the commit-time gate makes its own decision


if __name__ == "__main__":
    raise SystemExit(main())
