#!/usr/bin/env bash
# check_add_bash_hook.sh — PreToolUse Bash hook, WARN-ONLY, for raw `git add`
# against the shared real .git/index.
#
# 2026-08-26 pipeline reliability hardening
# (reports/skill-gaps/2026-08-26-pipeline-reliability-hardening.md,
# backlog ST-021 update:2026-08-26): check_commit_bash_hook.sh (this file's
# sibling) already requires a live S-76 context before `git commit` -- but
# its pattern matcher only ever matched the literal word `commit`, never
# `add`. Raw `git add` against the real, shared index was completely
# unguarded -- confirmed live: this exact vector swept 26 files from a
# concurrent session's own mid-revert-in-progress into another session's
# `git diff --staged` output the same day this hook was written.
#
# This is deliberately WARN-ONLY, never blocking -- the same soft-launch
# posture this repo already established for git_plumb_commit.py's
# --strict-isolation flag (reports/skill-gaps/
# 2026-08-20-git-plumb-commit-tier1-mutation-safety.md, Phase 2c): a brand
# new safety check reached for at already-stressful concurrent-session
# moments must not be able to newly block an operation that would
# previously have succeeded, until there has been a real review window
# against live usage. Promoting this to a hard block is a separate,
# later decision once that review has happened -- not something this file
# should decide unilaterally.
#
# Warned (stderr message, command still allowed to run):
#   git add ...     (any form) when no live skill context exists for the
#                   resolving session identity -- i.e. exactly the
#                   ad-hoc/no-governance-context shape the incident above
#                   had, whether or not the target ends up in a commit.
#
# Never warned (matches, but intentionally not the risk this file targets):
#   git add-* would be a plumbing-style name if one existed -- no real git
#   subcommand starts with "add-", so no exclusion is needed (unlike
#   check_commit_bash_hook.sh's commit-tree/commit-graph exclusion).
#
# Fail-open design, matching check_commit_bash_hook.sh exactly: if
# CLAUDE_TOOL_INPUT is empty, cannot be parsed, or Python is unavailable,
# the hook exits 0 silently. This hook ALSO always exits 0 even when it
# finds something to warn about -- "fail-open" here additionally means
# "never block," not just "never crash the tool-call pipeline."
#
# Bypass:
#   SKIP_ADD_BASH_CHECK=1 — operator-only, suppresses the warning entirely
#   (not required for normal use, since this hook never blocks -- provided
#   for parity with its sibling hooks and for a genuinely noisy-warning
#   situation, e.g. a long batch of intentionally-raw `git add` calls
#   during a supervised recovery procedure).
#   CHECK_ADD_HOOK_ROOT_OVERRIDE — test-harness-only root redirection seam,
#   same PYTEST_CURRENT_TEST-gated design as check_commit_bash_hook.sh's
#   CHECK_COMMIT_HOOK_ROOT_OVERRIDE (see that file's comment for the full
#   rationale -- identical here).
#
# Exit codes: always 0 (this hook never blocks the tool call).
#
# Wiring: added to Bash PreToolUse array in .claude/settings.json AFTER
# check_commit_bash_hook.sh.

set -euo pipefail

# Operator-only bypass
if [ "${SKIP_ADD_BASH_CHECK:-0}" = "1" ]; then
    exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
LIB_DIR="$(cd "$SCRIPT_DIR/../../pipeline/lib" && pwd)"

# Test seam (mirrors check_commit_bash_hook.sh's CHECK_COMMIT_HOOK_ROOT_OVERRIDE
# exactly -- same PYTEST_CURRENT_TEST gate, same rationale, same non-bypass
# status: every check still runs, just against the given root).
if [ -n "${CHECK_ADD_HOOK_ROOT_OVERRIDE:-}" ] && [ -n "${PYTEST_CURRENT_TEST:-}" ]; then
    REPO_ROOT="$CHECK_ADD_HOOK_ROOT_OVERRIDE"
fi

source "$(dirname "${BASH_SOURCE[0]}")/find_python.sh" || true

TOOL_INPUT="${CLAUDE_TOOL_INPUT:-}"
if [ -z "$TOOL_INPUT" ]; then
    TOOL_INPUT=$(cat 2>/dev/null || true)
fi

# Fail-open: no input → cannot inspect → allow, no warning
if [ -z "$TOOL_INPUT" ]; then
    exit 0
fi

# Fail-open: no Python → cannot parse → allow, no warning
if [ -z "$PYTHON" ]; then
    exit 0
fi

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
    exit 0
fi

# ---------------------------------------------------------------------------
# Pattern matching: detect `git add` (porcelain) in the command.
# Reuses check_commit_bash_hook.sh's exact prefix/option regex machinery
# (env-var prefixes, subshells, command/env wrappers, git global options) --
# proven correct across multiple hardening rounds there; retargeted from
# "commit" to "add" rather than re-derived, so it inherits the same
# bypass-attempt coverage without re-solving already-solved edge cases.
# ---------------------------------------------------------------------------

_found_add=false

COMMAND="${COMMAND//$'\r'/}"
_bsnl=$'\\\n'
COMMAND="${COMMAND//"$_bsnl"/ }"

while IFS= read -r _line; do
    _stripped="${_line#"${_line%%[![:space:]]*}"}"
    [ -z "$_stripped" ] && continue
    [[ "$_stripped" == \#* ]] && continue

    _PREFIX_RE="(\\(|[[:space:]])*((command|env)([[:space:]]+-[A-Za-z-]+)*[[:space:]]+|[A-Za-z_][A-Za-z0-9_]*=(\"[^\"]*\"|'[^']*'|[^[:space:]]*)[[:space:]]+)*"
    _GIT_OPTS_RE="([[:space:]]+(-[A-Za-z][[:space:]]+[^[:space:]]+|--[A-Za-z-]+[[:space:]]+[^[:space:]-][^[:space:]]*|--?[A-Za-z0-9][A-Za-z0-9=./_-]*))*"
    if echo "$_stripped" | grep -qE "(^|[;|&])[[:space:]]*${_PREFIX_RE}\\\\?git${_GIT_OPTS_RE}[[:space:]]+add([[:space:]]|\$)"; then
        _found_add=true
        break
    fi
done <<< "$COMMAND"

if [ "$_found_add" != "true" ]; then
    exit 0
fi

# ---------------------------------------------------------------------------
# git add detected — check for ANY live skill context (not specifically
# S-76, unlike the commit hook: staging legitimately happens under several
# skills' own flows, e.g. S-73 manual-edit, before /commit is ever reached
# -- the risk this hook targets is "no governance context at all", not
# "wrong specific skill").
# ---------------------------------------------------------------------------

VERDICT=$("$PYTHON" -c "
import json, re, sys
from datetime import datetime, timezone
from pathlib import Path

repo = Path(sys.argv[1])
command = sys.argv[2]
lib_dir = sys.argv[3]
ctx_dir = repo / 'reports' / 'skill-context'
active_file = ctx_dir / 'ACTIVE.json'
active_dir = ctx_dir / 'active'

if lib_dir not in sys.path:
    sys.path.insert(0, lib_dir)
import session_identity

def load(p):
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return None

def live(rec):
    if not rec:
        return False
    raw = rec.get('last_touched_at') or rec.get('started_at', '')
    try:
        activity = datetime.fromisoformat(raw.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        return False
    ttl = 1800 if rec.get('context_type') == 'gap_approved' else 7200
    return (datetime.now(timezone.utc) - activity).total_seconds() <= ttl

m = re.search(r'(?:^|[\s;&|(])AGENT_SESSION_ID=([A-Za-z0-9_.-]+)', command)
inline_sid = m.group(1) if m else None
sid = session_identity.resolve_sanitized(explicit=inline_sid) or ''

if sid and live(load(active_dir / (sid + '.json'))):
    print('OK')
    sys.exit(0)
if live(load(active_file)):
    print('OK')
    sys.exit(0)
if active_dir.exists():
    for p in sorted(active_dir.glob('*.json')):
        if live(load(p)):
            print('OK')
            sys.exit(0)
print('WARN:no live skill context found for this git add')
" "$REPO_ROOT" "$COMMAND" "$LIB_DIR" 2>/dev/null) || VERDICT=""

if [ "$VERDICT" = "OK" ] || [ -z "$VERDICT" ]; then
    exit 0
fi

WARN_REASON="${VERDICT#WARN:}"
echo "⚠️  WARN: raw 'git add' with no active skill context detected ($WARN_REASON)." >&2
echo "   This repo runs multiple concurrent agent sessions against one shared .git/index" >&2
echo "   (ST-021) -- an ungoverned 'git add' can sweep in another session's in-flight" >&2
echo "   staged work, or have its own staged files swept into an unrelated commit." >&2
echo "   Prefer git_plumb_commit.py's isolated temp-index commit path (never touches" >&2
echo "   the real index) over raw git add/commit when working in this shared checkout." >&2
echo "   This is advisory only (not blocked) -- SKIP_ADD_BASH_CHECK=1 silences it." >&2
exit 0
