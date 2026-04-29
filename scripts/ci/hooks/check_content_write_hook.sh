#!/usr/bin/env bash
# check_content_write_hook.sh — PreToolUse Write hook for content-check gate.
#
# Invoked by Claude Code's PreToolUse hook when the Write tool is called.
# Claude Code pipes hook input as JSON to stdin (see hooks.md).
#
# Behavior:
#   - If the target file_path is under content/, requires a content-check pass
#     marker at reports/content-check/<encoded-path>.pass before allowing Write.
#   - The marker is written by audit/runner.py (S-23) when a file passes with
#     zero FAIL findings.
#   - Exits 2 (block) if the marker is absent.
#   - Exits 0 for non-content paths or when the marker exists.
#
# Exit codes (Claude Code PreToolUse semantics):
#   0 = allow (tool executes)
#   2 = block (tool is denied, stderr shown to agent)
#
# Bypass:
#   Set SKIP_CONTENT_WRITE_CHECK=1 to bypass (for operator debugging only).
#
# Wiring (in .claude/settings.json):
#   Add alongside check_py_write_hook.sh in the Write PreToolUse hook array.

set -euo pipefail

# Bypass escape hatch
if [ "${SKIP_CONTENT_WRITE_CHECK:-0}" = "1" ]; then
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
        "Cannot resolve Python to inspect content path." \
        "rm -rf .venv && python -m venv .venv && pip install -r scripts/ci/requirements.txt" \
        "SKIP_CONTENT_WRITE_CHECK=1" \
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
        "SKIP_CONTENT_WRITE_CHECK=1" \
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
        "SKIP_CONTENT_WRITE_CHECK=1" \
        "docs/GOVERNANCE_QUICKSTART.md"
fi

# Normalise Windows backslashes to forward slashes
FILE_PATH="${FILE_PATH//\\//}"

# Convert Windows drive letter prefix (d:/) to MSYS2/Git Bash format (/d/)
# Runtime on Windows provides paths like "d:/path" but pwd gives "/d/path"
if [[ "$FILE_PATH" =~ ^([a-zA-Z]):/ ]]; then
    DRIVE="${BASH_REMATCH[1],,}"
    FILE_PATH="/${DRIVE}/${FILE_PATH:3}"
fi

# Strip absolute repo-root prefix to get relative path
FILE_PATH="${FILE_PATH#"${REPO_ROOT}/"}"

# Only gate content/ paths
if [[ "$FILE_PATH" != content/* ]]; then
    exit 0
fi

# Determine repo root from script location (scripts/ci/ — two levels up)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# Encode path: replace / with _ (mirrors the bash marker naming in the plan)
ENCODED="${FILE_PATH//\//_}"
MARKER="$REPO_ROOT/reports/content-check/${ENCODED}.pass"

if [ ! -f "$MARKER" ]; then
    _gov_block "Write denied — content-check (S-23) not passed." \
        "No pass marker for $FILE_PATH at reports/content-check/." \
        "Run /content-check on this file first." \
        "SKIP_CONTENT_WRITE_CHECK=1 (operator only)" \
        "docs/GOVERNANCE_QUICKSTART.md"
fi

exit 0
