"""Second seed pass: append an enriched row per existing task_id adding
rollback_or_recovery (schema 5f is append-only + last-occurrence-wins, so this
supersedes the earlier row's missing field without rewriting history). Status is
unchanged for every card -- this is field enrichment, not a state transition."""
import sys
from datetime import datetime, timezone

sys.path.insert(0, "scripts/pipeline")
from lib.taskcard_store import TaskcardStore  # noqa: E402

MISSION = "MT066-2026-09-09-PACKAGE-INSTALL-RECONCILIATION"
RECORDED_BY = "agent-session-b2a5f5f7"
NOW = datetime.now(timezone.utc).isoformat()

store = TaskcardStore(MISSION)
latest = store.read_latest()

ROLLBACK = {
    "PKGINSTALL-REPAIR-PLAN-DOCUMENT": (
        "Revert the plan-file edit directly (it lives outside git at "
        "<local-plan-cache>/plans/..., no repo state to roll back). No other "
        "artifact is written by this card."
    ),
    "PKGINSTALL-SCHEMA-ADAPTER-VERSION-EXTENSION": (
        "git revert the schema/adapter commit. This card never writes "
        "data/package_registry.json itself, so no registry-state rollback is needed "
        "-- reverting the code change is sufficient."
    ),
    "PKGINSTALL-UNIVERSAL-STATE-MACHINE-DETECTION": (
        "git revert the watcher-script commit. Detection-only card -- no registry "
        "writes to unwind."
    ),
    "PKGINSTALL-REGISTRY-AUTOAPPLY-COMMIT": (
        "A bad auto-commit is a single `git revert <sha>` against "
        "data/package_registry.json -- no cascading dependents beyond the next Hugo "
        "build's shortcode read (per plan §L). If a systemic adapter bug is "
        "suspected, disable --auto-apply first (falls back to today's issue-only "
        "behavior) before investigating, rather than reverting blind."
    ),
    "PKGINSTALL-EXECUTE-ST054-MIGRATION": (
        "Per ST-054's own sequencing rule (one product per commit, never one "
        "all-products commit): revert the single affected product's commit. Locale "
        "propagation for that product reverts with it since S-75 patches land in the "
        "same commit."
    ),
    "PKGINSTALL-PERMANENT-RECONCILIATION-LOOP": (
        "Disable the recurring-fire trigger first (falls back to ST-054's proven "
        "one-time-migration cadence, not broken, just less automated); revert any "
        "bad content commit the loop produced via git revert, same mechanics as the "
        "ST-054 migration card."
    ),
    "PKGINSTALL-DEPLOY-TRIGGER-3LAYER-FIX": (
        "Layer 3 (this repo): the verification poll is read-only -- disabling it "
        "requires no rollback, only removing its scheduled trigger. Layer 2 (sibling "
        "repo): revert the merged detect_changes.py PR in Aspose/aspose.org-workflows "
        "if the new SHARED_DATA_CONSUMERS mapping causes false-positive deploy "
        "triggers -- this is a separate repo's revert, coordinated with its own "
        "reviewers, not a unilateral agent action."
    ),
    "PKGINSTALL-OPERATIONAL-ROLLOUT-MONITORING": (
        "git revert the cadence/alerting workflow changes. If the first live cycle "
        "needs to be halted mid-run, disable the scheduled workflows via the GitHub "
        "UI (or revert the cron trigger to workflow_dispatch-only) rather than "
        "killing an in-flight run destructively."
    ),
}

for task_id, rollback_text in ROLLBACK.items():
    prior = latest.get(task_id)
    if prior is None:
        raise SystemExit(f"task_id {task_id} not found in current taskcards.jsonl")
    enriched = dict(prior)
    enriched["rollback_or_recovery"] = rollback_text
    enriched["recorded_at"] = NOW
    enriched["recorded_by"] = RECORDED_BY
    store.append(enriched)
    print(f"enriched {task_id} (status unchanged: {enriched['status']})")

print(f"\ntaskcards.jsonl -> {store.path}")
