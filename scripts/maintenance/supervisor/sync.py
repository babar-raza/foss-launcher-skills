"""
sync.py — Persist supervisor state to .supervisor/state/ and .supervisor/memory/.

Idempotent: same sprint path → same state output (timestamps excluded).
Runtime state (.supervisor/state/, .supervisor/memory/) is gitignored.
Tracked assets (.supervisor/schemas/, .supervisor/prompts/, .supervisor/config/) are
NOT overwritten by sync — only runtime state is written here.

Exit 0 always in dry-run. Exit 1 on fatal errors.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
from _common import REPO_ROOT, base_args, safe_emit


def sync(sprint_prompt_path=None, repo_root=None, write_to_disk=False):
    """Return sync state dict. If write_to_disk=True, persist to .supervisor/state/.

    write_to_disk defaults to False for backward compatibility.
    orchestrate() passes write_to_disk=True in execute mode only.
    """
    root = Path(repo_root or REPO_ROOT)
    now = datetime.now(timezone.utc)

    # Load prior state if available
    state_path = root / ".supervisor" / "state" / "current.json"
    prior_state = {}
    if state_path.exists():
        try:
            prior_state = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    sprint_info = {}
    if sprint_prompt_path and Path(sprint_prompt_path).exists():
        sprint_info = {
            "sprint_prompt_path": str(sprint_prompt_path),
            "sprint_prompt_exists": True,
        }

    new_state = {
        "last_sync": now.isoformat(),
        "last_action": prior_state.get("last_action", "none"),
        "sprint_count": prior_state.get("sprint_count", 0) + 1,
        "products_processed": prior_state.get("products_processed", []),
        "last_handoff_sha": prior_state.get("last_handoff_sha", "none"),
        **sprint_info,
    }

    session_context = {
        "last_sync": now.isoformat(),
        "supervisor_version": "1.0.0",
        "repo_root": str(root),
        "state_path": str(state_path.relative_to(root) if state_path.is_absolute() else state_path),
    }

    result = {
        "status": "SYNC_COMPLETE",
        "state": new_state,
        "session_context": session_context,
        "state_path": str(state_path),
    }

    if write_to_disk:
        state_dir = state_path.parent
        memory_dir = root / ".supervisor" / "memory"
        state_dir.mkdir(parents=True, exist_ok=True)
        memory_dir.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(new_state, indent=2), encoding="utf-8")
        (memory_dir / "session_context.json").write_text(
            json.dumps(session_context, indent=2), encoding="utf-8"
        )
        result["persisted"] = True

    return result


def main():
    parser = base_args("Persist supervisor state to .supervisor/")
    parser.add_argument("--sprint", type=str, default=None,
                        help="Path to generated sprint prompt file")
    args = parser.parse_args()

    data = sync(sprint_prompt_path=args.sprint)

    root = Path(REPO_ROOT)
    state_dir = root / ".supervisor" / "state"
    memory_dir = root / ".supervisor" / "memory"
    state_dir.mkdir(parents=True, exist_ok=True)
    memory_dir.mkdir(parents=True, exist_ok=True)

    # Write runtime state (gitignored paths)
    state_path = state_dir / "current.json"
    state_path.write_text(json.dumps(data["state"], indent=2), encoding="utf-8")

    mem_path = memory_dir / "session_context.json"
    mem_path.write_text(json.dumps(data["session_context"], indent=2), encoding="utf-8")

    if args.output:
        safe_emit(data, args.output)
        print(f"Sync state written to {args.output}")
    else:
        print(json.dumps(data, indent=2, default=str))

    return 0


if __name__ == "__main__":
    sys.exit(main())
