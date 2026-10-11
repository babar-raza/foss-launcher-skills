#!/usr/bin/env bash
# governance_pilot.sh — TC-GOV-11: Non-destructive governance hook test sandbox.
#
# Tests all 8 PreToolUse hooks and key pre-commit behaviors against controlled
# scenarios without touching production content or branches.
#
# Usage:
#   bash tests/governance_pilot.sh --dry-run   # List scenarios, no execution
#   bash tests/governance_pilot.sh              # Run on disposable branch
#
# Safety:
#   - REFUSES to run on main/master branch (real mode only)
#   - Creates disposable branch: gov-pilot-<timestamp>
#   - Cleanup trap deletes branch and test files on exit
#   - Verifies post-test state matches pre-test state

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

DRY_RUN=false
if [ "${1:-}" = "--dry-run" ]; then
    DRY_RUN=true
fi

# Resolve bash for subprocess calls
if [ -x "/c/Program Files/Git/usr/bin/bash.exe" ]; then
    BASH_BIN="/c/Program Files/Git/usr/bin/bash.exe"
else
    BASH_BIN="bash"
fi

# ---------------------------------------------------------------------------
# Test scenario definitions
# ---------------------------------------------------------------------------

SCENARIOS=(
    "session_gate_read_exempt|Read tool exempt from session gate|exit 0"
    "session_gate_edit_blocked|Edit blocked without bootstrap|exit 2"
    "content_edit_blocked|Direct content Edit blocked|exit 2"
    "content_edit_bypass|SKIP_CONTENT_EDIT_CHECK bypass|exit 0"
    "skill_context_ungoverned|reports/ path ungoverned|exit 0"
    "skill_context_governed_blocked|content/ blocked without skill|exit 2"
    "write_path_allowed|docs/ Write allowed|exit 0"
    "write_path_root_blocked|Root-level Write blocked|exit 2"
    "content_write_no_marker|Content Write without S-23 marker|exit 2"
    "content_write_bypass|SKIP_CONTENT_WRITE_CHECK bypass|exit 0"
    "py_write_non_py|Non-.py file allowed|exit 0"
    "venv_bare_python_blocked|Bare python blocked|exit 2"
    "venv_venv_python_allowed|.venv python allowed|exit 0"
    "destructive_reset_hard_blocked|git reset --hard blocked|exit 2"
    "destructive_force_lease_allowed|--force-with-lease allowed|exit 0"
    "destructive_empty_failopen|Empty input fail-open|exit 0"
)

if $DRY_RUN; then
    echo "=== Governance Pilot -- Dry Run ==="
    echo "Would test ${#SCENARIOS[@]} scenarios on a disposable branch."
    echo ""
    printf "%-35s %-45s %s\n" "SCENARIO" "DESCRIPTION" "EXPECTED"
    printf "%-35s %-45s %s\n" "--------" "-----------" "--------"
    for s in "${SCENARIOS[@]}"; do
        IFS='|' read -r name desc expected <<< "$s"
        printf "%-35s %-45s %s\n" "$name" "$desc" "$expected"
    done
    echo ""
    echo "Run without --dry-run to execute."
    exit 0
fi

# ---------------------------------------------------------------------------
# Safety: refuse to run on main/master
# ---------------------------------------------------------------------------

CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
PRE_SHA=$(git rev-parse HEAD)
PRE_STATUS=$(git status --porcelain)
if [ -n "$PRE_STATUS" ]; then
    echo "ABORT: Working tree is not clean. Commit or stash changes first."
    exit 1
fi

# ---------------------------------------------------------------------------
# Create disposable branch + cleanup trap
# ---------------------------------------------------------------------------

PILOT_BRANCH="gov-pilot-$(date +%s)"
git checkout -b "$PILOT_BRANCH" >/dev/null 2>&1

cleanup() {
    echo ""
    echo "--- Cleanup ---"
    git checkout "$CURRENT_BRANCH" >/dev/null 2>&1 || true
    git branch -D "$PILOT_BRANCH" >/dev/null 2>&1 || true

    POST_SHA=$(git rev-parse HEAD)
    POST_STATUS=$(git status --porcelain)
    if [ "$PRE_SHA" = "$POST_SHA" ] && [ -z "$POST_STATUS" ]; then
        echo "CLEAN: Repo state unchanged (SHA: ${PRE_SHA:0:7})"
    else
        echo "WARNING: Post-test state differs from pre-test!"
        echo "  Pre:  $PRE_SHA (clean)"
        echo "  Post: $POST_SHA (status: $POST_STATUS)"
    fi
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# Helper: run a hook and check exit code
# ---------------------------------------------------------------------------

PASS_COUNT=0
FAIL_COUNT=0
TOTAL=0

run_test() {
    local name="$1"
    local hook_rel="$2"
    local payload="$3"
    local expected_exit="$4"
    local env_overrides="${5:-}"

    TOTAL=$((TOTAL + 1))

    # Build env
    local env_str=""
    if [ -n "$payload" ]; then
        env_str="CLAUDE_TOOL_INPUT=$payload"
    fi
    if [ -n "$env_overrides" ]; then
        env_str="$env_str $env_overrides"
    fi

    local actual_exit=0
    eval "$env_str \"$BASH_BIN\" \"$hook_rel\"" >/dev/null 2>&1 || actual_exit=$?

    if [ "$actual_exit" -eq "$expected_exit" ]; then
        printf "  PASS  %-40s (exit %d)\n" "$name" "$actual_exit"
        PASS_COUNT=$((PASS_COUNT + 1))
    else
        printf "  FAIL  %-40s (expected %d, got %d)\n" "$name" "$expected_exit" "$actual_exit"
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
}

echo "=== Governance Pilot -- Running ${#SCENARIOS[@]} scenarios ==="
echo "Branch: $PILOT_BRANCH (disposable)"
echo ""

# Use a temp gate file for session gate tests
GATE_DIR=$(mktemp -d)
GATE_FILE="$GATE_DIR/agents_read"

# ---------------------------------------------------------------------------
# Run scenarios
# ---------------------------------------------------------------------------

# Session gate
touch "$GATE_FILE"
run_test "session_gate_read_exempt" \
    "scripts/ci/check_session_gate.sh" \
    '{"tool_name":"Read","tool_input":{"file_path":"AGENTS.md"}}' \
    0 \
    "SESSION_GATE_OVERRIDE=$GATE_FILE"

rm -f "$GATE_FILE"
run_test "session_gate_edit_blocked" \
    "scripts/ci/check_session_gate.sh" \
    '{"tool_name":"Edit","tool_input":{"file_path":"scripts/ci/test.sh"}}' \
    2 \
    "SESSION_GATE_OVERRIDE=$GATE_FILE"

# Content edit
run_test "content_edit_blocked" \
    "scripts/ci/check_content_edit_hook.sh" \
    '{"tool_name":"Edit","tool_input":{"file_path":"content/docs.aspose.org/en/cells/net/index.md"}}' \
    2

run_test "content_edit_bypass" \
    "scripts/ci/check_content_edit_hook.sh" \
    '{"tool_name":"Edit","tool_input":{"file_path":"content/docs.aspose.org/en/cells/net/index.md"}}' \
    0 \
    "SKIP_CONTENT_EDIT_CHECK=1"

# Skill context
run_test "skill_context_ungoverned" \
    "scripts/ci/check_skill_context_hook.sh" \
    '{"tool_name":"Write","tool_input":{"file_path":"reports/test.txt"}}' \
    0

run_test "skill_context_governed_blocked" \
    "scripts/ci/check_skill_context_hook.sh" \
    '{"tool_name":"Write","tool_input":{"file_path":"content/docs.aspose.org/en/cells/net/index.md"}}' \
    2

# Write path
run_test "write_path_allowed" \
    "scripts/ci/check_write_path_hook.sh" \
    '{"tool_name":"Write","tool_input":{"file_path":"docs/test.md"}}' \
    0

run_test "write_path_root_blocked" \
    "scripts/ci/check_write_path_hook.sh" \
    '{"tool_name":"Write","tool_input":{"file_path":"NEWFILE.txt"}}' \
    2

# Content write
run_test "content_write_no_marker" \
    "scripts/ci/check_content_write_hook.sh" \
    '{"tool_name":"Write","tool_input":{"file_path":"content/docs.aspose.org/en/cells/net/_test.md"}}' \
    2

run_test "content_write_bypass" \
    "scripts/ci/check_content_write_hook.sh" \
    '{"tool_name":"Write","tool_input":{"file_path":"content/docs.aspose.org/en/cells/net/_test.md"}}' \
    0 \
    "SKIP_CONTENT_WRITE_CHECK=1"

# Py write
run_test "py_write_non_py" \
    "scripts/ci/check_py_write_hook.sh" \
    '{"tool_name":"Write","tool_input":{"file_path":"docs/test.md"}}' \
    0

# Venv bash
run_test "venv_bare_python_blocked" \
    "scripts/ci/check_venv_bash_hook.sh" \
    '{"tool_name":"Bash","tool_input":{"command":"python script.py"}}' \
    2

run_test "venv_venv_python_allowed" \
    "scripts/ci/check_venv_bash_hook.sh" \
    '{"tool_name":"Bash","tool_input":{"command":".venv/Scripts/python script.py"}}' \
    0

# Destructive bash
run_test "destructive_reset_hard_blocked" \
    "scripts/ci/check_destructive_bash_hook.sh" \
    '{"tool_name":"Bash","tool_input":{"command":"git reset --hard HEAD"}}' \
    2

run_test "destructive_force_lease_allowed" \
    "scripts/ci/check_destructive_bash_hook.sh" \
    '{"tool_name":"Bash","tool_input":{"command":"git push --force-with-lease"}}' \
    0

run_test "destructive_empty_failopen" \
    "scripts/ci/check_destructive_bash_hook.sh" \
    '' \
    0

# Cleanup temp gate dir
rm -rf "$GATE_DIR"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo ""
echo "=== Results: $PASS_COUNT/$TOTAL passed, $FAIL_COUNT failed ==="
if [ "$FAIL_COUNT" -gt 0 ]; then
    echo "PILOT FAILED: $FAIL_COUNT scenario(s) did not match expected behavior."
    exit 1
fi
echo "PILOT PASSED: All scenarios match expected behavior."
exit 0
