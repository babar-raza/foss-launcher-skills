#!/usr/bin/env bash
# check_content_edit_hook.sh — PreToolUse Edit hook for content-file governance.
#
# Invoked by Claude Code's PreToolUse hook when the Edit tool is called.
# Claude Code pipes hook input as JSON to stdin (see hooks.md).
#
# Behavior:
#   - If the target file_path is under content/, blocks the Edit with a
#     governance reminder to invoke /manual-edit (S-73) first.
#   - Exits 2 (block) for content/ paths.
#   - Exits 0 for all other paths.
#
# Exit codes (Claude Code PreToolUse semantics):
#   0 = allow (tool executes)
#   2 = block (tool is denied, stderr shown to agent)
#
# Bypass:
#   Set SKIP_CONTENT_EDIT_CHECK=1 to bypass (for operator use inside S-73 only).
#   S-73 sets this env var before calling Edit internally.
#
# Wiring (in .claude/settings.json):
#   {
#     "matcher": "Edit",
#     "hooks": [{"type": "command", "command": "bash scripts/ci/hooks/check_content_edit_hook.sh"}]
#   }

set -euo pipefail

# Bypass escape hatch — S-73 sets this when calling Edit as part of its own procedure
if [ "${SKIP_CONTENT_EDIT_CHECK:-0}" = "1" ]; then
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
    _gov_block "Edit denied — .venv is broken or missing." \
        "Cannot resolve Python to inspect edit path." \
        "rm -rf .venv && python -m venv .venv && pip install -r scripts/ci/requirements.txt" \
        "SKIP_CONTENT_EDIT_CHECK=1" \
        "docs/GOVERNANCE_QUICKSTART.md"
fi

# Read tool input JSON from stdin (Claude Code pipes PreToolUse JSON to stdin)
TOOL_INPUT="${CLAUDE_TOOL_INPUT:-}"

if [ -z "$TOOL_INPUT" ]; then
    TOOL_INPUT=$(cat 2>/dev/null || true)
fi

if [ -z "$TOOL_INPUT" ]; then
    # Fail-closed: no input means we cannot verify — block
    _gov_block "Edit denied — no tool input available." \
        "Cannot determine file path from empty input (fail-closed)." \
        "Retry the Edit tool call." \
        "SKIP_CONTENT_EDIT_CHECK=1" \
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
    _gov_block "Edit denied — could not parse file_path." \
        "JSON parse failure (fail-closed)." \
        "Retry the Edit tool call." \
        "SKIP_CONTENT_EDIT_CHECK=1" \
        "docs/GOVERNANCE_QUICKSTART.md"
fi

# Normalise Windows backslashes to forward slashes for path comparison
FILE_PATH="${FILE_PATH//\\//}"

# Convert Windows drive letter prefix (d:/) to MSYS2/Git Bash format (/d/)
# Runtime on Windows provides paths like "d:/path" but pwd gives "/d/path"
if [[ "$FILE_PATH" =~ ^([a-zA-Z]):/ ]]; then
    DRIVE="${BASH_REMATCH[1],,}"
    FILE_PATH="/${DRIVE}/${FILE_PATH:3}"
fi

# Strip absolute repo-root prefix to get relative path
FILE_PATH="${FILE_PATH#"${REPO_ROOT}/"}"

# Block direct Edit calls on content/ files
if [[ "$FILE_PATH" == content/* ]]; then
    _gov_block "Direct Edit on content file denied." \
        "$FILE_PATH is under content/ — requires /manual-edit (S-73) first." \
        "Invoke /manual-edit which sets the bypass internally." \
        "SKIP_CONTENT_EDIT_CHECK=1 (operator only)" \
        "docs/GOVERNANCE_QUICKSTART.md"
fi

exit 0
