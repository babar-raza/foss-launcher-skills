#!/usr/bin/env bash
# check_write_path_hook.sh — PreToolUse Write hook for universal path-guard enforcement.
#
# Invoked by Claude Code's PreToolUse hook when the Write tool is called.
# Claude Code pipes hook input as JSON to stdin (see hooks.md).
#
# Behavior:
#   - Extracts file_path from the Write tool input JSON.
#   - Runs path_guard.py on the relative path.
#   - Exits 2 (block) if the path is DENY — root-level files and any non-allowlisted path.
#   - Exits 0 (allow) if the path is ALLOW.
#   - Fail-closed: any parse error or missing input blocks the write.
#
# Human authorization for root writes:
#   Set ROOT_WRITE_AUTHORIZED=1 in the shell session to allow a single explicitly
#   authorized root-level write.  The bypass is logged to reports/root-writes/audit.log.
#   See docs/OPERATOR_BYPASSES.md for the full protocol.
#
# Exit codes (Claude Code PreToolUse semantics):
#   0 = allow (tool executes)
#   2 = block (tool is denied, stderr shown to agent)
#
# Wiring (in .claude/settings.json):
#   Add as the FIRST entry in the Write PreToolUse hook array so path governance
#   fires before any type-specific checks.

set -euo pipefail

# Determine repo root from script location (scripts/ci/ — two levels up)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# Resolve Python via shared resolver (venv-only, no python3 fallback — DR-01)
source "$(dirname "${BASH_SOURCE[0]}")/find_python.sh" || true

# Shared governance block helper (TC-DS-03)
source "$(dirname "${BASH_SOURCE[0]}")/_gov_block.sh"
if [ -z "$PYTHON" ]; then
    _gov_block "Write denied — .venv is broken or missing." \
        "Cannot resolve Python to inspect write path." \
        "rm -rf .venv && python -m venv .venv && pip install -r scripts/ci/requirements.txt" \
        "Not available (path guard is foundational)" \
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
        "Not available (path guard is foundational)" \
        "docs/GOVERNANCE_QUICKSTART.md"
fi

# Extract file_path from the JSON — pipe via stdin to avoid shell injection
# Claude Code stdin format: {"tool_input": {"file_path": "..."}, ...}
# Manual test format: {"file_path": "..."}
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
        "Not available (path guard is foundational)" \
        "docs/GOVERNANCE_QUICKSTART.md"
fi

# Normalise Windows backslashes to forward slashes for path comparison
FILE_PATH="${FILE_PATH//\\//}"

# Convert Windows drive letter prefix (d:/) to MSYS2/Git Bash format (/d/)
if [[ "$FILE_PATH" =~ ^([a-zA-Z]):/ ]]; then
    DRIVE="${BASH_REMATCH[1],,}"
    FILE_PATH="/${DRIVE}/${FILE_PATH:3}"
fi

# Strip absolute repo-root prefix to get relative path
REL_ROOT="${REPO_ROOT//\\//}"
REL_PATH="${FILE_PATH#"$REL_ROOT/"}"

# If path was not absolute or didn't contain repo root, use as-is
# This handles the case where Claude passes a relative path directly
if [ "$REL_PATH" = "$FILE_PATH" ]; then
    # No repo-root prefix stripped — path is either relative or absolute to a different root.
    # After drive-letter normalisation (lines above), all absolute paths start with '/'.
    # An absolute path that is not under REPO_ROOT is OUTSIDE the repository;
    # path_guard.py is an in-repo governance tool and must not apply to it.
    if [[ "$FILE_PATH" = /* ]]; then
        # Absolute path not under repo root — out-of-repo write (DR-04: block by default).
        # Allow only explicit operator-approved external paths.
        _OOR_ALLOWED=0
        for _oor_prefix in \
            "$HOME/.claude/plans/" \
            "$HOME/.claude/projects/"; do
            if [[ "$FILE_PATH" == "$_oor_prefix"* ]]; then
                _OOR_ALLOWED=1
                break
            fi
        done
        unset _oor_prefix
        if [ "$_OOR_ALLOWED" = "1" ]; then
            unset _OOR_ALLOWED
            exit 0
        fi
        unset _OOR_ALLOWED
        _gov_block "Write denied — path is outside repository root." \
            "$FILE_PATH is not under repo root and not in external allowlist." \
            "Use a path under the repository, or ~/.claude/plans/, ~/.claude/projects/." \
            "Not available (path guard is foundational)" \
            "docs/GOVERNANCE_QUICKSTART.md"
    fi
    # Relative path — strip any leading ./
    REL_PATH="${REL_PATH#./}"
fi

# Run path_guard.py on the relative path
GUARD_EXIT=0
GUARD_OUTPUT=$("$PYTHON" "$REPO_ROOT/scripts/pipeline/commands/governance/path_guard.py" "$REL_PATH" 2>/dev/null) || GUARD_EXIT=$?

if [ $GUARD_EXIT -eq 0 ]; then
    # ALLOW
    exit 0
fi

# --- Token-aware PreToolUse (GOV-LIGHT-001) ---
# If a valid pending override token covers this exact path, allow the write.
# The pre-commit hook will independently re-validate the token at commit time.
_TOKEN_EXIT=0
"$PYTHON" "$REPO_ROOT/scripts/pipeline/commands/governance/override_manager.py" \
    validate-for-path "$REL_PATH" >/dev/null 2>&1 || _TOKEN_EXIT=$?
if [ "$_TOKEN_EXIT" = "0" ]; then
    _AUDIT_DIR="$REPO_ROOT/reports/overrides"
    mkdir -p "$_AUDIT_DIR"
    printf '%s|%s|OVERRIDE_TOKEN_PRETOOLUSE|write-allowed\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$REL_PATH" \
        >> "$_AUDIT_DIR/pretooluse-audit.log"
    echo "Override token covers $REL_PATH — write allowed (pre-commit will re-validate)" >&2
    exit 0
fi

# DENY — check for human authorization bypass
if [ "${ROOT_WRITE_AUTHORIZED:-0}" = "1" ]; then
    # Operator has explicitly authorized this write — log it and allow
    AUDIT_DIR="$REPO_ROOT/reports/root-writes"
    mkdir -p "$AUDIT_DIR"
    printf '%s|%s|ROOT_WRITE_AUTHORIZED|operator-bypass\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$REL_PATH" \
        >> "$AUDIT_DIR/audit.log"
    echo "⚠️  ROOT_WRITE_AUTHORIZED bypass used for: $REL_PATH (logged to reports/root-writes/audit.log)" >&2
    exit 0
fi

# Block the write
_gov_block "Write denied — $REL_PATH not in allowed path list." \
    "$GUARD_OUTPUT" \
    "Move file to an allowed path, or create an override token for forbidden paths." \
    "ROOT_WRITE_AUTHORIZED=1 (root-level only, audited) | Override token (forbidden paths)" \
    "docs/BYPASS_REGISTRY.md, docs/GOVERNANCE_QUICKSTART.md"
