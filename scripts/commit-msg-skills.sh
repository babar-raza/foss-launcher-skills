#!/bin/bash
# Commit-msg hook: verify content commits include "Skills invoked:" with valid IDs.
# Install: cp scripts/commit-msg-skills.sh .git/hooks/commit-msg && chmod +x .git/hooks/commit-msg
#
# Validates:
#   1. Presence of "Skills invoked:" field on content commits
#   2. That all S-{n} IDs are real IDs from the AGENTS.md §12 registry

# ---------------------------------------------------------------------------
# DR-01 (TC-GOV-15): Central .venv Python resolver — mirrors pre-commit-audit.sh.
# Steps 2 and 3 use $_HOOK_PYTHON. When .venv is absent, those steps skip.
# ---------------------------------------------------------------------------
if [ -f ".venv/Scripts/python" ]; then
    _HOOK_PYTHON=".venv/Scripts/python"
elif [ -f ".venv/bin/python" ]; then
    _HOOK_PYTHON=".venv/bin/python"
else
    echo "[commit-msg] WARN: .venv not found — Python-based skill ID and run-record checks will be skipped." >&2
    _HOOK_PYTHON=""
fi

# Add the Codex co-author trailer only for agent-authored messages. Human
# commits normally have no "Skills invoked:" line and must not be modified.
if [ -n "$1" ] && [ -f "$1" ]; then
    msg=$(cat "$1")
    if echo "$msg" | grep -qiE 'skills?\s*invoked'; then
        _codex_trailer="Co-authored-by: Codex <codex@openai.com>"
        if ! grep -qiF "$_codex_trailer" "$1"; then
            printf '\n%s\n' "$_codex_trailer" >> "$1"
            msg=$(cat "$1")
        fi
    fi
fi

# Only check commits that touch content files.
content_staged=$(git diff --cached --name-only --diff-filter=ACM 2>/dev/null | grep '^content/.*\.md$' | head -1)
[ -z "$content_staged" ] && exit 0

# --- Audited operator bypass (3-var model) ---
# Requires ALL THREE: SKIP_SKILL_COMMIT_CHECK=1 + GOV_BYPASS_TASKCARD + GOV_BYPASS_REASON
# Bare bypass (flag only) is rejected. See docs/BYPASS_REGISTRY.md.
if [ "${SKIP_SKILL_COMMIT_CHECK:-0}" = "1" ]; then
    _tc="${GOV_BYPASS_TASKCARD:-}"
    _reason="${GOV_BYPASS_REASON:-}"
    if [ -z "$_tc" ] || [ -z "$_reason" ]; then
        echo ""
        echo "BLOCKED: SKIP_SKILL_COMMIT_CHECK=1 set but missing required context."
        echo "REASON:  GOV_BYPASS_TASKCARD and GOV_BYPASS_REASON are mandatory for audited bypass."
        echo "FIX:     SKIP_SKILL_COMMIT_CHECK=1 GOV_BYPASS_TASKCARD=TC-GOV-XX GOV_BYPASS_REASON='reason' git commit ..."
        echo "BYPASS:  Not allowed without taskcard and reason."
        echo ""
        exit 1
    fi
    _repo="$(git rev-parse --show-toplevel)"
    _log="$_repo/reports/overrides/env-bypasses.log"
    _branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
    _head="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
    mkdir -p "$(dirname "$_log")"
    printf 'timestamp_utc=%s event=env_bypass bypass=SKIP_SKILL_COMMIT_CHECK taskcard=%s reason="%s" user=%s branch=%s head=%s files=%s result=allowed\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$_tc" "$_reason" "$(whoami)" "$_branch" "$_head" \
        "$(echo "$content_staged" | tr '\n' ';')" >> "$_log"
    echo "WARN: Skill commit check bypassed (taskcard=$_tc reason=$_reason)"
    exit 0
fi

# $1 is the commit message file.
if [ -z "$1" ] || [ ! -f "$1" ]; then
    exit 0
fi

msg=$(cat "$1")

# --- Human-commit detection (TC-GOV-15) ---
# If NO "Skills invoked:" line is present, treat as human commit.
# The /commit skill (S-76) ALWAYS produces "Skills invoked:" by contract.
# Its absence reliably signals a human-authored message (GitHub Desktop, GUI, etc.).
# Human commits cannot supply skill run records; bypass is logged for audit.
if ! echo "$msg" | grep -qiE 'skills?\s*invoked'; then
    _repo="$(git rev-parse --show-toplevel)"
    _log="$_repo/reports/overrides/env-bypasses.log"
    _branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
    _head="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
    mkdir -p "$(dirname "$_log")"
    printf 'timestamp_utc=%s event=human_commit bypass=no_skills_invoked taskcard=TC-GOV-15 branch=%s head=%s files=%s result=allowed\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$_branch" "$_head" \
        "$(echo "$content_staged" | tr '\n' ';')" >> "$_log"
    echo "INFO: Human commit detected (no 'Skills invoked:' line) — skill run check bypassed (TC-GOV-15). Logged."
    exit 0
fi

# Step 1: (agent path) verify Skills invoked: field is present — already confirmed above.

# Step 2: Validate that listed S-{n} IDs exist in the AGENTS.md §12 registry
if [ -n "$_HOOK_PYTHON" ]; then
    echo "$msg" | "$_HOOK_PYTHON" scripts/ci/checks/validate_skill_ids.py --stdin
    if [ $? -ne 0 ]; then
        echo ""
        echo "BLOCKED: Content commit denied — invalid skill IDs."
        echo "REASON:  One or more skill IDs in 'Skills invoked:' are not in the AGENTS.md §12 registry."
        echo "FIX:     Check AGENTS.md §12 for valid skill IDs."
        echo "BYPASS:  SKIP_SKILL_COMMIT_CHECK=1 + GOV_BYPASS_TASKCARD + GOV_BYPASS_REASON"
        echo "DOC:     AGENTS.md §12 (Skill Registry)"
        echo ""
        exit 1
    fi
else
    echo "[commit-msg Step 2] SKIP: .venv not found — skill ID validation skipped." >&2
fi

# Step 3: Validate declared skills against pending skill run record (BLOCKING).
# No bypass path — all content commits must have a matching skill run record.

if [ -n "$_HOOK_PYTHON" ]; then
    PENDING_RUN=$("$_HOOK_PYTHON" scripts/pipeline/commands/ops/skill_run_manager.py find-pending --max-age-hours 48 2>/dev/null)
    if [ -n "$PENDING_RUN" ]; then
        declared=$(echo "$msg" | grep -iE 'skills?\s*invoked' | sed 's/.*[Ss]kills\s*[Ii]nvoked[: ]*//' | tr -d '[]')
        validation_result=$("$_HOOK_PYTHON" scripts/pipeline/commands/ops/skill_run_manager.py validate \
            --run-id "$PENDING_RUN" --declared "$declared" 2>&1)
        validation_exit=$?
        if [ $validation_exit -ne 0 ]; then
            echo ""
            echo "BLOCKED: Content commit denied — skills do not match run record."
            echo "REASON:  Declared skills do not match skill run record $PENDING_RUN."
            echo "FIX:     Run: $_HOOK_PYTHON scripts/pipeline/commands/ops/skill_run_manager.py get-declared-skills --run-id $PENDING_RUN"
            echo "BYPASS:  SKIP_SKILL_COMMIT_CHECK=1 + GOV_BYPASS_TASKCARD + GOV_BYPASS_REASON"
            echo "DOC:     AGENTS.md §10"
            echo ""
            exit 1
        fi
    else
        # No pending run record — BLOCKED. All content commits require skill run evidence.
        echo ""
        echo "BLOCKED: Content commit denied — no skill run record found."
        echo "REASON:  Content commits require a skill run record for provenance."
        echo "FIX:     Use /commit (S-76) to create auditable skill run records."
        echo "BYPASS:  SKIP_SKILL_COMMIT_CHECK=1 + GOV_BYPASS_TASKCARD + GOV_BYPASS_REASON"
        echo "DOC:     AGENTS.md §10"
        echo ""
        exit 1
    fi
else
    echo "[commit-msg Step 3] SKIP: .venv not found — skill run record validation skipped." >&2
fi

exit 0
