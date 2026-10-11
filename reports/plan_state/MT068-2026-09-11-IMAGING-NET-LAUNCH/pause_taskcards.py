import sys
sys.path.insert(0, "scripts/pipeline")
from lib.taskcard_store import TaskcardStore

MISSION_ID = "MT068-2026-09-11-IMAGING-NET-LAUNCH"
RECORDED_BY = "session:69f58bf2-c7d9-4d98-8de9-1a947e4860e8"
REASON = ("User explicitly interrupted mid-session: 'Do not start the publishing of "
          "imaging net. Work on other things that matter.' Paused before any content "
          "generation began (still at TC-MT068-01, registry step incomplete -- the "
          "auto-scanner doesn't recognize Aspose.Imaging.Foss's naming convention, gap "
          "filed at reports/skill-gaps/2026-09-11-imaging-net-naming-convention.md, "
          "awaiting approval that is now moot). Nothing under content/ or knowledge/ was "
          "touched for imaging/net.")

store = TaskcardStore(MISSION_ID)
for task_id in ["TC-MT068-01", "TC-MT068-02", "TC-MT068-03", "TC-MT068-04", "TC-MT068-05"]:
    rec = store.pause_taskcard(task_id, reason=REASON, recorded_by=RECORDED_BY)
    print("paused", rec["task_id"], rec["status"])
