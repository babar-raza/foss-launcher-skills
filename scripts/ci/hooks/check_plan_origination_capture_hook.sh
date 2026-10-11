#!/usr/bin/env bash
# check_plan_origination_capture_hook.sh — PreToolUse Write/Edit hook.
#
# Breadcrumb only. Never blocks (always exits 0). Records the exact file_path
# of the most recent Write/Edit under ~/.claude/plans/ so the ExitPlanMode gate
# hook (check_plan_origination_gate_hook.sh) can read the plan file directly
# instead of scanning the directory and guessing by mtime (PSE plan F1/F3).
#
# Scope: only acts when file_path is under $HOME/.claude/plans/ and ends in
# .md. For every other Write/Edit call (the overwhelming majority in this
# repo) this exits 0 immediately with no side effect.
#
# This hook has zero governance authority. Any failure (unparseable input,
# missing python) is silently swallowed and this exits 0 — a plan-mode
# breadcrumb writer must never be the reason a Write/Edit is blocked.
#
# All logic (including path normalization) lives in _plan_capture.py, invoked
# by path — deliberately NOT inlined as `python -c "..."` here. Inline -c
# strings with backslash-heavy path logic were empirically found to be
# unreliable across the bash-quoting/heredoc/Python-literal escaping layers
# in this environment; a standalone file has exactly one interpretation
# layer (bytes on disk -> Python), which is unambiguous.
#
# Wiring (in .claude/settings.json): append as one more hook in BOTH the
# Write and Edit PreToolUse arrays, alongside the existing path/content hooks.

set -uo pipefail  # deliberately no -e: any failure below just falls through to exit 0

TOOL_INPUT="${CLAUDE_TOOL_INPUT:-}"
if [ -z "$TOOL_INPUT" ]; then
    TOOL_INPUT=$(cat 2>/dev/null || true)
fi
[ -z "$TOOL_INPUT" ] && exit 0

source "$(dirname "${BASH_SOURCE[0]}")/find_python.sh" 2>/dev/null || true
[ -z "${PYTHON:-}" ] && exit 0

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
printf '%s' "$TOOL_INPUT" | "$PYTHON" "$SCRIPT_DIR/_plan_capture.py" 2>/dev/null || true

exit 0
