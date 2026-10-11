#!/usr/bin/env bash
# check_destructive_bash_hook.sh — PreToolUse Bash hook for destructive operation governance.
#
# Invoked by Claude Code's PreToolUse hook when the Bash tool is called.
# Blocks high-blast-radius destructive operations that are hard to reverse.
#
# Blocked operations (exit 2):
#   git reset (ANY form)   — bare, HEAD, --soft/--mixed/--hard, any target,
#                             with or without a `-- <file>` suffix. No allowed
#                             forms via the Bash tool (closed 2026-07-15 after a
#                             concurrent-session `git reset` emptied a commit's
#                             index mid-hook and pushed an empty commit to main,
#                             b860c6fb92). Use `git restore --staged <path>` to
#                             unstage, or `git checkout <sha> -- <path>` to
#                             restore file content, instead. The one legitimate
#                             git-reset caller in this codebase — clone_cache.py's
#                             guarded `git reset --hard origin/HEAD` — runs via
#                             subprocess.run(), never the Bash tool, so it never
#                             reaches this hook and needs no special-casing here.
#   git clean -f           (destroys untracked files; -n dry-run is allowed)
#   git push --force/-f    (force-push to main/master)
#   git checkout -- .      (resets all tracked files to HEAD)
#   git rm (without -n)    (stages deletion of tracked files)
#   find ... -delete       (find with -delete flag)
#   rm -rf /               (system-level mass deletion)
#   rm -rf ~               (home directory mass deletion)
#   Remove-Item -Recurse on root or home paths (PowerShell)
#   hugo -d public*    (relative destination writes artifacts into repo root)
#
# Allowed despite destructive appearance:
#   git push --force-with-lease   (safe force: checks remote state first)
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

    # --- git reset (ANY form — blanket prohibition, no exceptions) ---
    # A concurrent-session `git reset` mid-commit produced an empty commit on
    # main (2026-07-14, b860c6fb92). All forms are blocked: bare `git reset`,
    # `git reset HEAD`, --soft/--mixed/--hard, any target, with or without a
    # `-- <file>` suffix. Use `git restore --staged <path>` to unstage, or
    # `git checkout <sha> -- <path>` to restore file content, instead.
    if echo "$_stripped" | grep -qE '(^|[;|&])\s*git\s+reset(\s|$)'; then
        _block "$_stripped" "git reset is prohibited in any form -- use git restore --staged <path> to unstage, or git checkout <sha> -- <path> to restore file content"
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

    # --- hugo with relative public* destination (TC-HUGO-03) ---
    # Blocked: hugo ... -d public<anything>  or  --destination public<anything>
    # These write build artifacts into the repo root, bloating git status.
    # Allowed: hugo server (no -d), hugo ... -d /tmp/..., hugo ... -d $(mktemp -d)
    # Reference: scripts/ci/hooks/check_hugo_build.sh uses mktemp -d correctly.
    if echo "$_stripped" | grep -qE '(^|[;|&])\s*hugo\b'; then
        if echo "$_stripped" | grep -qE -- '(-d|--destination)[[:space:]]+public'; then
            _block "$_stripped" "hugo with a relative 'public*' destination writes build output into the repo root -- use a system temp dir instead: tmpdir=\$(mktemp -d) then hugo -d \"\$tmpdir\". See docs/governance/write-boundaries.md \u00a7Hugo Output Discipline."
        fi
    fi

done <<< "$COMMAND"

exit 0
