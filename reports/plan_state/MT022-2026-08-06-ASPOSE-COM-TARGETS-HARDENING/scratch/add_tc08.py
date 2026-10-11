import sys
sys.path.insert(0, r"d:\onedrive\Documents\GitHub\aspose.org\scripts\pipeline\lib")
from taskcard_store import TaskcardStore

MISSION = "MT022-2026-08-06-ASPOSE-COM-TARGETS-HARDENING"
REPO_ROOT = r"d:\onedrive\Documents\GitHub\aspose.org"
RECORDED_BY = "claude-session-20260806-psl-convergence"
NOW = "2026-08-06T00:00:00Z"

store = TaskcardStore(MISSION, repo_root=REPO_ROOT)
rec = {
    "task_id": "TC-08",
    "mission_id": MISSION,
    "phase_id": "PHASE_4_PSL_CONVERGENCE",
    "title": "Register mission in plans/master-plan.md + plans/missions/ (MT022-L2-001)",
    "status": "TODO",
    "recorded_at": NOW,
    "recorded_by": RECORDED_BY,
    "evidence_refs": [],
    "lane_owner": "Lane 8 (PSL convergence)",
    "allowed_paths": [
        "plans/master-plan.md",
        "plans/missions/MT022-2026-08-06-ASPOSE-COM-TARGETS-HARDENING.md",
    ],
    "forbidden_paths": ["content/**"],
    "dependencies": ["TC-00", "TC-01", "TC-02", "TC-03", "TC-04", "TC-05"],
    "source_issue_ids": ["MT022-L2-001"],
    "source_issue_level": "L2_INTEGRATION",
    "source_audit_finding": ".supervisor/state/MT022-2026-08-06-ASPOSE-COM-TARGETS-HARDENING/stage1-issue-model.json",
    "why_it_matters": "prompt4-close-task.md cannot validly close this mission without this ledger entry existing.",
    "risk_addressed": "Mission becomes undiscoverable via the repo's canonical mission index; a future close-task.md run would either fail its own validation or falsely claim closure.",
    "supervisor_role": "PSL convergence controller (this session)",
    "required_implementation": "Create plans/missions/{mission_id}.md summarizing the mission (what/why/taskcards/commits/evidence); upsert plans/master-plan.md's index row via master_plan_index.py's upsert_mission_row() (lock-guarded, not a hand-edit).",
    "required_verification": "Re-read plans/master-plan.md and confirm the row exists and points at the new mission file; re-read the mission file and confirm it accurately reflects the real taskcard store and commit list.",
    "required_evidence": "git diff/show of both files post-change; commit SHA.",
    "quality_dimensions": {
        "requirement_correctness": 5, "implementation_correctness": 5,
        "integration_completeness": 5, "pipeline_compatibility": 5,
        "governance_compliance": 5, "evidence_completeness": 5,
        "test_coverage": 4, "validator_coverage": 4, "repeatability": 5,
        "idempotency": 5, "downstream_consumer_readiness": 5,
        "agentic_consumption_quality": 5, "rollback_safety_quality": 5,
        "documentation_skill_agent_sync_quality": 5, "production_readiness": 5,
    },
    "scoring_rubric": "15-dimension scale per prompt3-controlled-execution.md Phase 5; each dimension 1-5, item accepted only if every dimension >= 4.",
    "reroute_rule_if_score_below_4": "If any dimension scores below 4/5 after execution, mark REROUTED, repair, rerun verification, rescore before acceptance.",
    "acceptance_criteria": "plans/master-plan.md has a MT022 row pointing at plans/missions/MT022-2026-08-06-ASPOSE-COM-TARGETS-HARDENING.md; that file exists and accurately summarizes the mission; both committed and pushed.",
    "stop_conditions": "Stop and escalate if master_plan_index.py's lock cannot be acquired (another session holds it) -- retry with backoff, do not hand-edit the index file to bypass the lock.",
    "closeout_rules": "CLOSED only once the row + mission file are both confirmed present at the pushed commit SHA via a fresh git show against origin/main.",
    "machine_state": "TODO -> IN_PROGRESS -> IMPLEMENTED -> FOCUSED_VERIFIED -> CLOSED (schema 5f enum, this repo's real taskcard_store.py)",
    "validation_commands": [
        "grep -n MT022 plans/master-plan.md",
        "test -f plans/missions/MT022-2026-08-06-ASPOSE-COM-TARGETS-HARDENING.md",
        "git show <sha>:plans/master-plan.md | grep MT022",
    ],
}
out = store.append(rec)
print("appended", out["task_id"], out["status"])
