#!/usr/bin/env bash
# check_py_write_hook.sh — PreToolUse Write hook for Python file placement.
#
# Invoked by Claude Code's PreToolUse hook when the Write tool is called.
# Claude Code pipes hook input as JSON to stdin (see hooks.md).
#
# Behavior:
#   - If the proposed file path ends in .py, runs check_python_placement.py --propose
#   - Exits 2 if placement is wrong (blocks the Write tool call)
#   - Exits 0 if path is correct or does not end in .py
#
# Exit codes (Claude Code PreToolUse semantics):
#   0 = allow (tool executes)
#   2 = block (tool is denied, stderr shown to agent)
#
# Bypass:
#   Set SKIP_PY_PLACEMENT_CHECK=1 to bypass (for operator debugging only).
#   Example: SKIP_PY_PLACEMENT_CHECK=1 claude "..."
#
# Wiring (in .claude/settings.json):
#   {
#     "matcher": "Write",
#     "hooks": [{"type": "command", "command": "bash scripts/ci/hooks/check_py_write_hook.sh"}]
#   }

set -euo pipefail

# Bypass escape hatch
if [ "${SKIP_PY_PLACEMENT_CHECK:-0}" = "1" ]; then
    exit 0
fi

# Determine repo root from script location (scripts/ci/ — two levels up)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# Resolve Python via shared resolver (venv-only, no python3 fallback — DR-01)
source "$(dirname "${BASH_SOURCE[0]}")/find_python.sh" || true

# Shared governance block helper (TC-DS-03)
source "$(dirname "${BASH_SOURCE[0]}")/_gov_block.sh"
if [ -z "$PYTHON" ]; then
    _gov_block "Write denied — .venv is broken or missing." \
        "Cannot resolve Python to inspect .py placement." \
        "rm -rf .venv && python -m venv .venv && pip install -r scripts/ci/requirements.txt" \
        "SKIP_PY_PLACEMENT_CHECK=1" \
        "docs/GOVERNANCE_QUICKSTART.md"
fi

# Read tool input JSON from stdin (Claude Code pipes PreToolUse JSON to stdin)
TOOL_INPUT="${CLAUDE_TOOL_INPUT:-}"

if [ -z "$TOOL_INPUT" ]; then
    TOOL_INPUT=$(cat 2>/dev/null || true)
fi

if [ -z "$TOOL_INPUT" ]; then
    # Fail-closed: no input means we cannot verify — block
    _gov_block "Write denied — no tool input available." \
        "Cannot determine file path from empty input (fail-closed)." \
        "Retry the Write tool call." \
        "SKIP_PY_PLACEMENT_CHECK=1" \
        "docs/GOVERNANCE_QUICKSTART.md"
fi

# Extract file_path from the JSON — pipe via stdin to avoid shell injection
# Claude Code stdin format: {"tool_input": {"file_path": "..."}, ...}
PARSE_EXIT=0
FILE_PATH=$(printf '%s' "$TOOL_INPUT" | "$PYTHON" -c "
import json, sys
try:
    data = json.load(sys.stdin)
    ti = data.get('tool_input', {})
    fp = ti.get('file_path', '') if isinstance(ti, dict) else ''
    if not fp:
        fp = data.get('file_path', '')
    print(fp)
except Exception:
    sys.exit(1)
" 2>/dev/null) || PARSE_EXIT=$?

if [ $PARSE_EXIT -ne 0 ] || [ -z "$FILE_PATH" ]; then
    # Fail-closed: unparseable input — block
    _gov_block "Write denied — could not parse file_path." \
        "JSON parse failure (fail-closed)." \
        "Retry the Write tool call." \
        "SKIP_PY_PLACEMENT_CHECK=1" \
        "docs/GOVERNANCE_QUICKSTART.md"
fi

# Only check .py files
if [[ "$FILE_PATH" != *.py ]]; then
    exit 0
fi

# Run the placement check in --propose mode.
# Use set +e to capture exit code safely — set -e would abort immediately on non-zero.
set +e
"$PYTHON" "$REPO_ROOT/scripts/ci/checks/check_python_placement.py" --propose "$FILE_PATH" >&2
EXIT_CODE=$?
set -e

if [ $EXIT_CODE -ne 0 ]; then
    _gov_block "Write denied — $FILE_PATH is not in a sanctioned .py location." \
        "Python files must be in scripts/pipeline/, scripts/ci/, tests/, etc." \
        "Move the .py file to a sanctioned location." \
        "SKIP_PY_PLACEMENT_CHECK=1 (operator only)" \
        "docs/GOVERNANCE_QUICKSTART.md" \
        '{"violation_type": "unsanctioned_py_location", "path": "'"'"'$FILE_PATH'"'"'", "unblock_condition": "move .py file to a sanctioned location"}'
fi

exit 0
