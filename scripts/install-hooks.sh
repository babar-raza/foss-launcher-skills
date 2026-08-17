#!/bin/bash
# install-hooks.sh — Point git at the tracked scripts/githooks/ directory via
# core.hooksPath. Run once after cloning: bash scripts/install-hooks.sh
#
# Design (2026-08-08): previously this script copied each hook source into the
# untracked .git/hooks/ directory, which meant every edit to a hook's source had to
# be followed by re-running this installer or the installed copy silently went stale
# — confirmed live: the installed copy was missing a bug fix and an entire safety
# step (media asset size guard) that had already landed in scripts/pre-commit-audit.sh.
# core.hooksPath eliminates the copy: git executes the tracked wrapper directly, which
# execs the real source, so there is nothing left to fall behind. See
# docs/operations/hook-installation.md for the full rationale.
#
# Wrappers (in scripts/githooks/, each execs its real script directly):
#   pre-commit  -> scripts/pre-commit-audit.sh  (forbidden-path guard + API audit)
#   commit-msg  -> scripts/commit-msg-skills.sh  (Skills invoked field validation)
#   post-commit -> scripts/post-commit-override.sh (override token consumption)
#   reference-transaction -> tracked verbatim (self-contained, no exec wrapper needed)
#
# The former pre-push wrapper -> scripts/pre-push-audit.sh (Tier 2: governance test
# suite, Python placement baseline, actionlint, dependency sanity — added 2026-08-14,
# TC-CIR-06) was removed 2026-08-16: it broke on GitHub Desktop (non-executable
# wrapper on checkout, see docs/operations/hook-installation.md) and its ~281s
# runtime badly exceeded its own 90s budget.

set -e

# Shell preflight (Windows-only; warn mode until Phase 4 hardens to block)
# shellcheck source=scripts/ci/hooks/check_shell_bash.sh
source "$(dirname "$0")/ci/hooks/check_shell_bash.sh" || exit 1

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
GITHOOKS_DIR="$REPO_ROOT/scripts/githooks"

if [ ! -d "$GITHOOKS_DIR" ]; then
    echo "ERROR: scripts/githooks/ not found. Are you inside a git repository?"
    exit 1
fi

# Ensure reports/ directories exist for skill context, overrides, and audits
mkdir -p "$REPO_ROOT/reports/skill-context"
mkdir -p "$REPO_ROOT/reports/skill-runs"
mkdir -p "$REPO_ROOT/reports/overrides/pending"
mkdir -p "$REPO_ROOT/reports/audit"
echo "reports/ directories ensured."

echo "Installing governance hooks (core.hooksPath -> scripts/githooks/)..."

# core.fileMode=false in this repo: git does not track/restore the executable bit,
# so chmod +x must still run once per fresh checkout — this is the only remaining
# per-clone step; it never needs rerunning after a hook *source* edit.
chmod +x "$GITHOOKS_DIR/pre-commit" "$GITHOOKS_DIR/commit-msg" \
         "$GITHOOKS_DIR/post-commit" "$GITHOOKS_DIR/reference-transaction"

git -C "$REPO_ROOT" config core.hooksPath scripts/githooks
echo "  core.hooksPath -> scripts/githooks"

echo ""
echo "=== Hook installation verification ==="
ALL_OK=1
for hook in pre-commit commit-msg post-commit reference-transaction; do
    if [ -x "$GITHOOKS_DIR/$hook" ]; then
        echo "  OK  $hook"
    else
        echo "  MISSING  $hook -- installation failed"
        ALL_OK=0
    fi
done

CONFIGURED_PATH=$(git -C "$REPO_ROOT" config --get core.hooksPath || true)
if [ "$CONFIGURED_PATH" != "scripts/githooks" ]; then
    echo "  MISMATCH  core.hooksPath is '$CONFIGURED_PATH', expected 'scripts/githooks'"
    ALL_OK=0
fi

if [ "$ALL_OK" -eq 0 ]; then
    echo "ERROR: One or more hooks failed to install."
    exit 1
fi

echo "All hooks installed, executable, and wired via core.hooksPath."
echo ""
echo "Requirements:"
echo "  - Python .venv must be activated: source .venv/bin/activate (Unix) or .venv/Scripts/activate (Windows)"
echo "  - scripts/pipeline/commands/governance/path_guard.py and scripts/pipeline/commands/governance/override_manager.py must be importable"
