#!/usr/bin/env python3
"""_plan_capture.py — helper for check_plan_origination_capture_hook.sh.

Reads a Claude Code PreToolUse hook JSON payload from stdin. If tool_input's
file_path is a .md file under $HOME/.claude/plans/, records
{file_path, written_at} to $HOME/.claude/plans/.last-plan-write.json.

Never raises, never prints, always exits 0 — this is a breadcrumb writer with
zero governance authority (see check_plan_origination_capture_hook.sh header).
"""
import json
import sys
import os
import datetime


def to_posix(p: str) -> str:
    p = p.replace("\\", "/")
    if len(p) >= 2 and p[1] == ":" and p[0].isalpha():
        p = "/" + p[0].lower() + p[2:]
    return p


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0

    ti = data.get("tool_input", {})
    fp = ti.get("file_path", "") if isinstance(ti, dict) else ""
    if not fp:
        fp = data.get("file_path", "")
    if not fp:
        return 0

    # POSIX-normalized forms are for STRING COMPARISON ONLY — native Windows
    # Python's open() does not understand git-bash's "/c/Users/..." convention
    # (that translation is a shell-level thing MSYS2 does, not the OS or
    # Python's io layer), so file I/O below always uses the native home_raw
    # form, never the posix-normalized one.
    home_raw = os.environ.get("HOME", os.path.expanduser("~"))
    norm_path = to_posix(fp)
    plans_prefix_posix = to_posix(home_raw).rstrip("/") + "/.claude/plans/"

    if not (norm_path.startswith(plans_prefix_posix) and norm_path.endswith(".md")):
        return 0

    plans_dir_native = os.path.join(home_raw.rstrip("\\/"), ".claude", "plans")
    breadcrumb = os.path.join(plans_dir_native, ".last-plan-write.json")
    written_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        with open(breadcrumb, "w", encoding="utf-8") as f:
            json.dump({"file_path": fp, "written_at": written_at}, f)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
