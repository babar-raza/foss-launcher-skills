#!/bin/bash
# install-hooks.sh — Install all governance hooks into .git/hooks/
# Run once after cloning: bash scripts/install-hooks.sh
#
# Installs:
#   pre-commit  <- scripts/pre-commit-audit.sh  (forbidden-path guard + API audit)
#   commit-msg  <- scripts/commit-msg-skills.sh  (Skills invoked field validation)
#   post-commit <- scripts/post-commit-override.sh (override token consumption)
#   reference-transaction <- scripts/maintenance/reference-transaction-unshallow.sh (auto-unshallow)

set -e

# Shell preflight (Windows-only; warn mode until Phase 4 hardens to block)
# shellcheck source=scripts/ci/check_shell_bash.sh
source "$(dirname "$0")/ci/check_shell_bash.sh" || exit 1

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

# reference-transaction: heredoc ensures executable bit on Windows NTFS
cat > "$HOOKS_DIR/reference-transaction" << HOOKEOF
#!/bin/bash
exec bash "$REPO_ROOT/scripts/maintenance/reference-transaction-unshallow.sh" "\$@"
HOOKEOF
echo "  reference-transaction -> scripts/maintenance/reference-transaction-unshallow.sh"
echo ""
echo "=== Hook installation verification ==="
ALL_OK=1
for hook in pre-commit commit-msg post-commit reference-transaction; do
    if [ -x "$HOOKS_DIR/$hook" ]; then
        echo "  OK  $hook"
    else
        echo "  MISSING  $hook — installation failed"
        ALL_OK=0
    fi
done

if [ "$ALL_OK" -eq 0 ]; then
    echo "ERROR: One or more hooks failed to install."
    exit 1
fi

echo "All hooks installed and executable."
echo ""
echo "Requirements:"
echo "  - Python .venv must be activated: source .venv/bin/activate (Unix) or .venv/Scripts/activate (Windows)"
echo "  - scripts/pipeline/path_guard.py and scripts/pipeline/override_manager.py must be importable"
