"""reconcile_content_healing_status.py — PKGINSTALL-CONTENT-HEALING-STATUS-WRITEBACK.

content_healing_status (data/package_registry.json, per (family, platform))
is real, actively-written state -- package_publish_watch.py::apply_proposal()
sets it to "pending" the moment a package flips to published with content
healing owed -- but nothing has ever computed the OTHER half of that
lifecycle: "the pending content healing is actually done now." Confirmed
live 2026-09-10: 13 of 18 tracked entries still show "pending", several
dated back to 2026-08-01, with zero mechanism anywhere that could ever flip
one to "healed" even after a product's literal-mention count genuinely
reaches zero.

This module closes that gap using ReconciliationStore's own per-page rows
(reports/package-reconciliation/inventory.jsonl, PKGINSTALL-RECONCILIATION-
STORE) as the evidence source: a product is proposed for pending->healed
only when the store has at least one row for it (never treat "we have never
swept this product" as "zero findings" -- that would be a false-positive
healed status, worse than the stale-pending status this module exists to
fix) AND every one of its latest-known rows shows finding_count_literal == 0.

--dry-run (the default) only ever REPORTS a proposed transition; it never
writes data/package_registry.json. A real (non-dry-run) write is refused
loudly unless PKGINSTALL-DEPLOY-TRIGGER-3LAYER-FIX has reached CLOSED in the
live MT066 taskcard store -- content_healing_status lives inside a
Hugo-consumed file, and this mission's own plan-repair review already
flagged the daily-spurious-full-portfolio-rebuild risk of writing
observation-derived fields there before that deploy-trigger fix lands (see
governing plan section R.3.1). This guard is not a placeholder: as of
2026-09-10 that taskcard is READY, not CLOSED, so real writes are refused
today by design, not by omission.

CLI:
    PYTHONPATH=scripts/pipeline python scripts/pipeline/commands/ops/reconcile_content_healing_status.py
        (dry-run report, the default -- no flag needed)
    PYTHONPATH=scripts/pipeline python scripts/pipeline/commands/ops/reconcile_content_healing_status.py --execute
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_PIPELINE_ROOT = _HERE.parents[1]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = _PIPELINE_ROOT / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from package_registry_data import (  # noqa: E402
    default_registry_path, load_registry, validate_package_registry, set_content_healing_status,
)
from reconciliation_store import ReconciliationStore  # noqa: E402
from taskcard_store import TaskcardStore  # noqa: E402

MISSION_ID = "MT066-2026-09-09-PACKAGE-INSTALL-RECONCILIATION"
GATING_TASK_ID = "PKGINSTALL-DEPLOY-TRIGGER-3LAYER-FIX"

_DEFAULT_REPO_ROOT = _PIPELINE_ROOT.parents[1]
REPO_ROOT = _DEFAULT_REPO_ROOT
REGISTRY_PATH = default_registry_path()


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing."""
    global REPO_ROOT, REGISTRY_PATH
    REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    REGISTRY_PATH = REPO_ROOT / "data" / "package_registry.json"


class DeployTriggerNotClosedError(Exception):
    """Raised when a non-dry-run reconciliation is attempted while
    PKGINSTALL-DEPLOY-TRIGGER-3LAYER-FIX has not reached CLOSED."""


def compute_transition(
    family: str, platform: str, *, store: ReconciliationStore,
) -> "dict[str, Any] | None":
    """Return a proposed transition dict, or None if none is warranted.

    None covers 3 distinct cases, deliberately not distinguished in the
    return value (the caller only needs "nothing to propose"): no
    reconciliation-store rows exist for this product at all (insufficient
    data -- never inferred as zero findings), at least one row still shows
    a nonzero literal-finding count, or the rows found belong to a stale
    sweep that no longer reflects any real page (still counted as "not
    ready" -- a future, more precise pass can refine this once
    PKGINSTALL-DEFECT-SWEEP-REDESIGN's real sweep data exists at scale).
    """
    rows = store.read_latest_for_product(family, platform)
    if not rows:
        return None
    total_literal = sum((row.get("finding_count_literal") or 0) for row in rows.values())
    if total_literal > 0:
        return None
    return {
        "family": family,
        "platform": platform,
        "from_status": "pending",
        "to_status": "healed",
        "evidence_row_count": len(rows),
        "evidence_paths": sorted(rows.keys()),
    }


def _deploy_trigger_is_closed(*, taskcard_store: "TaskcardStore | None" = None) -> bool:
    store = taskcard_store or TaskcardStore(MISSION_ID, repo_root=REPO_ROOT)
    card = store.get(GATING_TASK_ID)
    return bool(card) and card.get("status") == "CLOSED"


def find_pending_transitions(
    data: dict[str, Any], *, store: "ReconciliationStore | None" = None,
) -> list[dict[str, Any]]:
    """Scan every entry currently content_healing_status == 'pending' and
    return the subset with a real, evidence-backed proposed transition."""
    store = store or ReconciliationStore(repo_root=REPO_ROOT)
    proposals: list[dict[str, Any]] = []
    for family, platforms in data.items():
        if family.startswith("_") or not isinstance(platforms, dict):
            continue
        for platform, entry in platforms.items():
            if not isinstance(entry, dict):
                continue
            if entry.get("content_healing_status") != "pending":
                continue
            transition = compute_transition(family, platform, store=store)
            if transition is not None:
                proposals.append(transition)
    return proposals


def run_reconciliation(
    *, dry_run: bool = True, checked_at: "str | None" = None,
    store: "ReconciliationStore | None" = None, taskcard_store: "TaskcardStore | None" = None,
) -> dict[str, Any]:
    """Compute (and, only when dry_run=False and the deploy-trigger gate is
    CLOSED, apply) pending->healed content_healing_status transitions.

    Returns a result dict with `proposals` (always populated) and
    `wrote_changes` (always False in dry-run mode). Raises
    DeployTriggerNotClosedError if dry_run=False is requested while the
    gating taskcard has not reached CLOSED -- this is a loud refusal, never
    a silent downgrade to dry-run.
    """
    from datetime import datetime, timezone
    checked_at = checked_at or datetime.now(timezone.utc).date().isoformat()

    original_bytes = REGISTRY_PATH.read_text(encoding="utf-8")
    data = json.loads(original_bytes)

    proposals = find_pending_transitions(data, store=store)
    result: dict[str, Any] = {"proposals": proposals, "wrote_changes": False, "validation_errors": []}

    if not proposals:
        return result

    if dry_run:
        return result

    if not _deploy_trigger_is_closed(taskcard_store=taskcard_store):
        raise DeployTriggerNotClosedError(
            f"refusing to write content_healing_status transitions: {GATING_TASK_ID} has not "
            "reached CLOSED. content_healing_status lives inside data/package_registry.json, a "
            "Hugo-consumed file -- writing observation-derived fields there before the deploy-"
            "trigger 3-layer fix lands risks a daily spurious full-portfolio rebuild once that "
            "fix ships and makes this file visible to the deploy scanner (governing plan section "
            "R.3.1). Re-run with --dry-run to see the proposed transitions without writing."
        )

    for proposal in proposals:
        entry = data[proposal["family"]][proposal["platform"]]
        set_content_healing_status(
            entry, proposal["to_status"], checked_at=checked_at,
            reason=(
                f"reconcile_content_healing_status.py: {proposal['evidence_row_count']} "
                "reconciliation-store row(s), 0 remaining literal findings"
            ),
        )

    errors = validate_package_registry(data)
    if errors:
        result["validation_errors"] = errors
        return result

    new_bytes = json.dumps(data, indent=2) + "\n"
    tmp_path = REGISTRY_PATH.with_name(REGISTRY_PATH.name + ".tmp")
    tmp_path.write_text(new_bytes, encoding="utf-8")
    reparsed = json.loads(tmp_path.read_text(encoding="utf-8"))
    reparse_errors = validate_package_registry(reparsed)
    if reparse_errors:
        tmp_path.unlink(missing_ok=True)
        result["validation_errors"] = reparse_errors
        return result
    os.replace(tmp_path, REGISTRY_PATH)
    final_errors = validate_package_registry(json.loads(REGISTRY_PATH.read_text(encoding="utf-8")))
    if final_errors:
        result["validation_errors"] = final_errors
        return result

    result["wrote_changes"] = True
    return result


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Apply transitions (default: dry-run report only)")
    args = parser.parse_args(argv)

    try:
        result = run_reconciliation(dry_run=not args.execute)
    except DeployTriggerNotClosedError as exc:
        print(f"REFUSED: {exc}")
        return 1

    if not result["proposals"]:
        print("No pending->healed transitions proposed (no product both has reconciliation-store "
              "evidence and zero remaining literal findings).")
        return 0

    for p in result["proposals"]:
        print(
            f"{'APPLIED' if result['wrote_changes'] else 'PROPOSED'}: "
            f"{p['family']}/{p['platform']}: pending -> healed "
            f"({p['evidence_row_count']} reconciliation-store row(s), 0 remaining literal findings)"
        )
    if result["validation_errors"]:
        print("VALIDATION ERRORS (not written):")
        for e in result["validation_errors"]:
            print(f"  {e}")
        return 1
    if not args.execute:
        print("(dry-run -- re-run with --execute to apply, once PKGINSTALL-DEPLOY-TRIGGER-3LAYER-FIX is CLOSED)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
