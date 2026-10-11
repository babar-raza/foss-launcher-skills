"""
tm_export.py — Export action list to Task Master-compatible JSON format.

Does NOT write to .taskmaster/ (requires explicit MODE 4 approval).
Bridges to backlog item IDs when available; uses supervisor IDs as fallback.
Output always goes to reports/ (never to .taskmaster/).
"""
from __future__ import annotations
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
from _common import REPO_ROOT, base_args, safe_emit


def _priority_label(p):
    return {0: "critical", 1: "high", 2: "medium"}.get(p, "low")


def _find_backlog_id(action, backlog_ids):
    fam = action.get("family", "").upper()
    plat = action.get("platform", "").upper()
    for bid in backlog_ids:
        if fam in bid.upper() or (plat and plat in bid.upper()):
            return bid
    return None


def tm_export(action_plan, repo_root=None):
    now = datetime.now(timezone.utc)
    actions = action_plan.get("actions", [])
    backlog_ids = action_plan.get("backlog_priority_ids", [])
    tasks = []
    for i, action in enumerate(actions):
        atype = action.get("type", "UNKNOWN")
        fam = action.get("family", "")
        plat = action.get("platform", "")
        reason = action.get("reason", "")
        backlog_id = _find_backlog_id(action, backlog_ids)
        task_id = backlog_id if backlog_id else f"SUP-{i+1:03d}"
        id_src = "backlog" if backlog_id else "supervisor_generated"
        title = f"{atype}: {fam}/{plat}" if fam else f"{atype}: {reason[:50]}"
        desc = (f"Supervisor action: {atype}\n"
                + (f"Family: {fam}, Platform: {plat}\n" if fam else "")
                + f"Reason: {reason}\n"
                + f"Skill chain: {action.get('skill_chain', 'needs_skill_contract_discovery')}")
        tasks.append({
            "id": task_id,
            "id_source": id_src,
            "title": title,
            "description": desc,
            "priority": _priority_label(action.get("priority", 99)),
            "status": "pending",
            "dependencies": [],
            "supervisor_action_type": atype,
            "created_at": now.isoformat(),
        })
    return {
        "tasks": tasks,
        "task_count": len(tasks),
        "generated_at": now.isoformat(),
        "taskmaster_write_mode": "report_only",
        "taskmaster_dir_written": False,
        "note": "Output is report-only. .taskmaster/ write requires MODE 4 human approval.",
        "backlog_ids_used": [t["id"] for t in tasks if t["id_source"] == "backlog"],
        "supervisor_ids_used": [t["id"] for t in tasks if t["id_source"] == "supervisor_generated"],
    }


def main():
    parser = base_args("Export action list to Task Master JSON format")
    parser.add_argument("--action-plan", required=True, help="Path to compare output JSON")
    args = parser.parse_args()
    try:
        action_plan = json.loads(Path(args.action_plan).read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 1
    data = tm_export(action_plan)
    if args.output:
        safe_emit(data, args.output)
        print(f"TM export: {data['task_count']} tasks -> {args.output}")
    else:
        print(json.dumps(data, indent=2, default=str))
    return 0

if __name__ == "__main__":
    sys.exit(main())
