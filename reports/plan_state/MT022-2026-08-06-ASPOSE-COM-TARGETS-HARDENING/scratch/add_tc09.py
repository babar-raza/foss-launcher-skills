import sys
sys.path.insert(0, r"d:\onedrive\Documents\GitHub\aspose.org\scripts\pipeline\lib")
from taskcard_store import TaskcardStore

MISSION = "MT022-2026-08-06-ASPOSE-COM-TARGETS-HARDENING"
REPO_ROOT = r"d:\onedrive\Documents\GitHub\aspose.org"
RECORDED_BY = "claude-session-20260806-pilot-followup"
NOW = "2026-08-06T00:00:00Z"

store = TaskcardStore(MISSION, repo_root=REPO_ROOT)
rec = {
    "task_id": "TC-09",
    "mission_id": MISSION,
    "phase_id": "PHASE_5_PILOT_FOLLOWUP",
    "title": "Bound aspose_com_targets_watch.py's worst-case runtime (found live via pilot rerun, run 31120889071 cancelled at timeout-minutes:15)",
    "status": "TODO",
    "recorded_at": NOW,
    "recorded_by": RECORDED_BY,
    "evidence_refs": [],
    "lane_owner": "Lane 9 (pilot followup)",
    "allowed_paths": [
        "scripts/pipeline/commands/ops/aspose_com_targets_watch.py",
        "scripts/pipeline/tests/test_aspose_com_targets_watch.py",
        ".github/workflows/aspose-com-targets-watch.yml",
    ],
    "forbidden_paths": ["content/**"],
    "dependencies": ["TC-04"],
    "source_issue_ids": ["pilot-rerun-2026-08-06-Finding-C"],
    "source_audit_finding": "reports/sprint/aspose-com-targets-hardening-2026-08-06/pilot_rerun_comparison_report.md",
    "why_it_matters": "A cancelled job produces zero signal (no clean result, no regression report) exactly on days aspose.com is broadly slow -- the one scenario the watcher most needs to report on.",
    "risk_addressed": "Unbounded cumulative retry time (TC-01 hardening x TC-04's per-entry recheck) can exceed the external GitHub Actions job timeout with no internal awareness or graceful degradation.",
}
out = store.append(rec)
print("appended", out["task_id"], out["status"])
