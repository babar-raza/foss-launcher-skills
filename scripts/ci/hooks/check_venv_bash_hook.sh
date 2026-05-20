#!/usr/bin/env bash

# Shell preflight (defensive; agents use Git Bash via runtime on Windows)
# warn mode — will be block mode in Phase 4 (caller prepends _SHELL_CHECK_MODE=block)
# shellcheck source=scripts/ci/hooks/check_shell_bash.sh
source "$(dirname "$0")/check_shell_bash.sh" || exit 2

# check_venv_bash_hook.sh — PreToolUse Bash hook for venv Python enforcement.
#
# Invoked by Claude Code's PreToolUse hook when the Bash tool is called.
# Claude Code passes tool input as JSON via $CLAUDE_TOOL_INPUT or stdin.
#
# Behavior:
#   - Extracts the command string from tool input JSON.
#   - Blocks (exit 2) if the command contains a bare `python` or bare `pip`
#     invocation not prefixed by .venv/ — these would use system Python,
#     bypassing repo-managed dependencies.
#   - Allows (exit 0) for compliant commands, exemptions, or non-Python commands.
#
# Blocked patterns:
#   python <script|module|-c>     (bare python — system Python)
#   pip install|show|freeze|...   (bare pip — system pip)
#
# Exemptions (always allowed):
#   .venv/Scripts/python ...     (correct Windows path)
#   .venv/bin/python ...         (correct Unix path)
#   python -m venv ...           (venv bootstrap — must use system Python)
#   python --version             (diagnostic — no execution side effects)
#   python3 --version            (diagnostic)
#
# Exit codes (Claude Code PreToolUse semantics):
#   0 = allow (tool executes)
#   2 = block (tool is denied, stderr shown to agent)
#
# Wiring (in .claude/settings.json):
#   {
#     "matcher": "Bash",
#     "hooks": [{"type": "command", "command": "bash scripts/ci/hooks/check_venv_bash_hook.sh"}]
#   }

set -euo pipefail

# Determine repo root from script location (scripts/ci/ — two levels up)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# Resolve Python via shared resolver (venv-only, no python3 fallback — DR-01)
# If venv absent/broken: PYTHON="" — falls through to fail-open (cannot inspect command)
source "$(dirname "${BASH_SOURCE[0]}")/find_python.sh" || true

# Shared governance block helper (TC-DS-03)
source "$(dirname "${BASH_SOURCE[0]}")/_gov_block.sh"

# Read tool input JSON from env var (set by Claude Code) or stdin
TOOL_INPUT="${CLAUDE_TOOL_INPUT:-}"

if [ -z "$TOOL_INPUT" ]; then
    TOOL_INPUT=$(cat 2>/dev/null || true)
fi

if [ -z "$TOOL_INPUT" ]; then
    # Fail-open: no input means we cannot inspect the command — allow.
    # This differs from content hooks (fail-closed) because a false-positive
    # here blocks legitimate tool use with no recourse.
    exit 0
fi

# Extract command string from the JSON — pipe via stdin to avoid shell injection
# Claude Code format: {"tool_name":"Bash","tool_input":{"command":"..."}}
# or                 : {"command":"..."}  (manual test format)
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

if [ -z "$COMMAND" ]; then
    # Cannot parse command — fail-open (see reasoning above)
    exit 0
fi

# ---------------------------------------------------------------------------
# Detection: scan each line of the command for bare python/pip invocations.
#
# The check works on the *first token* of each pipeline segment — it catches
# the pattern `python script.py` or `pip install foo` but not `echo python`
# or `VAR=$(which python)` (which are string uses, not invocations).
#
# KNOWN LIMITATION (L-1): IFS-based splitting is quote-unaware.
# A command like: CLAUDE_TOOL_INPUT='{"command":"python ..."}' bash this_script.sh
# will falsely trigger because "python" appears after stripping the env-var
# prefix token (the JSON value is not a quoted argument — it's a raw string
# in the token stream). This only affects compound inline test patterns, not
# normal agent Bash invocations. Severity: LOW. Classification: accepted
# design tradeoff (conservative failure). Do not redesign.
# ---------------------------------------------------------------------------

VIOLATION=""

while IFS= read -r line; do
    # Strip leading whitespace
    stripped="${line#"${line%%[![:space:]]*}"}"

    # Skip blank lines and comments
    [ -z "$stripped" ] && continue
    [[ "$stripped" == \#* ]] && continue

    # Normalise: collapse runs of spaces and handle semicolons/pipes as segment breaks
    # Split on ; | && || to get individual command tokens
    IFS=';|&' read -ra SEGMENTS <<< "$stripped"
    for seg in "${SEGMENTS[@]}"; do
        # Get the first non-empty word (the command itself)
        read -r first_token rest_of_seg <<< "$seg" 2>/dev/null || continue
        [ -z "$first_token" ] && continue

        # Strip env-var prefixes like PYTHONPATH=foo python ...
        # Keep stripping VAR=value tokens until we hit a non-assignment token
        while [[ "$first_token" == *=* ]]; do
            first_token="$rest_of_seg"
            read -r first_token rest_of_seg <<< "$rest_of_seg" 2>/dev/null || break
            [ -z "$first_token" ] && break
        done
        [ -z "$first_token" ] && continue

        # Check if first token is a bare python/python3/pip invocation
        case "$first_token" in
            python|python3)
                # Exempt: venv bootstrap (must use system python)
                [[ "$rest_of_seg" == "-m venv"* ]] && continue
                [[ "$rest_of_seg" == "--version"* ]] && continue
                [[ "$rest_of_seg" == "-V"* ]] && continue
                # Anything else is a bare python invocation — flag it
                VIOLATION="$stripped"
                break 2
                ;;
            pip|pip3)
                # All bare pip subcommands are violations
                VIOLATION="$stripped"
                break 2
                ;;
            *.venv/*)
                # Already prefixed with .venv/ path — compliant
                continue
                ;;
        esac
    done
done <<< "$COMMAND"

if [ -n "$VIOLATION" ]; then
    _gov_block "Bash denied — bare python/pip invocation detected."         "Command uses system Python: $VIOLATION"         "Use .venv/Scripts/python (Win) or .venv/bin/python (Unix) instead."         "Not available (exempt: python -m venv, python --version)"         "AGENTS.md §12 (Virtual environment)"
fi

exit 0
