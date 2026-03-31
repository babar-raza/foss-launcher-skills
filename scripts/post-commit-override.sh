#!/bin/bash
# Post-commit hook: consume pending override tokens after a protected-path commit.
# Install: cp scripts/post-commit-override.sh .git/hooks/post-commit && chmod +x .git/hooks/post-commit
#
# After a commit permitted via override tokens, this hook consumes each pending
# token in reports/overrides/pending/ by calling override_manager.py consume,
# which moves it to archived/ and records the commit SHA.
# If no pending tokens exist, this hook exits silently.

PENDING_DIR="reports/overrides/pending"

[ -d "$PENDING_DIR" ] || exit 0
token_files=$(find "$PENDING_DIR" -maxdepth 1 -name "*.json" -not -name ".gitkeep" 2>/dev/null)
[ -z "$token_files" ] && exit 0

COMMIT_SHA=$(git rev-parse HEAD 2>/dev/null)
if [ -z "$COMMIT_SHA" ]; then
    echo "post-commit-override: could not get HEAD SHA -- tokens NOT consumed" >&2
    exit 0
fi

consumed=0
for token_file in $token_files; do
    token_id=$(basename "$token_file" .json)
    echo "Consuming override token: $token_id"
    python scripts/pipeline/override_manager.py consume \
        --token-id "$token_id" \
        --commit-sha "$COMMIT_SHA"
    if [ $? -eq 0 ]; then
        git add -f "reports/overrides/archived/${token_id}.json" 2>/dev/null || true
        consumed=$((consumed + 1))
    else
        echo "post-commit-override: failed to consume token $token_id" >&2
    fi
done

if [ $consumed -gt 0 ]; then
    echo "post-commit-override: consumed $consumed override token(s)."
    echo "  Stage the archived tokens: git add reports/overrides/archived/"
fi
