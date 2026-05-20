#!/usr/bin/env bash
# check_venv.sh — Venv health diagnostic utility.
#
# Run standalone to check whether the repo .venv is healthy.
# Also sourced by bootstrap_session_gate.sh as a warning-only post-bootstrap check.
#
# Exit codes (standalone):
#   0 = healthy
#   1 = broken or absent (includes diagnostic to stderr)
#
# When sourced: sets VENV_OK=1 (healthy) or VENV_OK=0 (broken).
# Never blocks the caller when sourced — callers decide what to do.
#
# Usage (standalone):
#   bash scripts/ci/hooks/check_venv.sh
#
# Usage (sourced, warning-only):
#   source "$(dirname "${BASH_SOURCE[0]}")/check_venv.sh" || true
#   if [ "${VENV_OK:-0}" != "1" ]; then echo "Warning: venv unhealthy" >&2; fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

VENV_DIR="$REPO_ROOT/.venv"
VENV_OK=0

_cv_fail() {
    echo "  [check_venv] FAIL: $1" >&2
    echo "  Recovery: rm -rf .venv && python -m venv .venv && pip install -r scripts/ci/requirements.txt" >&2
}

# Check 1: .venv directory exists
if [ ! -d "$VENV_DIR" ]; then
    _cv_fail ".venv directory not found at $VENV_DIR"
    return 1 2>/dev/null || exit 1
fi

# Check 2: pyvenv.cfg exists (catches OneDrive partial sync — text files not synced)
if [ ! -f "$VENV_DIR/pyvenv.cfg" ]; then
    _cv_fail "pyvenv.cfg missing — .venv may be an OneDrive partial sync stub"
    return 1 2>/dev/null || exit 1
fi

# Check 3: Python binary exists
_cv_python=""
for _cv_candidate in "$VENV_DIR/Scripts/python" "$VENV_DIR/bin/python"; do
    if [ -f "${_cv_candidate}.exe" ] || [ -f "$_cv_candidate" ]; then
        _cv_python="$_cv_candidate"
        break
    fi
done

if [ -z "$_cv_python" ]; then
    _cv_fail "Python binary not found in .venv/Scripts/ or .venv/bin/"
    unset _cv_candidate _cv_python
    return 1 2>/dev/null || exit 1
fi

# Check 4: Python binary passes health check (catches stub-only .exe syncs)
if ! "$_cv_python" -c "import sys" >/dev/null 2>&1; then
    _cv_fail "Python binary exists but fails to run — may be an OneDrive stub"
    _cv_fail "  Binary: $_cv_python"
    unset _cv_candidate _cv_python
    return 1 2>/dev/null || exit 1
fi

unset _cv_candidate _cv_python _cv_fail VENV_DIR SCRIPT_DIR REPO_ROOT

VENV_OK=1

# When executed directly (not sourced): print OK and exit 0
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo "  [check_venv] OK: .venv is healthy"
    exit 0
fi
