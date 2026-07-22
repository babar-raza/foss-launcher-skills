#!/usr/bin/env bash
# check_skill_context_hook.sh — PreToolUse Edit/Write hook for skill-context governance.
#
# Invoked by Claude Code's PreToolUse hook when Edit or Write is called.
# Claude Code pipes hook input as JSON to stdin (see hooks.md).
#
# Behavior:
#   - If the target file_path is under a governed path (content/, scripts/pipeline/,
#     scripts/ci/, knowledge/, data/), requires an active skill context at
#     reports/skill-context/ACTIVE.json.
#   - Ungoverned paths (reports/, plans/, backlog/, .claude/plans/) are always allowed.
#   - Exits 2 (block) if no active context or file is outside skill scope.
#   - Exits 0 for ungoverned paths or when skill context covers the file.
#   - **Fail-closed**: any parse error or missing input blocks the edit.
#
# Exit codes (Claude Code PreToolUse semantics):
#   0 = allow (tool executes)
#   2 = block (tool is denied, stderr shown to agent)
#
# Wiring (in .claude/settings.json):
#   Add to both Edit and Write PreToolUse hook arrays.

set -euo pipefail

# Operator-only bypass (not documented in agent-visible files)
if [ "${SKIP_SKILL_CONTEXT_CHECK:-0}" = "1" ]; then
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
    _gov_block "Edit/Write denied — .venv is broken or missing." \
        "Cannot resolve Python to inspect skill context." \
        "rm -rf .venv && python -m venv .venv && pip install -r scripts/ci/requirements.txt" \
        "SKIP_SKILL_CONTEXT_CHECK=1" \
        "docs/GOVERNANCE_QUICKSTART.md"
fi

# Read tool input JSON from stdin (Claude Code pipes PreToolUse JSON to stdin)
# Also check CLAUDE_TOOL_INPUT env var for manual testing compatibility
TOOL_INPUT="${CLAUDE_TOOL_INPUT:-}"

if [ -z "$TOOL_INPUT" ]; then
    TOOL_INPUT=$(cat 2>/dev/null || true)
fi

if [ -z "$TOOL_INPUT" ]; then
    # Fail-closed: no input means we cannot verify — block
    _gov_block "Edit/Write denied — no tool input available." \
        "Cannot determine file path from empty input (fail-closed)." \
        "Retry the Edit/Write tool call." \
        "SKIP_SKILL_CONTEXT_CHECK=1" \
        "docs/GOVERNANCE_QUICKSTART.md"
fi

# Extract file_path from the JSON — pipe via stdin to avoid shell injection
# Claude Code stdin format: {"tool_input": {"file_path": "..."}, ...}
# Manual test format: {"file_path": "..."}
# We support both by checking tool_input.file_path first, then file_path
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
    _gov_block "Edit/Write denied — could not parse file_path." \
        "JSON parse failure (fail-closed)." \
        "Retry the Edit/Write tool call." \
        "SKIP_SKILL_CONTEXT_CHECK=1" \
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

# Strip absolute repo-root prefix to get relative path (handles Windows paths)
REL_ROOT="${REPO_ROOT//\\//}"
FILE_PATH="${FILE_PATH#"$REL_ROOT/"}"

# If the path was not stripped (still absolute), the file lives outside the repo.
# DR-04: block out-of-repo writes by default; allow only approved external paths.
if [[ "$FILE_PATH" == /* ]]; then
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
    _gov_block "Edit/Write denied — path is outside repository root." \
        "$FILE_PATH is not under repo root and not in external allowlist." \
        "Use a path under the repository, or ~/.claude/plans/, ~/.claude/projects/." \
        "SKIP_SKILL_CONTEXT_CHECK=1" \
        "docs/GOVERNANCE_QUICKSTART.md"
fi

# Classify path as governed or ungoverned
# Ungoverned paths — always allowed without skill context
if [[ "$FILE_PATH" == reports/* ]] || \
   [[ "$FILE_PATH" == plans/* ]] || \
   [[ "$FILE_PATH" == backlog/* ]] || \
   [[ "$FILE_PATH" == .claude/plans/* ]] || \
   [[ "$FILE_PATH" == */plans/* ]] || \
   [[ "$FILE_PATH" == tests/* ]]; then
    exit 0
fi

# --- Governance maintenance mode (TC-GOV-03) ---
# When GOV_MAINTENANCE_MODE=1 + GOV_MAINTENANCE_PLAN + GOV_BYPASS_REASON are all set,
# allow edits to scripts/ci/ and scripts/pipeline/ without active skill context.
# This enables governance-layer maintenance (hook edits, pipeline fixes) under audit.
if [ "${GOV_MAINTENANCE_MODE:-0}" = "1" ]; then
    _mm_plan="${GOV_MAINTENANCE_PLAN:-}"
    _mm_reason="${GOV_BYPASS_REASON:-}"
    if [ -n "$_mm_plan" ] && [ -n "$_mm_reason" ]; then
        if [[ "$FILE_PATH" == scripts/ci/* ]] || \
           [[ "$FILE_PATH" == scripts/pipeline/* ]] || \
           [[ "$FILE_PATH" == scripts/maintenance/* ]]; then
            # Audit log
            _log_dir="reports/overrides"
            mkdir -p "$_log_dir"
            echo "timestamp_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ) event=maintenance_mode_edit bypass=GOV_MAINTENANCE_MODE taskcard=$_mm_plan reason=\"$_mm_reason\" file=$FILE_PATH result=allowed" >> "$_log_dir/env-bypasses.log"
            echo "WARN: Governance maintenance mode active (plan=$_mm_plan) — allowing $FILE_PATH" >&2
            exit 0
        fi
    else
        _gov_block "GOV_MAINTENANCE_MODE=1 set but missing required context." \
            "Both GOV_MAINTENANCE_PLAN and GOV_BYPASS_REASON must be set." \
            "export GOV_MAINTENANCE_PLAN=TC-XX GOV_BYPASS_REASON='reason'" \
            "Complete the 3-var model (all three env vars required)." \
            "docs/BYPASS_REGISTRY.md"
    fi
fi

# Governed paths — require active skill context
# .github/workflows/ is also governed: CI changes need skill context + pre-commit
# override token (enforced by git hook at commit time, not here at edit time).
GOVERNED=false
if [[ "$FILE_PATH" == content/* ]] || \
   [[ "$FILE_PATH" == scripts/pipeline/* ]] || \
   [[ "$FILE_PATH" == scripts/ci/* ]] || \
   [[ "$FILE_PATH" == scripts/maintenance/* ]] || \
   [[ "$FILE_PATH" == knowledge/* ]] || \
   [[ "$FILE_PATH" == data/* ]] || \
   [[ "$FILE_PATH" == .github/workflows/* ]] || \
   [[ "$FILE_PATH" == docs/governance/* ]] || \
   [[ "$FILE_PATH" == docs/workflows/* ]] || \
   [[ "$FILE_PATH" == docs/registries/* ]] || \
   [[ "$FILE_PATH" == CODEX.md ]] || \
   [[ "$FILE_PATH" == OPERATOR_GUIDE.md ]]; then
    GOVERNED=true
fi

# Non-governed, non-ungoverned paths — run path_guard.py to catch root-level and other
# non-allowlisted targets.  Paths that are in the allowlist (e.g. docs/, backlog/, reports/)
# are allowed; paths that are not in the allowlist (e.g. bare repo-root files) are blocked.
if [ "$GOVERNED" != "true" ]; then
    # PYTHON already resolved via find_python.sh at script start (DR-01)
    GUARD_EXIT=0
    "$PYTHON" "$REPO_ROOT/scripts/pipeline/commands/governance/path_guard.py" "$FILE_PATH" >/dev/null 2>&1 || GUARD_EXIT=$?
    if [ $GUARD_EXIT -ne 0 ]; then
        # --- Token-aware PreToolUse (GOV-LIGHT-002) ---
        _TOKEN_EXIT=0
        "$PYTHON" "$REPO_ROOT/scripts/pipeline/commands/governance/override_manager.py" \
            validate-for-path "$FILE_PATH" >/dev/null 2>&1 || _TOKEN_EXIT=$?
        if [ "$_TOKEN_EXIT" = "0" ]; then
            _AUDIT_DIR="$REPO_ROOT/reports/overrides"
            mkdir -p "$_AUDIT_DIR"
            printf '%s|%s|OVERRIDE_TOKEN_PRETOOLUSE|edit-allowed\n' \
                "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$FILE_PATH" \
                >> "$_AUDIT_DIR/pretooluse-audit.log"
            echo "Override token covers $FILE_PATH — edit allowed (pre-commit will re-validate)" >&2
            exit 0
        fi
        _gov_block "Edit/Write denied — $FILE_PATH is not in the allowed path list." \
            "Root-level files and non-allowlisted paths are blocked." \
            "Move file to an allowlisted path (scripts/, content/, reports/, etc.)." \
            "SKIP_SKILL_CONTEXT_CHECK=1" \
            "scripts/pipeline/commands/governance/path_guard.py for the allowed path list" \
            '{"violation_type": "forbidden_path", "unblock_condition": "move file to an allowlisted path (scripts/, content/, reports/, backlog/, plans/, etc.)"}'
    fi
    exit 0
fi

ACTIVE_FILE="$REPO_ROOT/reports/skill-context/ACTIVE.json"
# RPR-G-03: per-session contexts live here (opt-in --session-id). A session on the OCC
# path has no legacy ACTIVE.json, so the marker check accepts either. With no session
# files present this is byte-identical to the previous behavior.
ACTIVE_DIR="$REPO_ROOT/reports/skill-context/active"

# Fast check: does a context marker exist (legacy ACTIVE.json OR any per-session file)?
if [ ! -f "$ACTIVE_FILE" ] && ! ls "$ACTIVE_DIR"/*.json >/dev/null 2>&1; then
    _gov_block "Edit/Write denied — no active skill context." \
        "$FILE_PATH is under a governed path and requires skill context." \
        "Invoke a registered skill that covers this file." \
        "SKIP_SKILL_CONTEXT_CHECK=1 (operator only)" \
        "AGENTS.md §6a (Skill-First Execution Mandate)" \
        '{"violation_type": "no_active_context", "unblock_condition": "run skill_context.py begin --skill S-xx --scope \"<glob>\""}'  
fi

# Scope validation: check if the file is within the active skill's scope
# Use `|| true` idiom to capture non-zero exit codes under `set -e`
CHECK_EXIT=0
PYTHONPATH="$REPO_ROOT/scripts/pipeline" "$PYTHON" "$REPO_ROOT/scripts/pipeline/commands/governance/skill_context.py" \
    check --file "$FILE_PATH" 2>/dev/null || CHECK_EXIT=$?

if [ $CHECK_EXIT -eq 0 ]; then
    # File is in scope — record touch with skill+session attribution (best-effort,
    # non-blocking). HARDEN-A3/F1: session-aware. The old block read skill_id ONLY
    # from legacy ACTIVE.json, so a session on the per-session path (AGENT_SESSION_ID
    # exported — now the default) had no ACTIVE.json, recording silently stopped,
    # ledgers starved, and agents were pushed toward `adopt --all` — re-opening the
    # exact cross-session sweep A2 guards against. Attribution order: env identity's
    # per-session context > legacy ACTIVE.json > sole live per-session file.
    ATTRIB=$("$PYTHON" -c "
import json, os, sys
from pathlib import Path
ctx_dir = Path(sys.argv[1])
active_file = ctx_dir / 'ACTIVE.json'
active_dir = ctx_dir / 'active'

def load(p):
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return None

sid = os.environ.get('AGENT_SESSION_ID', '').strip()
rec = load(active_dir / (sid + '.json')) if sid else None
if rec is None:
    legacy = load(active_file)
    if legacy:
        rec = legacy
        sid = legacy.get('session_id', '') or sid
if rec is None and active_dir.exists():
    files = sorted(active_dir.glob('*.json'))
    if len(files) == 1:
        rec = load(files[0])
        sid = files[0].stem
if rec and rec.get('skill_id'):
    print(rec.get('skill_id') + '\t' + (sid or ''))
" "$REPO_ROOT/reports/skill-context" 2>/dev/null || true)
    if [ -n "$ATTRIB" ]; then
        ACTIVE_SKILL="${ATTRIB%%$'\t'*}"
        ATTRIB_SID="${ATTRIB#*$'\t'}"
        _REC_ARGS=(record --file "$FILE_PATH" --action modified --skill "$ACTIVE_SKILL")
        if [ -n "$ATTRIB_SID" ] && [ "$ATTRIB_SID" != "$ATTRIB" ]; then
            _REC_ARGS+=(--session-id "$ATTRIB_SID")
        fi
        PYTHONPATH="$REPO_ROOT/scripts/pipeline" "$PYTHON" \
            "$REPO_ROOT/scripts/pipeline/commands/ops/session_ledger.py" \
            "${_REC_ARGS[@]}" 2>/dev/null || true
    fi
    exit 0
elif [ $CHECK_EXIT -eq 2 ]; then
    # No active context (stale expired during check)
    _gov_block "Edit/Write denied — skill context expired." \
        "Skill context for $FILE_PATH has expired." \
        "Re-invoke the skill to refresh the context." \
        "SKIP_SKILL_CONTEXT_CHECK=1 (operator only)" \
        "AGENTS.md §6a (Skill-First Execution Mandate)" \
        '{"violation_type": "no_active_context", "unblock_condition": "re-invoke skill: skill_context.py begin --skill S-xx --scope \"<glob>\""}'  
else
    # File is outside scope
    ACTIVE_SKILL=$(printf '%s' "$(cat "$ACTIVE_FILE")" | "$PYTHON" -c "
import json, sys
try:
    print(json.load(sys.stdin).get('skill_id', 'unknown'))
except Exception:
    print('unknown')
" 2>/dev/null || echo "unknown")
    _gov_block "Edit/Write denied — file outside active skill scope." \
        "$FILE_PATH is not in scope of active skill $ACTIVE_SKILL." \
        "Widen the skill scope or invoke a different skill." \
        "SKIP_SKILL_CONTEXT_CHECK=1 (operator only)" \
        "AGENTS.md §6a (Skill-First Execution Mandate)" \
        '{"violation_type": "missing_skill_context", "unblock_condition": "widen scope: skill_context.py begin --skill S-xx --scope \"<broader-glob>\" or invoke a different skill"}'  
fi
