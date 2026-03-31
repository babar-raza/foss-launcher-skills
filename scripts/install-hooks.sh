#!/bin/bash
# install-hooks.sh — Install all governance hooks into .git/hooks/
# Run once after cloning: bash scripts/install-hooks.sh
#
# Installs:
#   pre-commit  <- scripts/pre-commit-audit.sh  (forbidden-path guard + API audit)
#   commit-msg  <- scripts/commit-msg-skills.sh  (Skills invoked field validation)
#   post-commit <- scripts/post-commit-override.sh (override token consumption)

set -e

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
HOOKS_DIR="$REPO_ROOT/.git/hooks"

if [ ! -d "$HOOKS_DIR" ]; then
    echo "ERROR: .git/hooks/ not found. Are you inside a git repository?"
    exit 1
fi

echo "Installing governance hooks..."

cp "$REPO_ROOT/scripts/pre-commit-audit.sh" "$HOOKS_DIR/pre-commit"
chmod +x "$HOOKS_DIR/pre-commit"
echo "  pre-commit  -> scripts/pre-commit-audit.sh"

cp "$REPO_ROOT/scripts/commit-msg-skills.sh" "$HOOKS_DIR/commit-msg"
chmod +x "$HOOKS_DIR/commit-msg"
echo "  commit-msg  -> scripts/commit-msg-skills.sh"

cp "$REPO_ROOT/scripts/post-commit-override.sh" "$HOOKS_DIR/post-commit"
chmod +x "$HOOKS_DIR/post-commit"
echo "  post-commit -> scripts/post-commit-override.sh"

echo ""
echo "Hooks installed. Verify with: ls -la .git/hooks/pre-commit .git/hooks/commit-msg .git/hooks/post-commit"
echo ""
echo "Requirements:"
echo "  - Python .venv must be activated: source .venv/bin/activate (Unix) or .venv\\Scripts\\activate (Windows)"
echo "  - scripts/pipeline/path_guard.py and scripts/pipeline/override_manager.py must be importable"
