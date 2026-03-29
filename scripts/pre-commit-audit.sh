#!/bin/bash
# Pre-commit hook: verify API accuracy in staged content files.
# Install: cp scripts/pre-commit-audit.sh .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit

# Collect staged content markdown files into an array (handles filenames with spaces)
mapfile -t changed < <(git diff --cached --name-only --diff-filter=ACM | grep '^content/.*\.md$')
[ ${#changed[@]} -eq 0 ] && exit 0

echo "Running content API audit on staged files..."
python scripts/pipeline/audit.py --files "${changed[@]}" --fail-fast
status=$?

if [ $status -ne 0 ]; then
    echo ""
    echo "BLOCKED: Content has API accuracy failures."
    echo "Fix the issues above, then re-stage and commit."
    exit 1
fi

echo "Content API audit passed."

# Check plugin_platform canonical values whenever products pages are staged
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
