#!/usr/bin/env python3
"""check_session_identity_parity.py — production concurrency redesign (2026-08-01),
Step 2: catch a reimplemented AGENT_SESSION_ID/CODEX_THREAD_ID/CLAUDE_CODE_SESSION_ID
precedence chain mechanically, instead of only by another forensic pass.

This repo shipped 4 independent copies of the same 3-tier identity-resolution
precedence (explicit > AGENT_SESSION_ID > CODEX_THREAD_ID > CLAUDE_CODE_SESSION_ID)
before this redesign: skill_context.py, refresh_run.py, skill_context_attribution.py,
and check_commit_bash_hook.sh's inline Python. One of them (check_commit_bash_hook.sh)
was independently found to have drifted -- an early version silently omitted the
CODEX_THREAD_ID tier, and nothing caught it until a manual forensic review did. All
4 now delegate to scripts/pipeline/lib/session_identity.py instead of hand-copying
the chain. This check exists so a *future* hand-copy (someone adding a 5th duplicate,
or reverting one of the 4 back to inline env-var reads) is caught the same way
check_taskcard_plan_parity.py (RPR-G-04) catches plan/store drift: as a named,
scriptable check, not a thing a human has to remember to look for.

Detection heuristic: any non-test .py/.sh file under scripts/ that literally mentions
all three env var names (AGENT_SESSION_ID, CODEX_THREAD_ID, CLAUDE_CODE_SESSION_ID)
is assumed to be implementing (or re-implementing) the full 3-tier precedence, and
must also reference session_identity somewhere in the same file -- either a Python
`import session_identity` or, for a .sh file shelling out to an embedded Python
heredoc, the literal substring appearing in that heredoc's own source text (a plain
whole-file substring search sees it either way, since the heredoc is inline).

This is deliberately a coarse text-level heuristic, not an AST/import-graph
analysis (matching this repo's other check_*_parity.py scripts) -- it will not
catch someone importing session_identity but never calling it, and it will not
catch logic split across two files that only together implement the 3-tier chain.
It catches the actual failure mode this repo hit in production: a single file
hand-copying the whole chain inline.

A file that mentions fewer than all 3 names (e.g. session_ledger.py, which as of
this check only implements a 2-tier explicit>AGENT_SESSION_ID scheme -- see Step 3
of the redesign plan, an explicit pending decision, not a silent gap) is not a
match for this heuristic and is not flagged. Widening that check is Step 3's job,
not this one's.

Exit codes:
  0 — no un-migrated duplicates found
  1 — at least one file implements the full 3-tier chain without importing
      session_identity
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_SCAN_ROOT = _REPO_ROOT / "scripts"

_ENV_NAMES = ("AGENT_SESSION_ID", "CODEX_THREAD_ID", "CLAUDE_CODE_SESSION_ID")
_DELEGATION_MARKER = "session_identity"

# The shared module's own file legitimately defines all 3 names and is exempt
# by construction (it IS the source of truth, not a consumer of it).
_EXEMPT_PATHS = {_SCAN_ROOT / "pipeline" / "lib" / "session_identity.py"}

_EXCLUDED_DIR_PARTS = {"__pycache__", "tests", "test", ".venv", "node_modules"}


def _is_excluded(path: Path) -> bool:
    if path in _EXEMPT_PATHS:
        return True
    if path.name.startswith("test_"):
        return True
    return any(part in _EXCLUDED_DIR_PARTS for part in path.parts)


def find_candidate_files(scan_root: Path = _SCAN_ROOT) -> list[Path]:
    """All non-test .py/.sh files under scripts/ (deterministic order)."""
    if not scan_root.exists():
        return []
    files = [
        p for pattern in ("*.py", "*.sh")
        for p in scan_root.rglob(pattern)
        if not _is_excluded(p)
    ]
    return sorted(set(files))


def find_undelegated_files(scan_root: Path = _SCAN_ROOT) -> list[Path]:
    """Files that mention all 3 identity env vars but never reference
    session_identity -- candidate un-migrated (or newly re-introduced)
    duplicate precedence chains."""
    violations = []
    for path in find_candidate_files(scan_root):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if not all(name in text for name in _ENV_NAMES):
            continue
        if _DELEGATION_MARKER in text:
            continue
        violations.append(path)
    return violations


def main(argv: list[str] | None = None) -> int:
    del argv  # no CLI options today; kept for parity with sibling check scripts
    # Read _SCAN_ROOT at call time, not via find_undelegated_files' default
    # parameter (bound once at def time) -- so a test's
    # monkeypatch.setattr(parity, "_SCAN_ROOT", ...) is actually honored.
    violations = find_undelegated_files(_SCAN_ROOT)
    if violations:
        print(f"SESSION IDENTITY PARITY: {len(violations)} un-migrated duplicate(s):")
        for path in violations:
            try:
                rel = path.relative_to(_REPO_ROOT)
            except ValueError:
                rel = path
            print(f"  {rel} mentions all 3 identity env vars but never references "
                  f"session_identity -- route it through scripts/pipeline/lib/"
                  f"session_identity.py instead of hand-copying the precedence chain.")
        return 1
    print("OK: no un-migrated session-identity precedence chains found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
