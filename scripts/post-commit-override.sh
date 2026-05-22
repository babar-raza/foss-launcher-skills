#!/bin/bash
# Post-commit hook: consume pending override tokens after a protected-path commit.
# Install: cp scripts/post-commit-override.sh .git/hooks/post-commit && chmod +x .git/hooks/post-commit
#
# After a commit permitted via override tokens, this hook consumes each pending
# token in reports/overrides/pending/ by calling override_manager.py consume,
# which moves it to archived/ and records the commit SHA.
# Tokens are local-only artifacts (reports/ is gitignored). They are NOT staged
# or committed — the move to archived/ is a local filesystem operation only.
# If no pending tokens exist, this hook exits silently.

PENDING_DIR="reports/overrides/pending"

[ -d "$PENDING_DIR" ] || exit 0
token_files=$(find "$PENDING_DIR" -maxdepth 1 -name "*.json" -not -name ".gitkeep" 2>/dev/null)
[ -z "$token_files" ] && exit 0

# ---------------------------------------------------------------------------
# DR-01: Central .venv Python resolver — no system Python fallback.
# Mirrors the pattern used in pre-commit-audit.sh and commit-msg-skills.sh.
# When .venv is absent, skip token consumption with a diagnostic warning.
# ---------------------------------------------------------------------------
if [ -f ".venv/Scripts/python" ]; then
    _HOOK_PYTHON=".venv/Scripts/python"
elif [ -f ".venv/bin/python" ]; then
    _HOOK_PYTHON=".venv/bin/python"
else
    echo "[post-commit] WARN: .venv not found — override token consumption skipped." >&2
    echo "  Recovery: bash scripts/ci/hooks/repair_venv.sh" >&2
    exit 0
fi

COMMIT_SHA=$(git rev-parse HEAD 2>/dev/null)
if [ -z "$COMMIT_SHA" ]; then
    echo "post-commit-override: could not get HEAD SHA -- tokens NOT consumed" >&2
    exit 0
fi

consumed=0
for token_file in $token_files; do
    token_id=$(basename "$token_file" .json)
    echo "Consuming override token: $token_id"
    "$_HOOK_PYTHON" scripts/pipeline/commands/governance/override_manager.py consume \
        --token-id "$token_id" \
        --commit-sha "$COMMIT_SHA"
    if [ $? -eq 0 ]; then
        consumed=$((consumed + 1))
    else
        echo "post-commit-override: failed to consume token $token_id" >&2
    fi
done

if [ $consumed -gt 0 ]; then
    echo "post-commit-override: consumed $consumed override token(s). Archived locally (not staged)."
fi
