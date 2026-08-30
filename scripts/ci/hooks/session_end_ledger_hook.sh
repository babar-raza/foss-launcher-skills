#!/usr/bin/env bash
# session_end_ledger_hook.sh — SessionEnd hook: close this session's ledger
# manifest (2026-08-30 stale-guard plan, T6 / TC-SG-05).
#
# Manifests were never closed automatically, so every ended session stayed
# "live" for the full 8h staleness TTL, keeping >=2-live-manifest ambiguity
# as the steady state. SessionEnd does NOT run on crash/kill — the TTL sweep
# remains the backstop for that case, by design.
#
# Wire with an explicit per-hook "timeout" (SessionEnd hooks otherwise share
# a very short global budget; a venv Python start needs more).
#
# Fail-open, always. Exit codes: 0 (always).
# Bypass: SKIP_SESSION_LEDGER_HOOKS=1 — operator-only.
# Test seam: SESSION_LEDGER_HOOK_ROOT_OVERRIDE + PYTEST_CURRENT_TEST.

set -uo pipefail

if [ "${SKIP_SESSION_LEDGER_HOOKS:-0}" = "1" ]; then
    exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REAL_REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
if [ -n "${SESSION_LEDGER_HOOK_ROOT_OVERRIDE:-}" ] && [ -n "${PYTEST_CURRENT_TEST:-}" ]; then
    REPO_ROOT="$SESSION_LEDGER_HOOK_ROOT_OVERRIDE"
else
    REPO_ROOT="$REAL_REPO_ROOT"
fi

STDIN_PAYLOAD=$(cat 2>/dev/null || true)
SID="${CLAUDE_CODE_SESSION_ID:-}"
if [ -z "$SID" ] && [ -n "$STDIN_PAYLOAD" ]; then
    SID=$(printf '%s' "$STDIN_PAYLOAD" \
        | grep -o '"session_id"[[:space:]]*:[[:space:]]*"[^"]*"' \
        | head -1 | sed 's/.*"\([^"]*\)"$/\1/') || true
fi
if [ -z "$SID" ]; then
    exit 0
fi

source "$SCRIPT_DIR/find_python.sh" 2>/dev/null || true
if [ -z "${PYTHON:-}" ]; then
    exit 0
fi

"$PYTHON" "$REAL_REPO_ROOT/scripts/pipeline/commands/ops/session_ledger.py" \
    --repo-root "$REPO_ROOT" close --session-id "$SID" >/dev/null 2>&1 || true

exit 0
