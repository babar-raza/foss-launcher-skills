import sys, json
sys.path.insert(0, r"d:\onedrive\Documents\GitHub\aspose.org\scripts\pipeline\lib")
from taskcard_store import TaskcardStore

MISSION = "MT022-2026-08-06-ASPOSE-COM-TARGETS-HARDENING"
REPO_ROOT = r"d:\onedrive\Documents\GitHub\aspose.org"
RECORDED_BY = "claude-session-20260806-aspose-com-targets-hardening"

task_id = sys.argv[1]
expected = sys.argv[2]
new_status = sys.argv[3]
evidence = sys.argv[4:] if len(sys.argv) > 4 else []

store = TaskcardStore(MISSION, repo_root=REPO_ROOT)
out = store.update_taskcard_status(
    task_id, expected_status=expected, new_status=new_status,
    recorded_by=RECORDED_BY, evidence_refs=evidence,
)
print(json.dumps(out, indent=2))
