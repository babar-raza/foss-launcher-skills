#!/usr/bin/env python3
"""skill_context_attribution.py — HARDEN-A3/finding-3 (final-validation-gate
remediation, 2026-07-22).

Resolves which (skill_id, session_id) should be credited when
check_skill_context_hook.sh records a file touch. This logic used to live
inline as a 54-line Python heredoc inside the bash hook — functionally
correct (independently reviewed and manually exercised during HARDEN-A3), but
with zero automated test coverage, unlike its sibling check_commit_bash_hook.sh
(40 tests). Extracted here, unchanged in behavior, so it can be tested
directly like any other pure function instead of only by hand.

Attribution order (first match wins):
  1. AGENT_SESSION_ID env var names a live per-session context file
     (reports/skill-context/active/<id>.json) -> use it.
  2. Otherwise, the legacy reports/skill-context/ACTIVE.json, if present
     -> use it (and its own session_id field, if it carries one).
  3. Otherwise, if exactly one per-session context file exists under
     reports/skill-context/active/ -> use it (its filename stem is the
     session id). Two or more with no identity given is deliberately left
     unresolved here (ambiguous) — the hook's touch-recording is best-effort
     and non-blocking, unlike check_commit_bash_hook.sh's S-76 gate, which
     does hard-fail on the equivalent ambiguity.
  4. No context resolves -> None (caller records nothing; this must never
     raise or block the edit it's attached to).

Usage (as invoked by check_skill_context_hook.sh):
    python skill_context_attribution.py <ctx_dir>
Prints "<skill_id>\\t<session_id>" to stdout if attribution resolves
(session_id may be empty for the legacy single-session case); prints nothing
otherwise. Always exits 0 — this is a best-effort lookup, never a gate.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _load(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def resolve_attribution(ctx_dir: Path) -> tuple[str, str] | None:
    """Return (skill_id, session_id) to credit for a touch under ctx_dir
    (reports/skill-context/), or None if nothing resolves. See module
    docstring for the resolution order."""
    ctx_dir = Path(ctx_dir)
    active_file = ctx_dir / "ACTIVE.json"
    active_dir = ctx_dir / "active"

    sid = os.environ.get("AGENT_SESSION_ID", "").strip()
    rec = _load(active_dir / f"{sid}.json") if sid else None
    if rec is None:
        legacy = _load(active_file)
        if legacy:
            rec = legacy
            sid = legacy.get("session_id", "") or sid
    if rec is None and active_dir.exists():
        files = sorted(active_dir.glob("*.json"))
        if len(files) == 1:
            rec = _load(files[0])
            sid = files[0].stem
    if rec and rec.get("skill_id"):
        return rec["skill_id"], (sid or "")
    return None


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        return 0
    result = resolve_attribution(Path(argv[0]))
    if result:
        skill_id, sid = result
        print(f"{skill_id}\t{sid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
