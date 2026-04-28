#!/bin/bash
# Commit-msg hook: verify content commits include "Skills invoked:" with valid IDs.
# Install: cp scripts/commit-msg-skills.sh .git/hooks/commit-msg && chmod +x .git/hooks/commit-msg
#
# Validates:
#   1. Presence of "Skills invoked:" field on content commits
#   2. That all S-{n} IDs are real IDs from the AGENTS.md §12 registry

# Only check commits that touch content files.
content_staged=$(git diff --cached --name-only --diff-filter=ACM 2>/dev/null | grep '^content/.*\.md$' | head -1)
[ -z "$content_staged" ] && exit 0

# --- Audited operator bypass (3-var model) ---
# Requires ALL THREE: SKIP_SKILL_COMMIT_CHECK=1 + GOV_BYPASS_TASKCARD + GOV_BYPASS_REASON
# Bare bypass (flag only) is rejected. See docs/BYPASS_REGISTRY.md.
if [ "${SKIP_SKILL_COMMIT_CHECK:-0}" = "1" ]; then
    _tc="${GOV_BYPASS_TASKCARD:-}"
    _reason="${GOV_BYPASS_REASON:-}"
    if [ -z "$_tc" ] || [ -z "$_reason" ]; then
        echo ""
        echo "BLOCKED: SKIP_SKILL_COMMIT_CHECK=1 set but missing required context."
        echo "REASON:  GOV_BYPASS_TASKCARD and GOV_BYPASS_REASON are mandatory for audited bypass."
        echo "FIX:     SKIP_SKILL_COMMIT_CHECK=1 GOV_BYPASS_TASKCARD=TC-GOV-XX GOV_BYPASS_REASON='reason' git commit ..."
        echo "BYPASS:  Not allowed without taskcard and reason."
        echo ""
        exit 1
    fi
    _repo="$(git rev-parse --show-toplevel)"
    _log="$_repo/reports/overrides/env-bypasses.log"
    _branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
    _head="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
    mkdir -p "$(dirname "$_log")"
    printf 'timestamp_utc=%s event=env_bypass bypass=SKIP_SKILL_COMMIT_CHECK taskcard=%s reason="%s" user=%s branch=%s head=%s files=%s result=allowed\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$_tc" "$_reason" "$(whoami)" "$_branch" "$_head" \
        "$(echo "$content_staged" | tr '\n' ';')" >> "$_log"
    echo "WARN: Skill commit check bypassed (taskcard=$_tc reason=$_reason)"
    exit 0
fi

# $1 is the commit message file.
if [ -z "$1" ] || [ ! -f "$1" ]; then
    exit 0
fi

msg=$(cat "$1")

# Step 1: Check for field presence
if ! echo "$msg" | grep -qiE 'skills?\s*invoked'; then
    echo ""
    echo "BLOCKED: Content commits must include 'Skills invoked: [S-xx, ...]' (AGENTS.md Section 10, Section 6a)."
    echo "Add a line like: Skills invoked: [S-19, S-23, S-24, S-01]"
    echo ""
    exit 1
fi

# Step 2: Validate that listed S-{n} IDs exist in the AGENTS.md §12 registry
echo "$msg" | python scripts/ci/validate_skill_ids.py --stdin
if [ $? -ne 0 ]; then
    echo ""
    echo "BLOCKED: One or more skill IDs in 'Skills invoked:' are not in the registry."
    echo "Check AGENTS.md §12 for the list of valid skill IDs."
    echo ""
    exit 1
fi

# Step 3: Validate declared skills against pending skill run record (BLOCKING).
# No bypass path — all content commits must have a matching skill run record.

PENDING_RUN=$(python scripts/pipeline/skill_run_manager.py find-pending 2>/dev/null)
if [ -n "$PENDING_RUN" ]; then
    declared=$(echo "$msg" | grep -iE 'skills?\s*invoked' | sed 's/.*[Ss]kills\s*[Ii]nvoked[: ]*//' | tr -d '[]')
    validation_result=$(python scripts/pipeline/skill_run_manager.py validate \
        --run-id "$PENDING_RUN" --declared "$declared" 2>&1)
    validation_exit=$?
    if [ $validation_exit -ne 0 ]; then
        echo ""
        echo "BLOCKED: Declared skills do not match skill run record $PENDING_RUN."
        echo "$validation_result"
        echo "Run: python scripts/pipeline/skill_run_manager.py get-declared-skills --run-id $PENDING_RUN"
        echo ""
        exit 1
    fi
else
    # No pending run record — BLOCKED. All content commits require skill run evidence.
    echo ""
    echo "BLOCKED: No skill run record found for this content commit."
    echo "  Content commits require a skill run record for provenance."
    echo "  Use /commit (S-76) to create auditable skill run records."
    echo ""
    exit 1
fi

exit 0
