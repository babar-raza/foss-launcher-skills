#!/bin/bash
# Commit-msg hook: verify content commits include "Skills invoked:" (AGENTS.md Section 10).
# Install: cp scripts/commit-msg-skills.sh .git/hooks/commit-msg && chmod +x .git/hooks/commit-msg

# Only check commits that touch content files.
content_staged=$(git diff --cached --name-only --diff-filter=ACM 2>/dev/null | grep '^content/.*\.md$' | head -1)
[ -z "$content_staged" ] && exit 0

# $1 is the commit message file.
if [ -z "$1" ] || [ ! -f "$1" ]; then
    exit 0
fi

msg=$(cat "$1")

if ! echo "$msg" | grep -qiE 'skills?\s*invoked'; then
    echo ""
    echo "BLOCKED: Content commits must include 'Skills invoked: [S-xx, ...]' (AGENTS.md Section 10, Section 6a)."
    echo "Add a line like: Skills invoked: [S-19, S-23, S-24, S-01]"
    echo ""
    exit 1
fi

exit 0
