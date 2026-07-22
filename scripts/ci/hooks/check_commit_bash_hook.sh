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
#   CHECK_COMMIT_HOOK_ROOT_OVERRIDE — test-harness-only root redirection seam.
#   Agents MUST NOT set it: pointing it at a fabricated context directory is
#   functionally a bypass and is treated as a governance violation, same as
#   SKIP_* variables (AGENTS.md §11).
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

# Test seam (HARDEN-A3/F8): the test suite points the governance-state lookups at
# an isolated root so tests never read or mutate the LIVE repo's skill contexts
# (which could transiently yank a concurrent session's commit authorization).
# Not a bypass — every check still runs, just against the given root.
if [ -n "${CHECK_COMMIT_HOOK_ROOT_OVERRIDE:-}" ]; then
    REPO_ROOT="$CHECK_COMMIT_HOOK_ROOT_OVERRIDE"
fi

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

# HARDEN-A3/F2 round 2: normalize CRs first — the extraction Python's text-mode
# stdout emits \r\n on Windows, and a CR between backslash and LF defeats the
# continuation join below (and pollutes line matching generally).
COMMAND="${COMMAND//$'\r'/}"
# Join backslash-newline continuations — otherwise `git \` + newline + `commit`
# splits across lines and no single line matches. The pattern must be a QUOTED
# variable expansion: unquoted, the backslash in the pattern acts as an escape
# and only the newline gets replaced.
_bsnl=$'\\\n'
COMMAND="${COMMAND//"$_bsnl"/ }"

while IFS= read -r _line; do
    # Strip leading whitespace
    _stripped="${_line#"${_line%%[![:space:]]*}"}"
    [ -z "$_stripped" ] && continue
    [[ "$_stripped" == \#* ]] && continue

    # Match `git commit` but NOT `git commit-tree` or `git commit-graph` (plumbing).
    # HARDEN-A3/F2 (2 rounds): see through every prefix/infix form found to be a
    # full bypass of this hook:
    #   env-var assignments (AGENT_SESSION_ID=x git commit), quoted values
    #   (GIT_AUTHOR_NAME="John Doe" git commit), subshell parens ((git commit)),
    #   command/env words incl. options and interleaving (command git commit,
    #   env -i git commit, command -p git commit, VAR=1 command git commit),
    #   backslash-escaped word (\git commit), and git global options between git
    #   and the subcommand (git -c user.email=x commit, git --no-pager commit).
    # One repeated alternation covers word/assignment prefixes in ANY order.
    _PREFIX_RE="(\\(|[[:space:]])*((command|env)([[:space:]]+-[A-Za-z-]+)*[[:space:]]+|[A-Za-z_][A-Za-z0-9_]*=(\"[^\"]*\"|'[^']*'|[^[:space:]]*)[[:space:]]+)*"
    # Option alternatives: short-with-arg (-c x, -C dir), long-with-arg
    # (--git-dir /x), bare/equals (--no-pager, --exec-path=/x). POSIX ERE
    # match-if-possible semantics mean extra alternatives can only over-match
    # (detect MORE commits — fail-closed), never under-match.
    _GIT_OPTS_RE="([[:space:]]+(-[A-Za-z][[:space:]]+[^[:space:]]+|--[A-Za-z-]+[[:space:]]+[^[:space:]-][^[:space:]]*|--?[A-Za-z0-9][A-Za-z0-9=./_-]*))*"
    if echo "$_stripped" | grep -qE "(^|[;|&])[[:space:]]*${_PREFIX_RE}\\\\?git${_GIT_OPTS_RE}[[:space:]]+commit([[:space:]]|\$)"; then
        # Exclude plumbing commands that start with `commit-`
        if echo "$_stripped" | grep -qE "(^|[;|&])[[:space:]]*${_PREFIX_RE}\\\\?git${_GIT_OPTS_RE}[[:space:]]+commit-"; then
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
# git commit detected — session-identity-aware S-76 check (HARDEN-A3)
#
# The old check answered only "is SOME S-76 context active anywhere" — with
# concurrent sessions, session A's live /commit context let session B's raw
# `git commit` through. Now:
#   - `AGENT_SESSION_ID=<id> git commit ...` (or the id in the hook's env):
#     THAT session must hold a live S-76 context (per-session file, or the
#     legacy ACTIVE.json when it carries no session claim).
#   - No identity given: allowed only when exactly ONE live S-76 context
#     exists repo-wide (the single-session case, unchanged). Two or more is
#     ambiguous -> fail-closed with both named.
# Existing fail-open cases (no input, no python) are unchanged above.
# ---------------------------------------------------------------------------

VERDICT=$("$PYTHON" -c "
import json, os, re, sys
from datetime import datetime, timezone
from pathlib import Path

repo = Path(sys.argv[1])
command = sys.argv[2]
ctx_dir = repo / 'reports' / 'skill-context'
active_file = ctx_dir / 'ACTIVE.json'
active_dir = ctx_dir / 'active'

def load(p):
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return None

def live(rec):
    if not rec:
        return False
    try:
        started = datetime.fromisoformat(rec.get('started_at', '').replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        return False
    ttl = 1800 if rec.get('context_type') == 'gap_approved' else 7200
    return (datetime.now(timezone.utc) - started).total_seconds() <= ttl

def is_s76(rec):
    return bool(rec) and rec.get('skill_id') == 'S-76' and live(rec)

m = re.search(r'(?:^|[\s;&|(])AGENT_SESSION_ID=([A-Za-z0-9_.-]+)', command)
sid = m.group(1) if m else os.environ.get('AGENT_SESSION_ID', '').strip()

if sid:
    if is_s76(load(active_dir / (sid + '.json'))):
        print('ALLOW')
        sys.exit(0)
    legacy = load(active_file)
    if is_s76(legacy) and legacy.get('session_id') in (None, sid):
        print('ALLOW')
        sys.exit(0)
    print('BLOCK:session ' + sid + ' holds no live S-76 context')
    sys.exit(0)

holders = []
if is_s76(load(active_file)):
    holders.append('legacy-ACTIVE.json')
if active_dir.exists():
    for p in sorted(active_dir.glob('*.json')):
        if is_s76(load(p)):
            holders.append(p.stem)
if len(holders) == 1:
    print('ALLOW')
elif not holders:
    print('BLOCK:no live S-76 context')
else:
    print('BLOCK:AMBIGUOUS — multiple live S-76 contexts (' + ', '.join(holders) + '); rerun as AGENT_SESSION_ID=<yours> git commit ...')
" "$REPO_ROOT" "$COMMAND" 2>/dev/null) || VERDICT=""

if [ "$VERDICT" = "ALLOW" ]; then
    exit 0
fi

# Fail-open only if the verdict computation itself broke (no output at all)
if [ -z "$VERDICT" ]; then
    exit 0
fi

BLOCK_REASON="${VERDICT#BLOCK:}"

# Block: git commit without (this session's) S-76 context
_gov_block "Bash denied — direct git commit is not allowed. ($BLOCK_REASON)" \
    "Content commits must use the /commit skill (S-76), not direct git commit. With concurrent sessions, pass your identity: AGENT_SESSION_ID=<id> git commit ..." \
    "Invoke /commit --force-all --hint \"description of changes\"" \
    "SKIP_COMMIT_BASH_CHECK=1 (operator only)" \
    "CLAUDE.md (Behavioral Mandates)" \
    '{"violation_type": "direct_git_commit", "unblock_condition": "use /commit skill (S-76) with AGENT_SESSION_ID identity instead of direct git commit"}'
