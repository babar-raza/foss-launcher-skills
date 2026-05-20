#!/usr/bin/env bash
# _gov_block.sh — Shared blocking/warning helper for governance hooks.
# Source this file; do not execute directly.
# Created by TC-DS-03 (Governance Simplification Delta Sprint).

_gov_block() {
    local _exit_code="${7:-2}"
    echo "BLOCKED: ${1:?}" >&2
    echo "REASON:  ${2:?}" >&2
    echo "FIX:     ${3:?}" >&2
    echo "BYPASS:  ${4:-N/A}" >&2
    [ -n "${5:-}" ] && echo "DOC:     $5" >&2
    [ -n "${6:-}" ] && echo "HEAL_HINT: $6" >&2
    exit "$_exit_code"
}

_gov_warn() {
    echo "WARN: ${1:?}" >&2
    [ -n "${2:-}" ] && echo "REASON:  $2" >&2
    [ -n "${3:-}" ] && echo "FIX:     $3" >&2
}
