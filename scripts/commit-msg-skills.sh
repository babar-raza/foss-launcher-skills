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

# Step 3: Optional — validate declared skills against pending skill run record
PENDING_RUN=$(python scripts/pipeline/skill_run_manager.py find-pending 2>/dev/null)
if [ -n "$PENDING_RUN" ]; then
    declared=$(echo "$msg" | grep -iE 'skills?\s*invoked' | sed 's/.*[Ss]kills\s*[Ii]nvoked[: ]*//' | tr -d '[]')
    validation_result=$(python scripts/pipeline/skill_run_manager.py validate \
        --run-id "$PENDING_RUN" --declared "$declared" 2>&1)
    validation_exit=$?
    if [ $validation_exit -ne 0 ]; then
        echo ""
        echo "WARNING: Declared skills do not match skill run record $PENDING_RUN."
        echo "$validation_result"
        echo "Run: python scripts/pipeline/skill_run_manager.py get-declared-skills --run-id $PENDING_RUN"
        echo "(This is a warning only -- commit is not blocked. Fix the declaration to match the record.)"
        echo ""
    fi
fi

exit 0
