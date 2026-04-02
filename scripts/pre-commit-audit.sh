#!/bin/bash
# Pre-commit hook: enforce path guard and verify API accuracy in staged content files.
# Install: cp scripts/pre-commit-audit.sh .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit

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
        echo "  Then stage the token file (reports/overrides/pending/*.json) and commit together."
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
