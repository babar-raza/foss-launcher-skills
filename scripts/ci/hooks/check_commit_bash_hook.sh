#!/usr/bin/env bash
# check_commit_bash_hook.sh — PreToolUse Bash hook for commit governance.
#
# Invoked by Claude Code's PreToolUse hook when the Bash tool is called.
# Blocks direct `git commit` unless the /commit skill (S-76) is active.
#
# Blocked operations (exit 2):
#   git commit           (direct commit without /commit skill)
#   git commit -m "..."  (direct commit with message)
#   git commit --amend   (amend without /commit skill)
#
# Allowed despite matching `git commit`:
#   git commit-tree      (plumbing command, not porcelain)
#   git commit-graph     (plumbing command, not porcelain)
#   Any `git commit` when S-76 skill context is active (ACTIVE.json)
#
# Fail-open design: if CLAUDE_TOOL_INPUT is empty or command cannot be parsed,
# the hook exits 0. This prevents deadlocks when hook infrastructure is broken.
#
# Bypass:
#   SKIP_COMMIT_BASH_CHECK=1 — operator-only, not for agent use
#
# Exit codes (Claude Code PreToolUse semantics):
#   0 = allow (tool executes)
#   2 = block (tool denied; stderr shown to agent)
#
# Wiring: added to Bash PreToolUse array in .claude/settings.json AFTER
# check_destructive_bash_hook.sh.

set -euo pipefail

# Operator-only bypass
if [ "${SKIP_COMMIT_BASH_CHECK:-0}" = "1" ]; then
    exit 0
fi

# Determine repo root from script location (scripts/ci/hooks/ — three levels up)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# Resolve Python via shared resolver (venv-only, no python3 fallback — DR-01)
source "$(dirname "${BASH_SOURCE[0]}")/find_python.sh" || true

# Shared governance block helper (TC-DS-03)
source "$(dirname "${BASH_SOURCE[0]}")/_gov_block.sh"

# Read tool input JSON from env var (set by Claude Code) or stdin
TOOL_INPUT="${CLAUDE_TOOL_INPUT:-}"
if [ -z "$TOOL_INPUT" ]; then
    TOOL_INPUT=$(cat 2>/dev/null || true)
fi

# Fail-open: no input → cannot inspect → allow
if [ -z "$TOOL_INPUT" ]; then
    exit 0
fi

# Fail-open: no Python → cannot parse → allow
if [ -z "$PYTHON" ]; then
    exit 0
fi

# Extract command string from the JSON
COMMAND=$(printf '%s' "$TOOL_INPUT" | "$PYTHON" -c "
import json, sys
try:
    data = json.load(sys.stdin)
    ti = data.get('tool_input', {})
    cmd = ti.get('command', '') if isinstance(ti, dict) else ''
    if not cmd:
        cmd = data.get('command', '')
    print(cmd)
except Exception:
    sys.exit(0)
" 2>/dev/null) || true

# Fail-open: cannot extract command → allow
if [ -z "$COMMAND" ]; then
    exit 0
fi

# ---------------------------------------------------------------------------
# Pattern matching: detect `git commit` (porcelain) in the command
# ---------------------------------------------------------------------------

_found_commit=false

while IFS= read -r _line; do
    # Strip leading whitespace
    _stripped="${_line#"${_line%%[![:space:]]*}"}"
    [ -z "$_stripped" ] && continue
    [[ "$_stripped" == \#* ]] && continue

    # Match `git commit` but NOT `git commit-tree` or `git commit-graph` (plumbing)
    # The pattern requires `git commit` followed by end-of-string, whitespace, or a flag
    if echo "$_stripped" | grep -qE '(^|[;|&])\s*git\s+commit(\s|$)'; then
        # Exclude plumbing commands that start with `commit-`
        if echo "$_stripped" | grep -qE '(^|[;|&])\s*git\s+commit-'; then
            continue
        fi
        _found_commit=true
        break
    fi
done <<< "$COMMAND"

# No git commit found in command → allow
if [ "$_found_commit" != "true" ]; then
    exit 0
fi

# ---------------------------------------------------------------------------
# git commit detected — check if S-76 skill context is active
# ---------------------------------------------------------------------------

ACTIVE_FILE="$REPO_ROOT/reports/skill-context/ACTIVE.json"

if [ -f "$ACTIVE_FILE" ]; then
    # Check if the active skill is S-76 (the /commit skill)
    ACTIVE_SKILL=$("$PYTHON" -c "
import json, sys
try:
    with open(sys.argv[1]) as f:
        data = json.load(f)
    print(data.get('skill_id', ''))
except Exception:
    print('')
" "$ACTIVE_FILE" 2>/dev/null) || true

    if [ "$ACTIVE_SKILL" = "S-76" ]; then
        # /commit skill is orchestrating this git commit → allow
        exit 0
    fi
fi

# Block: git commit without S-76 context
_gov_block "Bash denied — direct git commit is not allowed." \
    "Content commits must use the /commit skill (S-76), not direct git commit." \
    "Invoke /commit --force-all --hint \"description of changes\"" \
    "SKIP_COMMIT_BASH_CHECK=1 (operator only)" \
    "CLAUDE.md (Behavioral Mandates)" \
    '{"violation_type": "direct_git_commit", "unblock_condition": "use /commit skill (S-76) instead of direct git commit"}'
