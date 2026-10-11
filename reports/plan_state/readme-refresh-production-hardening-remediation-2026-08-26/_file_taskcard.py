import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline" / "lib"))
from taskcard_store import TaskcardStore  # noqa: E402

MISSION_ID = "readme-refresh-production-hardening-remediation-2026-08-26"

arg = sys.argv[1]
if arg.startswith("@"):
    payload = json.loads(Path(arg[1:]).read_text(encoding="utf-8"))
else:
    payload = json.loads(arg)
records = payload if isinstance(payload, list) else [payload]
store = TaskcardStore(MISSION_ID, repo_root=REPO_ROOT)
for record in records:
    written = store.append(record)
    print(f"filed {written['task_id']} status={written['status']}")
