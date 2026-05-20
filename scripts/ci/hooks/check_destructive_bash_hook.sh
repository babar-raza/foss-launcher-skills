#!/usr/bin/env bash
# check_destructive_bash_hook.sh — PreToolUse Bash hook for destructive operation governance.
#
# Invoked by Claude Code's PreToolUse hook when the Bash tool is called.
# Blocks high-blast-radius destructive operations that are hard to reverse.
#
# Blocked operations (exit 2):
#   git reset --hard       (without a specific file — resets all tracked files)
#   git clean -f           (destroys untracked files; -n dry-run is allowed)
#   git push --force/-f    (force-push to main/master)
#   git checkout -- .      (resets all tracked files to HEAD)
#   git rm (without -n)    (stages deletion of tracked files)
#   git reset origin/HEAD  (mixed reset to remote — moves HEAD, unstages all)
#   git reset HEAD~N       (pops commits — destructive to branch pointer)
#   git reset <sha>        (moves HEAD to arbitrary commit — destructive)
#   find ... -delete       (find with -delete flag)
#   rm -rf /               (system-level mass deletion)
#   rm -rf ~               (home directory mass deletion)
#   Remove-Item -Recurse on root or home paths (PowerShell)
#
# Allowed despite destructive appearance:
#   git push --force-with-lease   (safe force: checks remote state first)
#   git reset --hard -- <file>    (specific file reset, not all-files reset)
#   git clean -n                  (dry-run: shows what would be deleted)
#   rm -rf reports/               (designated expendable output directories)
#   rm -rf runs/
#   rm -rf backlog/
#   rm -rf plans/
#   rm -rf .venv/                 (venv rebuild)
#
# Fail-open design: if CLAUDE_TOOL_INPUT is empty or command cannot be parsed,
# the hook exits 0. The venv bash hook (which runs first) already catches syntax
# issues. This hook only governs semantically destructive operations.
#
# Bypass:
#   SKIP_DESTRUCTIVE_BASH_CHECK=1 — operator-only, not for agent use
#
# Exit codes (Claude Code PreToolUse semantics):
#   0 = allow (tool executes)
#   2 = block (tool denied; stderr shown to agent)
#
# Wiring: added to Bash PreToolUse array in .claude/settings.json AFTER
# check_venv_bash_hook.sh (venv check runs first).

set -euo pipefail

# Operator-only bypass
if [ "${SKIP_DESTRUCTIVE_BASH_CHECK:-0}" = "1" ]; then
    exit 0
fi

# Determine repo root from script location (scripts/ci/ — two levels up)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# Resolve Python via shared resolver (venv-only, no python3 fallback — DR-01)
# If venv absent/broken: fail-open (cannot inspect command — same policy as venv bash hook)
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
# Pattern matching for destructive operations
# ---------------------------------------------------------------------------

_block() {
    _gov_block "Bash denied — destructive operation."         "$2"         "Ask the human operator to run it directly, or use a safer alternative."         "SKIP_DESTRUCTIVE_BASH_CHECK=1 (operator only)"         "docs/BYPASS_REGISTRY.md"
}

# Check each line of the command for destructive patterns
while IFS= read -r _line; do
    # Strip leading whitespace
    _stripped="${_line#"${_line%%[![:space:]]*}"}"
    [ -z "$_stripped" ] && continue
    [[ "$_stripped" == \#* ]] && continue

    # --- git reset --hard ---
    # Allowed: git reset --hard -- <specific-file>
    # Blocked: git reset --hard (no file), git reset --hard HEAD, git reset --hard <sha>
    if echo "$_stripped" | grep -qE '(^|[;|&])\s*git\s+reset\s+.*--hard'; then
        # Allow if followed by " -- " (specific file reset)
        if echo "$_stripped" | grep -qE -- '--hard\s+--\s+\S'; then
            continue
        fi
        _block "$_stripped" "git reset --hard resets all tracked files to the target commit"
    fi

    # --- git reset <remote-ref> (mixed/soft reset) ---
    if echo "$_stripped" | grep -qE '(^|[;|&])\s*git\s+reset\s+'; then
        if echo "$_stripped" | grep -qE '\borigin/|\brefs/remotes/'; then
            if ! echo "$_stripped" | grep -qE -- '(origin/\S+|refs/remotes/\S+)\s+--\s+\S'; then
                _block "$_stripped" "git reset to a remote ref (origin/HEAD, origin/main, etc.) moves HEAD and unstages all staged work; use git pull --rebase instead"
            fi
        fi
    fi

    # --- git reset HEAD~N or HEAD^ ---
    if echo "$_stripped" | grep -qE '(^|[;|&])\s*git\s+reset\s+'; then
        if echo "$_stripped" | grep -qE 'HEAD~[0-9]|HEAD\^'; then
            _block "$_stripped" "git reset HEAD~N pops commits off the local branch; requires explicit human approval"
        fi
    fi

    # --- git reset <sha> ---
    if echo "$_stripped" | grep -qE '(^|[;|&])\s*git\s+reset\s+[0-9a-f]{7,40}\b'; then
        if ! echo "$_stripped" | grep -qE '[0-9a-f]{7,40}\s+--\s+\S'; then
            _block "$_stripped" "git reset to a specific SHA moves HEAD; use git checkout <sha> -- <file> to restore individual files instead"
        fi
    fi

    # --- git clean -f / --force ---
    # Allowed: git clean -n (dry-run), git clean --dry-run
    if echo "$_stripped" | grep -qE '(^|[;|&])\s*git\s+clean\s+'; then
        if echo "$_stripped" | grep -qE -- '-n|--dry-run'; then
            continue
        fi
        if echo "$_stripped" | grep -qE -- '-f|--force'; then
            _block "$_stripped" "git clean -f destroys untracked files; use -n first to preview"
        fi
    fi

    # --- git push --force / -f to main or master ---
    # Allowed: git push --force-with-lease (safe force)
    if echo "$_stripped" | grep -qE '(^|[;|&])\s*git\s+push\s+'; then
        if echo "$_stripped" | grep -q 'force-with-lease'; then
            continue
        fi
        if echo "$_stripped" | grep -qE -- '--force|-f\b'; then
            if echo "$_stripped" | grep -qE 'main|master'; then
                _block "$_stripped" "force-push to main/master can overwrite shared history"
            fi
        fi
    fi

    # --- git checkout -- . or git checkout -- (all files) ---
    if echo "$_stripped" | grep -qE '(^|[;|&])\s*git\s+checkout\s+--\s+\.'; then
        _block "$_stripped" "git checkout -- . resets all tracked files to HEAD (mass discard)"
    fi

    # --- git rm without -n ---
    if echo "$_stripped" | grep -qE '(^|[;|&])\s*git\s+rm\b'; then
        if ! echo "$_stripped" | grep -qE -- '-n|--dry-run'; then
            _block "$_stripped" "git rm stages file deletion; use -n first to preview"
        fi
    fi

    # --- find ... -delete ---
    if echo "$_stripped" | grep -qE '(^|[;|&])\s*find\b.*-delete'; then
        _block "$_stripped" "find -delete permanently removes matched files"
    fi

    # --- rm -rf on system/home paths ---
    # Allowed: rm -rf reports/, runs/, backlog/, plans/, .venv/
    if echo "$_stripped" | grep -qE '(^|[;|&])\s*rm\s+.*-[a-zA-Z]*r[a-zA-Z]*f|rm\s+.*-[a-zA-Z]*f[a-zA-Z]*r'; then
        # Check for allowed expendable directories (safe to mass-delete)
        if echo "$_stripped" | grep -qE 'rm\s+.*-[rf]+\s+(reports/|runs/|backlog/|plans/|\.venv/|\.venv$)'; then
            continue
        fi
        # Block system-level and home-level mass deletion
        if echo "$_stripped" | grep -qE 'rm\s+.*-[rf]+\s+(\/\s*$|\/\s|~\/?\s*$|~\/?\s)'; then
            _block "$_stripped" "rm -rf on / or ~ destroys the system or home directory"
        fi
    fi

    # --- PowerShell Remove-Item -Recurse on root or home ---
    if echo "$_stripped" | grep -qi 'Remove-Item.*-Recurse\|Remove-Item.*-r\b'; then
        if echo "$_stripped" | grep -qE '(C:\\\\|/|~)' && echo "$_stripped" | grep -qEi 'Remove-Item\s+(C:\\\\|/\s|~)'; then
            _block "$_stripped" "Remove-Item -Recurse on root or home path destroys critical directories"
        fi
    fi

done <<< "$COMMAND"

exit 0
