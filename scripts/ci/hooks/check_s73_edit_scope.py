#!/usr/bin/env python3
"""check_s73_edit_scope.py — resolves "is there an active S-73 (manual-edit)
context, in any session, whose scope covers this file?" for
check_content_edit_hook.sh.

Pre-A2-migration, this question was answered by reading the single global
reports/skill-context/ACTIVE.json and checking skill_id == "S-73". The A2
migration (session_ledger.py / skill_context.py) moved live contexts to
per-session files under reports/skill-context/active/<session_id>.json and
stopped writing ACTIVE.json at all for sessions on the per-session path —
so that single-file check became permanently dead code, and the Edit-tool
S-73 bypass in check_content_edit_hook.sh stopped firing for every session
started after the migration (found 2026-07-23 while running /manual-edit
during the words/net launch).

This checks the legacy ACTIVE.json (back-compat, byte-identical to the old
behavior when present) AND every live per-session context file, independent
of which session invoked this hook process — deliberately not keyed off
AGENT_SESSION_ID, since a Bash-tool-set env var does not propagate to the
Edit tool's own hook subprocess.

Usage: python check_s73_edit_scope.py <ctx_dir> <file_path>
Exit 0 if an active S-73 context's scope covers <file_path>, exit 1 otherwise.
Always exits cleanly (never raises) — a lookup failure means "no bypass".
"""
from __future__ import annotations

import fnmatch
import json
import sys
from pathlib import Path


def _load(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _file_in_scope(file_path: str, scope_patterns: list[str]) -> bool:
    normalized = file_path.replace("\\", "/")
    for pattern in scope_patterns or []:
        if fnmatch.fnmatch(normalized, pattern):
            return True
    return False


def s73_covers(ctx_dir: Path, file_path: str) -> bool:
    active_file = ctx_dir / "ACTIVE.json"
    active_dir = ctx_dir / "active"

    legacy = _load(active_file)
    if legacy and legacy.get("skill_id") == "S-73" and _file_in_scope(
        file_path, legacy.get("scope_patterns", [])
    ):
        return True

    if active_dir.exists():
        for f in active_dir.glob("*.json"):
            rec = _load(f)
            if not rec:
                continue
            if rec.get("skill_id") == "S-73" and _file_in_scope(
                file_path, rec.get("scope_patterns", [])
            ):
                return True

    return False


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) < 2:
        return 1
    try:
        covered = s73_covers(Path(argv[0]), argv[1])
    except Exception:
        return 1
    return 0 if covered else 1


if __name__ == "__main__":
    raise SystemExit(main())
