#!/usr/bin/env bash
# check_plan_origination_gate_hook.sh — PreToolUse ExitPlanMode hook (PSE-03/04).
#
# Best-effort final gate for the parallel-mission/taskcard-tracker rule
# (check_plan_origination.py, PO-01/PO-02). This is intentionally NOT the
# primary detection mechanism — check_plan_origination_capture_hook.sh (wired
# to Write/Edit, which is proven to fire) records the exact plan file path.
# This hook only reads that breadcrumb; it never scans a directory or guesses
# by mtime (see the plan's F1/F3 findings for why).
#
# ExitPlanMode carries no plan content in tool_input (confirmed via the tool
# schema) — the plan lives in a file the agent already wrote. If the
# breadcrumb is missing, unreadable, or implausibly old, this FAILS OPEN
# (exit 0). Never block because the file couldn't be identified — the plans
# directory is shared across every project on this machine, not just this
# repo, so an incorrect block here has an unacceptable blast radius.
#
# Rollout mode — PLAN_ORIGINATION_GATE_MODE:
#   off      exit 0 immediately, no check, no log
#   shadow   (default) run the check, log the verdict, ALWAYS exit 0
#   enforce  run the check, log the verdict, block (exit 2) on a violation
#
# Do not flip the default to enforce without a shadow-mode burn-in showing
# zero false positives (plan F9 / PSE-05).
#
# All path/JSON/log logic lives in _plan_gate.py (see its header for why bash
# string substitution is deliberately avoided here). This wrapper only reads
# python's single-line verdict and translates it to bash exit codes.

set -uo pipefail

MODE="${PLAN_ORIGINATION_GATE_MODE:-shadow}"

if [ "$MODE" = "off" ]; then
    exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "$SCRIPT_DIR/find_python.sh" 2>/dev/null || true
source "$SCRIPT_DIR/_gov_block.sh"

# Fail open if the venv is broken — cannot run the check at all.
if [ -z "${PYTHON:-}" ]; then
    exit 0
fi

VERDICT=$("$PYTHON" "$SCRIPT_DIR/_plan_gate.py" "$MODE" 2>/dev/null)

case "$VERDICT" in
    BLOCK\|*)
        RULES="${VERDICT#BLOCK|}"
        RULES="${RULES%%|*}"
        REASONS="${VERDICT#BLOCK|*|}"
        _gov_block "Plan denied — invents a parallel mission/taskcard tracker ($RULES)." \
            "$REASONS" \
            "Bind this plan to MISSION_AUTHORITY.yaml / reports/plan_state/{mission_id}/taskcards.jsonl (schema 5f) / backlog/BACKLOG.md instead of inventing a new tracker — see AGENTS.md §17." \
            "PLAN_ORIGINATION_GATE_MODE=shadow or off (repo-level env var, logged either way)" \
            "docs/governance/planning-methodology.md"
        ;;
    *)
        exit 0
        ;;
esac
