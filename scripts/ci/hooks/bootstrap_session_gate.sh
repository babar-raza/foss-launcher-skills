#!/usr/bin/env bash
# bootstrap_session_gate.sh — Create .claude/.agents_read to unblock session tools.
#
# Run as step 0 of /session-start, before any other tool call (including the
# skill context gate). Idempotent: safe to run multiple times.
#
# This script is specifically exempted by check_session_gate.sh and
# auto-approved in .claude/settings.json permissions.allow.
#
# Semantics (Model B — honest latch):
#   .agents_read is a session bootstrap latch, not proof AGENTS.md was read.
#   The session-start skill steps provide the process guarantee that AGENTS.md
#   is read after this script runs.

set -euo pipefail

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)

# Gate file path: production uses repo default; SESSION_GATE_OVERRIDE redirects to a
# caller-supplied path (used by tests to avoid touching the live .claude/.agents_read)
GATE_FILE="${SESSION_GATE_OVERRIDE:-$REPO_ROOT/.claude/.agents_read}"

mkdir -p "$(dirname "$GATE_FILE")"
printf '1' > "$GATE_FILE"
echo "Session gate created: $GATE_FILE"

# Venv health check — warning only, does not block bootstrap
source "$(dirname "${BASH_SOURCE[0]}")/check_venv.sh" || true
if [ "${VENV_OK:-0}" != "1" ]; then
    echo "⚠️  Warning: .venv is broken or missing. Hook governance requires the venv." >&2
    echo "   Write/Edit/Delete tools will be blocked until venv is repaired." >&2
    echo "   Recovery: bash scripts/ci/hooks/repair_venv.sh" >&2
    echo "   (Manual fallback: python -m venv .venv && .venv/Scripts/python -m pip install -r scripts/pipeline/requirements.txt  # Windows)" >&2
    echo "   (Manual fallback: python -m venv .venv && .venv/bin/python -m pip install -r scripts/pipeline/requirements.txt      # Unix)" >&2
fi
