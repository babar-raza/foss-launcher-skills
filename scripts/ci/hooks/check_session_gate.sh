#!/usr/bin/env bash
# check_session_gate.sh — PreToolUse gate: requires session bootstrap before non-exempt tool calls.
#
# Invoked by Claude Code's PreToolUse hook (matcher ".*") for every tool call.
# Replaces the previous inline bash command in .claude/settings.json.
#
# Behavior:
#   - Exempts the Read tool (read-only; required for AGENTS.md during bootstrap)
#   - Exempts the exact bootstrap command: bash scripts/ci/hooks/bootstrap_session_gate.sh
#   - For all other tools: requires .claude/.agents_read to exist (session bootstrapped)
#   - Empty/missing input: fail-open (exit 0) — bootstrap deadlock prevention (DR-03)
#   - Malformed non-empty JSON: fail-closed (exit 2) regardless of gate state
#
# Bootstrap semantics (Model B — honest latch):
#   .agents_read is a session bootstrap latch, NOT proof that AGENTS.md was read.
#   Use language: "session not bootstrapped" / "run /session-start"
#   Never: "AGENTS.md not confirmed read"
#
# Exit codes (Claude Code PreToolUse semantics):
#   0 = allow (tool executes)
#   2 = block (tool denied; stderr shown to agent)
#
# Operator bypass (not for agents):
#   SKIP_SESSION_GATE_CHECK=1 — skips all checks; exit 0
#
# Test isolation override (not for production use):
#   SESSION_GATE_OVERRIDE=<absolute path> — use a temp gate file instead of the
#   repo default; allows tests to run without touching .claude/.agents_read

set -euo pipefail

# Operator-only bypass (not documented in agent-visible files)
if [ "${SKIP_SESSION_GATE_CHECK:-0}" = "1" ]; then
    exit 0
fi

# Determine repo root from script location (scripts/ci/hooks/ — three levels up)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# Gate file path: production uses repo default; SESSION_GATE_OVERRIDE redirects to a
# caller-supplied path (used by tests to avoid touching the live .claude/.agents_read)
GATE_FILE="${SESSION_GATE_OVERRIDE:-$REPO_ROOT/.claude/.agents_read}"

# Resolve Python via shared resolver (venv-only, no python3 fallback — DR-01)
# If venv absent/broken: PYTHON="" — session gate falls through to the bash-native
# degraded-venv fallback below (never the python-dependent parsing path).
source "$(dirname "${BASH_SOURCE[0]}")/find_python.sh" || true

# Test-only override: force the degraded-venv path without touching the real
# .venv (used by scripts/ci/tests/test_check_session_gate.py). Never set in
# production — there is no code path that sets this outside the test harness.
if [ "${SESSION_GATE_TEST_FORCE_NO_PYTHON:-0}" = "1" ]; then
    PYTHON=""
fi

# Shared governance block helper (TC-DS-03)
source "$(dirname "${BASH_SOURCE[0]}")/_gov_block.sh"

# Read tool input JSON from env var (set by Claude Code) or stdin
TOOL_INPUT="${CLAUDE_TOOL_INPUT:-}"
if [ -z "$TOOL_INPUT" ]; then
    TOOL_INPUT=$(cat 2>/dev/null || true)
fi

# Empty/missing input: fail-open (DR-03).
# Cannot determine tool name — cannot apply gate. This is the bootstrap deadlock path:
# if the gate is absent and Python is broken, blocking here prevents even Read from
# firing, making manual recovery impossible. Narrow fail-open here only.
# Malformed non-empty JSON is a different signal and is handled below (fail-closed).
if [ -z "$TOOL_INPUT" ]; then
    exit 0
fi

# --- Degraded-venv fallback (fixes a real deadlock, found live 2026-08-16) ---
# When $PYTHON is empty (venv missing/broken), the JSON parsing below — and the
# bootstrap-command regex match further down — both shell out to "$PYTHON" and
# silently fail (empty command), which fell through to the "python execution
# failure" branch that follows the parse step. That branch only ever checked
# the gate file — it never re-applied the hardcoded Read/Grep/Glob exemptions
# or the bootstrap-command exemption, because those checks compare against
# $TOOL_NAME, which was never extracted. Net effect: a broken venv in a fresh
# worktree blocked every tool call with no recovery path, including Read and
# the exact bootstrap command — defeating the "narrow fail-open" this file
# already claims to guarantee for the bootstrap-deadlock case (see comment
# above). This block restores that guarantee using bash-only parsing (no
# python required) for the essential recovery exemptions.
if [ -z "$PYTHON" ]; then
    TOOL_NAME_FALLBACK=$(printf '%s' "$TOOL_INPUT" | grep -o '"tool_name"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed -E 's/.*:[[:space:]]*"([^"]*)"$/\1/')

    if [ "$TOOL_NAME_FALLBACK" = "Read" ] || [ "$TOOL_NAME_FALLBACK" = "Grep" ] || [ "$TOOL_NAME_FALLBACK" = "Glob" ]; then
        exit 0
    fi

    if [ "$TOOL_NAME_FALLBACK" = "Bash" ]; then
        COMMAND_FALLBACK=$(printf '%s' "$TOOL_INPUT" | grep -o '"command"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed -E 's/.*:[[:space:]]*"([^"]*)"$/\1/')
        if [[ "$COMMAND_FALLBACK" =~ ^bash[[:space:]]+\.{0,2}/?scripts/ci/(hooks/)?bootstrap_session_gate\.sh[[:space:]]*$ ]]; then
            exit 0
        fi
    fi

    # Everything else (including Bash commands we can't classify as read-only
    # without python) still requires the bootstrap gate file — deliberately
    # fail-closed; only the recovery paths above are exempt.
    if [ -f "$GATE_FILE" ]; then
        exit 0
    fi
    _gov_block "Tool call denied — session not bootstrapped, and .venv is also broken." \
        "Python venv is unavailable, so read-only-Bash classification cannot run; .claude/.agents_read gate file is missing." \
        "Run: bash scripts/ci/hooks/bootstrap_session_gate.sh (exempted above via bash-native match), then bash scripts/ci/hooks/repair_venv.sh" \
        "SKIP_SESSION_GATE_CHECK=1" \
        "AGENTS.md §3 (Session Start)"
fi

# Parse tool name and command from JSON.
# Supports both Claude Code runtime format:  {"tool_name":"...","tool_input":{...}}
# and manual test format:                     {"tool_name":"...","command":"..."}
# Malformed JSON: fail-closed (exit 2) regardless of gate state.
PARSE_RESULT=$(printf '%s' "$TOOL_INPUT" | "$PYTHON" -c "
import json, sys

try:
    data = json.load(sys.stdin)
except json.JSONDecodeError as e:
    print('PARSE_ERROR:' + str(e))
    sys.exit(0)

tool_name = data.get('tool_name', '')

# Extract command for Bash tool (tool_input.command or top-level command)
ti = data.get('tool_input', {})
command = ''
if isinstance(ti, dict):
    command = ti.get('command', '')
if not command:
    command = data.get('command', '')

print('TOOL_NAME:' + tool_name)
print('COMMAND:' + command)
" 2>/dev/null || true)

# Handle Python execution failure (treat as empty — fall through to gate check)
if [ -z "$PARSE_RESULT" ]; then
    if [ -f "$GATE_FILE" ]; then
        exit 0
    else
        _gov_block "Tool call denied — session not bootstrapped." \
            ".claude/.agents_read gate file is missing." \
            "Run /session-start or: bash scripts/ci/hooks/bootstrap_session_gate.sh" \
            "SKIP_SESSION_GATE_CHECK=1" \
            "AGENTS.md §3 (Session Start)"
    fi
fi

# Check for parse error (malformed JSON) — fail-closed regardless of gate state
if echo "$PARSE_RESULT" | grep -q "^PARSE_ERROR:"; then
    PARSE_ERR=$(echo "$PARSE_RESULT" | grep "^PARSE_ERROR:" | sed 's/^PARSE_ERROR://')
    _gov_block "Tool call denied — malformed tool input JSON." \
        "Could not parse tool_name from input: $PARSE_ERR" \
        "This is likely a Claude Code bug. Retry the tool call." \
        "SKIP_SESSION_GATE_CHECK=1" \
        "AGENTS.md §3 (Session Start)"
fi

TOOL_NAME=$(echo "$PARSE_RESULT" | grep "^TOOL_NAME:" | sed 's/^TOOL_NAME://')
COMMAND=$(echo "$PARSE_RESULT" | grep "^COMMAND:" | sed 's/^COMMAND://')

# --- Exemptions ---

# 1. Read tool: always exempt (read-only, zero governance risk, needed for bootstrap)
if [ "$TOOL_NAME" = "Read" ]; then
    exit 0
fi

# 2. Exact bootstrap command: exempt
# Accepts: bash scripts/ci/hooks/bootstrap_session_gate.sh
#          bash ./scripts/ci/hooks/bootstrap_session_gate.sh
# Rejects: compound commands, quoted paths, path traversal
if [ "$TOOL_NAME" = "Bash" ] && [ -n "$COMMAND" ]; then
    BOOTSTRAP_MATCH=$(printf '%s' "$COMMAND" | "$PYTHON" -c "
import re, sys
cmd = sys.stdin.read().strip()
pattern = re.compile(r'^bash\s+\.{0,2}/?scripts/ci/(hooks/)?bootstrap_session_gate\.sh\s*$')
print('match' if pattern.match(cmd) else 'no-match')
" 2>/dev/null || echo "no-match")
    if [ "$BOOTSTRAP_MATCH" = "match" ]; then
        exit 0
    fi
fi

# 3. Grep tool: intrinsically read-only (TC-DS-01)
if [ "$TOOL_NAME" = "Grep" ]; then
    exit 0
fi

# 4. Glob tool: intrinsically read-only (TC-DS-01)
if [ "$TOOL_NAME" = "Glob" ]; then
    exit 0
fi

# 5. Read-only Bash commands: exempt via classifier (TC-DS-01)
#    Uses classify_bash_readonly.py — fail-closed (exit 1 = not read-only)
if [ "$TOOL_NAME" = "Bash" ] && [ -n "$COMMAND" ] && [ -n "$PYTHON" ]; then
    if printf '%s' "$COMMAND" | "$PYTHON" "$REPO_ROOT/scripts/ci/checks/classify_bash_readonly.py" 2>/dev/null; then
        exit 0
    fi
fi

# --- Gate check for all other tools ---
if [ ! -f "$GATE_FILE" ]; then
    _gov_block "Tool call denied — session not bootstrapped." \
        ".claude/.agents_read gate file is missing." \
        "Run /session-start or: bash scripts/ci/hooks/bootstrap_session_gate.sh" \
        "SKIP_SESSION_GATE_CHECK=1" \
        "AGENTS.md §3 (Session Start)"
fi

exit 0
