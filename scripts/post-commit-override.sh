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

# 2026-08-29 (stale-guard plan T8): consume ONLY tokens whose paths intersect
# this commit's changed files. The previous per-token loop consumed EVERY
# pending token on ANY successful commit -- sampled live: 3 of the 40 most
# recently archived tokens were attributed to commits that never touched
# their paths, and a concurrent session's still-needed token could be swept
# out from under its own pending commit. The path-intersection decision lives
# in override_manager.py (consume-for-commit, unit-tested), not in bash.
"$_HOOK_PYTHON" scripts/pipeline/commands/governance/override_manager.py consume-for-commit \
    --commit-sha "$COMMIT_SHA"
