#!/usr/bin/env bash
# session_start_ledger_hook.sh — SessionStart hook: idempotent session-ledger
# init at TRUE session start (2026-08-30 stale-guard plan, T6 / TC-SG-05).
#
# Why: ledger manifests were previously created only by the Edit/Write
# PreToolUse hook, so (a) Bash-driven sessions never got one, (b) the recorded
# base_commit_sha was HEAD at the FIRST EDIT, not at session start (a narrower
# stale-check window than the truth), and (c) manifests were never closed, so
# >=2 "live" manifests was the steady state (~34% of 5-minute slots measured
# at plan time). This hook records the honest base at startup/resume; its
# SessionEnd sibling closes the manifest; the Stop sibling heartbeats it.
#
# Identity: CLAUDE_CODE_SESSION_ID (VERIFIED equal to the harness session_id:
# the transcript file carries the same value). stdin JSON session_id is a
# best-effort fallback only. Also appends `export AGENT_SESSION_ID=<id>` to
# $CLAUDE_ENV_FILE when the variable is not already set, so every later Bash
# tool call carries identity without the honour-system inline prefix.
#
# Fail-open, always: this hook NEVER blocks a session from starting.
# Exit codes: 0 (always).
#
# Bypass: SKIP_SESSION_LEDGER_HOOKS=1 — operator-only.
# Test seam: SESSION_LEDGER_HOOK_ROOT_OVERRIDE (data root), honoured only when
# PYTEST_CURRENT_TEST is also set (same gated design as
# CHECK_COMMIT_HOOK_ROOT_OVERRIDE — see check_commit_bash_hook.sh).

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
    --repo-root "$REPO_ROOT" init --if-missing --session-id "$SID" 2>/dev/null || true

if [ -n "${CLAUDE_ENV_FILE:-}" ] && [ -z "${AGENT_SESSION_ID:-}" ]; then
    # Same value the hooks themselves resolve — a DIFFERENT hand-picked value
    # here would split one session into two identities (adversarial F3).
    echo "export AGENT_SESSION_ID=\"$SID\"" >> "$CLAUDE_ENV_FILE" 2>/dev/null || true
fi

# Residue report (read-only): SessionStart stdout becomes agent context, so a
# session sees the real-index traps left by crashes/other checkouts BEFORE
# committing anything.
"$PYTHON" "$REAL_REPO_ROOT/scripts/pipeline/commands/ops/checkout_sync.py" \
    --repo-root "$REPO_ROOT" report 2>/dev/null | head -12 || true

exit 0
