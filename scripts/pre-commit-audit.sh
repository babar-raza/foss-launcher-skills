#!/bin/bash
# Pre-commit hook: enforce path guard and verify API accuracy in staged content files.
# Install: cp scripts/pre-commit-audit.sh .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit

# ---------------------------------------------------------------------------
# Step 0: reports/ boundary — local-only artifacts must never be committed
# ---------------------------------------------------------------------------
# reports/ is gitignored and is a strict local-only boundary. Any staged
# addition or modification under reports/ is an error (usually caused by
# git add -f bypassing .gitignore). Deletions (git rm --cached) are allowed
# so that the cleanup commit can untrack already-committed files.
staged_reports=$(git diff --cached --name-only --diff-filter=ACM | grep '^reports/')
if [ -n "$staged_reports" ]; then
    echo "ERROR: Staged files under reports/ violate the local-only artifact boundary:"
    echo "$staged_reports"
    echo ""
    echo "reports/ is gitignored. Do not use 'git add -f' to stage files under reports/."
    echo "Override tokens are validated from disk (reports/overrides/pending/) — do not stage them."
    exit 1
fi

# ---------------------------------------------------------------------------
# Step 1: Forbidden-path enforcement
# ---------------------------------------------------------------------------
# For every staged file, check path_guard.py. If DENY, require a valid pending
# override token in reports/overrides/pending/ (via override_manager.py).
forbidden_staged=()
while IFS= read -r staged_file; do
    [ -z "$staged_file" ] && continue
    python scripts/pipeline/path_guard.py "$staged_file" > /dev/null 2>&1
    if [ $? -eq 2 ]; then
        forbidden_staged+=("$staged_file")
    fi
done < <(git diff --cached --name-only --diff-filter=ACM)

if [ ${#forbidden_staged[@]} -gt 0 ]; then
    forbidden_violation=0
    for staged_file in "${forbidden_staged[@]}"; do
        echo "Forbidden path staged: $staged_file"
        python scripts/pipeline/override_manager.py validate-for-path "$staged_file" 2>&1
        if [ $? -ne 0 ]; then
            forbidden_violation=1
        fi
    done
    if [ $forbidden_violation -ne 0 ]; then
        echo ""
        echo "BLOCKED: One or more staged files are in forbidden paths and have no override token."
        echo "  Create an override token before committing:"
        echo "    python scripts/pipeline/override_manager.py create \\"
        echo "      --paths <path> --reason '...' --plan '...'"
        echo "  The token is auto-validated from reports/overrides/pending/ — do NOT stage it."
        exit 1
    fi
fi

# ---------------------------------------------------------------------------
# Step 2: API accuracy audit on staged English content files
# ---------------------------------------------------------------------------
# Locale files (/ar/, /fr/, /de/, etc.) are translator output and are not
# subject to API accuracy audit — only English source pages are checked.
mapfile -t changed < <(
    git diff --cached --name-only --diff-filter=ACM \
        | grep '^content/.*\.md$' \
        | grep '/en/'
)
[ ${#changed[@]} -eq 0 ] && exit 0

echo "Running content API audit on staged files (${#changed[@]} English pages)..."
# Use --files-from to avoid OS argument-list-too-long errors on large commits.
_tmpfile=$(mktemp /tmp/audit-files-XXXXXX.txt 2>/dev/null || mktemp)
printf '%s\n' "${changed[@]}" > "$_tmpfile"
python scripts/pipeline/audit.py --files-from "$_tmpfile" --fail-fast
status=$?
rm -f "$_tmpfile"

if [ $status -ne 0 ]; then
    echo ""
    echo "BLOCKED: Content has API accuracy failures."
    echo "Fix the issues above, then re-stage and commit."
    exit 1
fi

echo "Content API audit passed."

# ---------------------------------------------------------------------------
# Step 3: Check plugin_platform canonical values for products pages
# ---------------------------------------------------------------------------
if git diff --cached --name-only --diff-filter=ACM | grep -q '^content/products\.aspose\.org/'; then
    echo "Running plugin_platform canonical-value check..."
    python scripts/ci/check_plugin_platform.py
    if [ $? -ne 0 ]; then
        echo ""
        echo "BLOCKED: plugin_platform has non-canonical values (see AGENTS.md Section 3b)."
        echo "Fix the values above, then re-stage and commit."
        exit 1
    fi
fi

exit 0
