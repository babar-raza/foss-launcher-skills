#!/usr/bin/env bash
# check_ledger_init_hook.sh — PreToolUse Edit/Write hook: mandatory session-ledger
# auto-initialization (mission-plan-the-end-to-end-vast-hejlsberg.md Task 24,
# closes G16 part 1).
#
# Root problem this closes: session_ledger.py (reports/session-state/{id}.json)
# already tracks dirty_at_start + touched_files, exactly the data needed to tell
# "a file I'm about to commit" apart from "a file some OTHER live session left
# dirty and uncommitted" -- but `init` was never auto-invoked by anything, so it
# only ever ran when an agent remembered to call it manually (the same
# honor-system shape git_plumb_commit.py's own stale-file-regression check was
# built to eliminate for a different check). This hook closes that one gap:
# ensure a ledger exists before any file-mutating tool call, so
# git_plumb_commit.py's new mandatory ledger cross-check (Task 25) always has
# real data to check against.
#
# Behavior:
#   - Cheap path (the overwhelming common case once a session is running):
#     if reports/session-state/{session_id}.json already exists, exit 0
#     immediately -- no subprocess, no meaningful cost added to Edit/Write.
#   - Cold path (first file-mutating tool call in a session): resolve the
#     session id from the same env-var precedence session_identity.py uses
#     (AGENT_SESSION_ID > CODEX_THREAD_ID > CLAUDE_CODE_SESSION_ID), then
#     invoke `session_ledger.py init` to capture dirty_at_start for real.
#   - Fail-open, always: this hook NEVER blocks the Edit/Write it's guarding,
#     regardless of whether session-id resolution or `init` itself succeeds.
#     A missing ledger degrades Task 25's check to "cannot verify, warn" (see
#     git_plumb_commit.py), it must never turn into "cannot edit at all."
#
# Exit codes (Claude Code PreToolUse semantics):
#   0 = allow (always, by design)
#
# Wiring (in .claude/settings.json):
#   Add as a new hook entry in BOTH the "Edit" and "Write" matcher arrays,
#   alongside check_content_edit_hook.sh / check_write_path_hook.sh.
#
# Bypass:
#   SKIP_LEDGER_INIT_CHECK=1 — operator-only, skips this hook entirely (there
#   is normally no reason to: the hook never blocks anything on its own).
#
# Test isolation override (not for production use, mirrors
# check_session_gate.sh's SESSION_GATE_OVERRIDE convention exactly):
#   LEDGER_INIT_HOOK_REPO_ROOT_OVERRIDE=<absolute path> — use this directory
#   as the repo root instead of the real one, so tests never touch the live
#   reports/session-state/.

set -uo pipefail
# Note: NOT `set -e` -- every failure path in this hook must fall through to
# `exit 0` (fail-open), not abort the script mid-way with a nonzero status.

if [ "${SKIP_LEDGER_INIT_CHECK:-0}" = "1" ]; then
    exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# REAL_REPO_ROOT locates this hook's own sibling code (session_ledger.py,
# find_python.sh) -- ALWAYS the real repo, never the test override below.
# REPO_ROOT is the DATA root (where dirty_at_start/manifests should be
# written and checked) -- this is the one the override redirects, so tests
# never touch the live reports/session-state/. Conflating these two was a
# real bug caught during this task's own test-writing: a test that overrides
# REPO_ROOT must not also lose track of where session_ledger.py's actual code
# lives.
REAL_REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
if [ -n "${LEDGER_INIT_HOOK_REPO_ROOT_OVERRIDE:-}" ]; then
    REPO_ROOT="$LEDGER_INIT_HOOK_REPO_ROOT_OVERRIDE"
else
    REPO_ROOT="$REAL_REPO_ROOT"
fi

# Resolve the session id using the exact same precedence as
# scripts/pipeline/lib/session_identity.py's resolve() -- pure bash, zero
# subprocess cost, safe because normal session ids (UUIDs, YYYYMMDD-HHMMSS-xxxx
# slugs) are already alnum+hyphen and need no sanitization for a filename
# existence check. `session_ledger.py init` (invoked below, only on the cold
# path) performs the real, authoritative resolution itself -- this bash-side
# resolution is only ever used for the cheap pre-check, never persisted.
SESSION_ID="${AGENT_SESSION_ID:-}"
if [ -z "$SESSION_ID" ]; then
    SESSION_ID="${CODEX_THREAD_ID:-}"
fi
if [ -z "$SESSION_ID" ]; then
    SESSION_ID="${CLAUDE_CODE_SESSION_ID:-}"
fi

if [ -z "$SESSION_ID" ]; then
    # No resolvable identity at all -- nothing to init against. Fail-open:
    # allow the edit; Task 25's check will see no ledger and warn, not block.
    exit 0
fi

MANIFEST_PATH="$REPO_ROOT/reports/session-state/${SESSION_ID}.json"

if [ -f "$MANIFEST_PATH" ]; then
    # Cheap path: already initialized this session. Done.
    exit 0
fi

# Cold path: first file-mutating tool call this session. Resolve Python
# (venv-only, DR-01) and run the real init -- best-effort, never fail-closed.
source "$SCRIPT_DIR/find_python.sh" 2>/dev/null || true
if [ -z "${PYTHON:-}" ]; then
    # .venv broken/missing -- cannot init, but this hook still never blocks.
    exit 0
fi

"$PYTHON" "$REAL_REPO_ROOT/scripts/pipeline/commands/ops/session_ledger.py" \
    --repo-root "$REPO_ROOT" init --session-id "$SESSION_ID" >/dev/null 2>&1 || true

exit 0
