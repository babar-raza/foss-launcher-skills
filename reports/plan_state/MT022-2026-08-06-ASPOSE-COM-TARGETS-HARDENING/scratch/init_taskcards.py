import sys
sys.path.insert(0, r"d:\onedrive\Documents\GitHub\aspose.org\scripts\pipeline\lib")
from taskcard_store import TaskcardStore

MISSION = "MT022-2026-08-06-ASPOSE-COM-TARGETS-HARDENING"
REPO_ROOT = r"d:\onedrive\Documents\GitHub\aspose.org"
RECORDED_BY = "claude-session-20260806-aspose-com-targets-hardening"
NOW = "2026-08-06T00:00:00Z"

store = TaskcardStore(MISSION, repo_root=REPO_ROOT)

cards = [
    dict(task_id="TC-00", phase_id="PHASE_0", title="Gap escalation + taskcard store init",
         lane_owner="Lane 0",
         allowed_paths=["reports/skill-gaps/**", "reports/plan_state/**"],
         forbidden_paths=["content/**", "knowledge/**"],
         dependencies=[],
         source_issue_ids=["operator-request: execute e2e", "plan: separately-flagged-not-fixed-hazy-crescent"]),
    dict(task_id="TC-01", phase_id="PHASE_1", title="Harden fetch_aspose_com_targets.py (retry, configure seam, tests, registry fix)",
         lane_owner="Lane 1",
         allowed_paths=["scripts/pipeline/commands/ops/fetch_aspose_com_targets.py",
                        "scripts/pipeline/tests/test_fetch_aspose_com_targets.py",
                        "scripts/pipeline/config/registry.yaml"],
         forbidden_paths=["content/**"],
         dependencies=["TC-00"],
         source_issue_ids=["commit e40ed6b509: verify_url retry gap"]),
    dict(task_id="TC-02", phase_id="PHASE_1", title="Live data backfill: classify + correct the 5 status regressions",
         lane_owner="Lane 2",
         allowed_paths=["data/aspose_com_targets.json", "data/backlinks/aspose_com_targets.yaml",
                        "reports/backlinks/aspose_com_targets_report.md"],
         forbidden_paths=["content/**"],
         dependencies=["TC-01"],
         source_issue_ids=["commit e40ed6b509: 5 status regressions never persisted"]),
    dict(task_id="TC-03", phase_id="PHASE_1", title="Staleness gate on backlink_targets.py / batch_reference.py",
         lane_owner="Lane 3",
         allowed_paths=["scripts/pipeline/lib/backlink_targets.py",
                        "scripts/pipeline/commands/content/batch_reference.py",
                        "scripts/pipeline/tests/test_backlink_targets.py"],
         forbidden_paths=["content/**"],
         dependencies=["TC-00"],
         source_issue_ids=["reassessment: generated_at written but never enforced"]),
    dict(task_id="TC-04", phase_id="PHASE_2", title="New scheduled drift-detection watcher + workflow",
         lane_owner="Lane 4",
         allowed_paths=["scripts/pipeline/commands/ops/aspose_com_targets_watch.py",
                        "scripts/pipeline/tests/test_aspose_com_targets_watch.py",
                        "scripts/pipeline/config/registry.yaml",
                        ".github/workflows/aspose-com-targets-watch.yml"],
         forbidden_paths=["content/**"],
         dependencies=["TC-01"],
         source_issue_ids=["reassessment: no scheduled re-verification exists"]),
    dict(task_id="TC-05", phase_id="PHASE_1", title="Backlog row for the 5 status regressions",
         lane_owner="Lane 5",
         allowed_paths=["backlog/BACKLOG.md"],
         forbidden_paths=["content/**"],
         dependencies=["TC-02"],
         source_issue_ids=["commit e40ed6b509: finding never tracked anywhere"]),
    dict(task_id="TC-06", phase_id="PHASE_3", title="Mint aspose-com-targets-watch skill (governance closure, deferrable)",
         lane_owner="Lane 6",
         allowed_paths=["skills/aspose-com-targets-watch.md", ".agents/skills/aspose-com-targets-watch/SKILL.md",
                        ".kilocode/skills/aspose-com-targets-watch/SKILL.md", ".claude/commands/aspose-com-targets-watch.md",
                        "docs/registries/skills.md"],
         forbidden_paths=["content/**"],
         dependencies=["TC-04"],
         source_issue_ids=["gap report: reports/skill-gaps/2026-08-06-aspose-com-targets-hardening.md"]),
    dict(task_id="TC-07", phase_id="PHASE_3", title="Verification + evidence bundle + final report",
         lane_owner="Lane 7",
         allowed_paths=["reports/sprint/aspose-com-targets-hardening-2026-08-06/**"],
         forbidden_paths=["content/**"],
         dependencies=["TC-01", "TC-02", "TC-03", "TC-04", "TC-05"],
         source_issue_ids=["plan: single-go execution requirement"]),
]

for c in cards:
    rec = {
        "task_id": c["task_id"],
        "mission_id": MISSION,
        "phase_id": c["phase_id"],
        "title": c["title"],
        "status": "TODO",
        "recorded_at": NOW,
        "recorded_by": RECORDED_BY,
        "evidence_refs": [],
        "lane_owner": c["lane_owner"],
        "allowed_paths": c["allowed_paths"],
        "forbidden_paths": c["forbidden_paths"],
        "dependencies": c["dependencies"],
        "source_issue_ids": c["source_issue_ids"],
    }
    out = store.append(rec)
    print("appended", out["task_id"], out["status"])

print("done")
