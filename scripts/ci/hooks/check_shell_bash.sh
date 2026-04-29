#!/usr/bin/env bash
# check_shell_bash.sh — Validate Git Bash is active on Windows
#
# Usage:
#   source scripts/ci/hooks/check_shell_bash.sh           # from another script
#   bash scripts/ci/hooks/check_shell_bash.sh             # direct execution (testing)
#
# Environment:
#   _SHELL_CHECK_MODE  warn|block  (default: warn)
#     warn  = print violation to stderr, return 0
#     block = print violation to stderr, return 1
#
# The utility always reads _SHELL_CHECK_MODE (default: warn). Phase hardening
# happens at the CALLER level: Phase 1+2 callers do not set it (→ warn default);
# Phase 4 callers prepend _SHELL_CHECK_MODE=block before sourcing.
# _SHELL_CHECK_MODE is never exported. It is an internal test/phase knob.
#
# Exit codes (when sourced):
#   return 0  = pass or non-Windows (skip)
#   return 1  = violation in block mode
#
# Exit codes (when executed directly):
#   exit 0    = pass or non-Windows
#   exit 1    = violation in block mode
#
# This script is Windows-only enforcement. On Linux/macOS/CI (ubuntu-latest),
# it skips unconditionally (returns 0).
#
# Rejected shells on Windows:
#   - WSL: env vars lost across Windows→WSL boundary (docs/STATUS-venv-closure.md)
#   - Cygwin: MSYS2-incompatible path semantics
#   - Any bash without MSYSTEM=MINGW*: not Git Bash
#
# Accepted shell on Windows:
#   - Git Bash (Git for Windows): MSYSTEM=MINGW64 or MSYSTEM=MINGW32

_check_shell_bash() {
    local _mode="${_SHELL_CHECK_MODE:-warn}"

    # Non-Windows: skip unconditionally (Linux, macOS, GitHub Actions CI)
    if [[ "${OS:-}" != "Windows_NT" ]]; then
        return 0
    fi

    # Windows: git hook context — GIT_DIR is set by git itself when running a hook.
    # MSYSTEM may not be inherited by the hook subprocess (observed in GitHub Desktop
    # 3.5.8 which uses its own git-for-Windows process). WSL is still rejected above;
    # this exemption only applies when not WSL and not Cygwin.
    if [[ -n "${GIT_DIR:-}" ]]; then
        return 0
    fi

    # Windows: check for WSL (explicitly rejected — env vars lost across boundary)
    # See: docs/STATUS-venv-closure.md
    if [[ -n "${WSL_DISTRO_NAME:-}" || -n "${WSL_INTEROP:-}" ]]; then
        echo "⛔ SHELL POLICY VIOLATION: WSL bash is not permitted for repo operations." >&2
        echo "   Reason: WSL drops environment variables across the Windows→WSL boundary," >&2
        echo "   breaking governance hooks. See docs/STATUS-venv-closure.md." >&2
        echo "   Required: Git Bash (Git for Windows) — https://git-scm.com/downloads" >&2
        echo "   See setup instructions: docs/QUICKSTART.md" >&2
        if [[ "$_mode" == "block" ]]; then
            return 1
        fi
        echo "   ⚠️  WARN MODE: continuing. This will be a hard block in Phase 4." >&2
        return 0
    fi

    # Windows: check for Cygwin (MSYS2-incompatible path semantics)
    if [[ "${OSTYPE:-}" == cygwin ]]; then
        echo "⛔ SHELL POLICY VIOLATION: Cygwin bash is not permitted for repo operations." >&2
        echo "   Reason: Cygwin uses MSYS2-incompatible path semantics." >&2
        echo "   Required: Git Bash (Git for Windows) — https://git-scm.com/downloads" >&2
        echo "   See setup instructions: docs/QUICKSTART.md" >&2
        if [[ "$_mode" == "block" ]]; then
            return 1
        fi
        echo "   ⚠️  WARN MODE: continuing. This will be a hard block in Phase 4." >&2
        return 0
    fi

    # Windows: Git Bash confirmed (MSYSTEM starts with MINGW)
    # shellcheck disable=SC2053
    if [[ "${MSYSTEM:-}" == MINGW* ]]; then
        return 0
    fi

    # Windows: bash is running but MSYSTEM not set — not Git Bash
    # Handles MSYS1, standalone bash installs, or unrecognized environments.
    if [[ -n "${BASH_VERSION:-}" ]]; then
        echo "⛔ SHELL POLICY VIOLATION: Running bash on Windows but MSYSTEM is not set." >&2
        echo "   This is not Git Bash (Git for Windows). Git Bash sets MSYSTEM=MINGW64." >&2
        echo "   Required: Git Bash (Git for Windows) — https://git-scm.com/downloads" >&2
        echo "   See setup instructions: docs/QUICKSTART.md" >&2
        if [[ "$_mode" == "block" ]]; then
            return 1
        fi
        echo "   ⚠️  WARN MODE: continuing. This will be a hard block in Phase 4." >&2
        return 0
    fi

    # Safety net: BASH_VERSION absent on Windows
    # Unreachable from bash, but guards against future invocation changes.
    echo "⛔ SHELL POLICY VIOLATION: Cannot determine shell on Windows." >&2
    echo "   Required: Git Bash (Git for Windows) — https://git-scm.com/downloads" >&2
    echo "   See setup instructions: docs/QUICKSTART.md" >&2
    if [[ "$_mode" == "block" ]]; then
        return 1
    fi
    return 0
}

# Invoke the check. Handle both source and direct execution:
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    # Executed directly (e.g., for testing or manual verification)
    _check_shell_bash
    exit $?
else
    # Sourced by another script — return value propagates to caller
    _check_shell_bash
fi
