#!/usr/bin/env bash
# find_python.sh — Shared venv Python resolver. SOURCE this file; do not execute directly.
#
# Policy (DR-01): NO fallback to bare python or python3.
# Only the repo .venv interpreter is accepted. System Python is never used.
#
# After sourcing, check the result:
#   source "$(dirname "${BASH_SOURCE[0]}")/find_python.sh" || true
#   if [ -z "$PYTHON" ]; then
#       echo "⛔ venv broken ..." >&2; exit 2
#   fi
#
# Sets:
#   PYTHON  — absolute path to .venv interpreter (e.g. /d/repo/.venv/Scripts/python)
#             empty string if venv is absent, stub-only, or broken
#
# On failure: emits diagnostic to stderr, returns 1.
# On success: PYTHON is set, returns 0.

# Compute repo root from THIS script's location (scripts/ci/ — two levels up).
# BASH_SOURCE[0] is find_python.sh itself when sourced — independent of the caller.
_FP_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_FP_REPO_ROOT="$(cd "$_FP_SCRIPT_DIR/../../.." && pwd)"

PYTHON=""

# Try candidates in order: Windows (.exe present), then Unix
for _fp_candidate in \
    "$_FP_REPO_ROOT/.venv/Scripts/python" \
    "$_FP_REPO_ROOT/.venv/bin/python"; do

    # Existence check: accept if .exe variant exists (Windows) or plain file exists (Unix/macOS)
    if [ -f "${_fp_candidate}.exe" ] || [ -f "$_fp_candidate" ]; then
        # Health check: interpreter must actually run (catches OneDrive stub-only syncs)
        if "$_fp_candidate" -c "import sys" >/dev/null 2>&1; then
            PYTHON="$_fp_candidate"
            break
        fi
    fi
done

# Clean up temp variables (do not pollute the caller's environment)
unset _FP_SCRIPT_DIR _FP_REPO_ROOT _fp_candidate

if [ -z "$PYTHON" ]; then
    echo "  [find_python] venv Python not available or broken." >&2
    echo "  Expected: .venv/Scripts/python (Windows) or .venv/bin/python (Unix/macOS)" >&2
    echo "  Recovery: rm -rf .venv && python -m venv .venv && pip install -r scripts/ci/requirements.txt" >&2
    # return 1 when sourced; fall back to exit 1 when executed directly (suppressed)
    return 1 2>/dev/null || exit 1
fi
