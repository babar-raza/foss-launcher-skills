"""
ruflo_export.py — Export lane assignments for Ruflo/claude-flow coordination.

Records TOOL_UNAVAILABLE if claude-flow is not in PATH.
Still produces lane assignment JSON from the action plan regardless.
Does NOT start daemons or register MCP servers.
"""
from __future__ import annotations
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
from _common import REPO_ROOT, base_args, safe_emit


LANE_MAP = {
    "INVESTIGATE_MISSING_STATE": "C1",
    "REFRESH_PRODUCT": "C3",
    "HEAL_PAGES": "C3",
    "ENRICH_PAGES": "C4",
    "HANDOFF_UPDATE": "C5",
    "NO_ACTIONS_READY": "C0",
}

LANE_DEPS = {
    "C0": [], "C1": [], "C3": ["C1"], "C4": ["C3"],
    "C5": ["C4"], "C6": ["C5"], "C7": ["C6"],
    "C8": ["C7"], "C9": ["C8"], "C10": ["C9"],
}


def _check_claude_flow():
    if not shutil.which("claude-flow"):
        return False, "TOOL_UNAVAILABLE: claude-flow not found in PATH"
    try:
        r = subprocess.run(
            ["claude-flow", "--version"],
            capture_output=True, text=True, timeout=10
        )
        return True, (r.stdout.strip() or r.stderr.strip())
    except Exception as exc:
        return False, f"TOOL_UNAVAILABLE: {exc}"


def ruflo_export(action_plan, repo_root=None):
    now = datetime.now(timezone.utc)
    actions = action_plan.get("actions", [])
    available, cf_status = _check_claude_flow()

    lanes = {}
    for action in actions:
        atype = action.get("type", "UNKNOWN")
        lane_id = LANE_MAP.get(atype, "C3")
        if lane_id not in lanes:
            lanes[lane_id] = {
                "lane_id": lane_id,
                "dependencies": LANE_DEPS.get(lane_id, []),
                "actions": [],
                "file_ownership": [],
            }
        lanes[lane_id]["actions"].append({
            "type": atype,
            "family": action.get("family"),
            "platform": action.get("platform"),
            "priority": action.get("priority"),
        })

    if not lanes:
        lanes["C0"] = {
            "lane_id": "C0",
            "dependencies": [],
            "actions": [{"type": "NO_ACTIONS_READY"}],
            "file_ownership": [],
        }

    return {
        "lanes": list(lanes.values()),
        "lane_count": len(lanes),
        "claude_flow_available": available,
        "claude_flow_status": cf_status,
        "daemon_started": False,
        "mcp_registered": False,
        "generated_at": now.isoformat(),
        "note": (
            "claude-flow not in PATH — lane assignments for documentation only."
            if not available
            else "Lane assignments ready for claude-flow coordination."
        ),
    }


def main():
    parser = base_args("Export lane assignments for Ruflo coordination")
    parser.add_argument("--action-plan", required=True, help="Path to compare output JSON")
    args = parser.parse_args()
    try:
        action_plan = json.loads(Path(args.action_plan).read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 1
    data = ruflo_export(action_plan)
    if args.output:
        safe_emit(data, args.output)
        print(f"Ruflo export: {data['lane_count']} lanes -> {args.output}")
        if not data["claude_flow_available"]:
            print(f"  NOTE: {data['claude_flow_status']}")
    else:
        print(json.dumps(data, indent=2, default=str))
    return 0

if __name__ == "__main__":
    sys.exit(main())
