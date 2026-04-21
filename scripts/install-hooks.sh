#!/usr/bin/env bash
# install-hooks.sh — Install git governance hooks for foss-launcher-skills-gitlab
#
# Installs three hooks into .git/hooks/:
#   pre-commit   — validates registry, sync, and staged content
#   commit-msg   — enforces skill provenance in content commit messages
#
# Usage:
#   bash scripts/install-hooks.sh
#
# Hooks are opt-in. Running this script installs them locally.
# They are never auto-installed by CI or on clone.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOKS_DIR="$REPO_ROOT/.git/hooks"
SCRIPTS_DIR="$REPO_ROOT/scripts"

if [[ ! -d "$REPO_ROOT/.git" ]]; then
  echo "ERROR: Not a git repository (no .git/ found at $REPO_ROOT)" >&2
  exit 1
fi

echo "Installing governance hooks into $HOOKS_DIR ..."

# pre-commit
cat > "$HOOKS_DIR/pre-commit" <<'EOF'
#!/usr/bin/env bash
# foss-launcher-skills-gitlab pre-commit hook
# Delegates to scripts/pre-commit-audit.sh
REPO_ROOT="$(git rev-parse --show-toplevel)"
exec bash "$REPO_ROOT/scripts/pre-commit-audit.sh"
EOF
chmod +x "$HOOKS_DIR/pre-commit"
echo "  ✓ pre-commit"

# commit-msg
cat > "$HOOKS_DIR/commit-msg" <<'EOF'
#!/usr/bin/env bash
# foss-launcher-skills-gitlab commit-msg hook
# Delegates to scripts/commit-msg-skills.sh
REPO_ROOT="$(git rev-parse --show-toplevel)"
exec bash "$REPO_ROOT/scripts/commit-msg-skills.sh" "$1"
EOF
chmod +x "$HOOKS_DIR/commit-msg"
echo "  ✓ commit-msg"

echo ""
echo "Hooks installed successfully."
echo ""
echo "To uninstall: rm $HOOKS_DIR/pre-commit $HOOKS_DIR/commit-msg"
