"""generate_agent_skill_index.py — Thin wrapper over scripts/sync_agents.py.

Delegates to the existing canonical sync script, which handles frontmatter
preservation and mirrors to .agents/skills/ and .kilocode/skills/.

Usage:
    python tools/capability_sync/generate_agent_skill_index.py --check
    python tools/capability_sync/generate_agent_skill_index.py --sync
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SYNC_SCRIPT = _REPO_ROOT / "scripts" / "sync_agents.py"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync skills/ → .agents/skills/ and .kilocode/skills/ (wraps sync_agents.py).")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Diff only; exit 1 if drift")
    mode.add_argument("--sync", action="store_true", help="Write derived targets")
    args = parser.parse_args(argv)

    if not _SYNC_SCRIPT.exists():
        print(f"ERROR: sync_agents.py not found at {_SYNC_SCRIPT}", file=sys.stderr)
        return 1

    mode_flag = "--check" if args.check else "--sync"
    result = subprocess.run(
        [sys.executable, str(_SYNC_SCRIPT), mode_flag],
        cwd=_REPO_ROOT,
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
