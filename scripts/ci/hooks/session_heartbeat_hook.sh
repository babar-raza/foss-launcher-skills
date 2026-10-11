#!/usr/bin/env bash
# session_heartbeat_hook.sh — Stop hook (fires at the end of every assistant
# turn): touch this session's ledger manifest so the mtime-based staleness
# sweep (session_ledger._sweep_stale, 8h TTL) reflects real liveness during
# long read-only stretches (2026-08-30 stale-guard plan, T6 / TC-SG-05).
#
# Pure bash by design — no Python start on a per-turn hook. NEVER closes or
# creates anything (Stop is per-turn, not per-session; closing here was
# adversarial finding F1's failure mode).
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

SID="${CLAUDE_CODE_SESSION_ID:-}"
if [ -z "$SID" ]; then
    exit 0
fi

MANIFEST="$REPO_ROOT/reports/session-state/${SID}.json"
if [ -f "$MANIFEST" ]; then
    touch "$MANIFEST" 2>/dev/null || true
fi

exit 0
