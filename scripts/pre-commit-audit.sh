#!/usr/bin/env bash
# pre-commit-audit.sh — Pre-commit governance checks for foss-launcher-skills-gitlab
#
# Runs on every commit. Enforces:
#   Step 1: Skill registry integrity (validate_skills.py)
#   Step 2: .claude/commands/ sync check (sync_commands.py)
#   Step 3: .agents/.kilocode/ sync check (sync_agents.py)
#   Step 4: Forbidden path guard on staged content files
#   Step 5: README currency check (readme_sync.py)
#
# Exit codes:
#   0  all checks pass — commit proceeds
#   1  violation found — commit is blocked; fix and re-stage

set -uo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
PYTHON="${VIRTUAL_ENV:+$VIRTUAL_ENV/bin/python}"
PYTHON="${PYTHON:-python}"

cd "$REPO_ROOT"

ERRORS=0

# ── Step 1: Skill registry integrity ────────────────────────────────────────
echo "[pre-commit] Step 1: Skill registry integrity ..."
if ! "$PYTHON" scripts/validate_skills.py; then
  echo "  FAIL: skill registry has violations — run 'python scripts/validate_skills.py' for details"
  ERRORS=$((ERRORS + 1))
fi

# ── Step 2: .claude/commands/ sync ──────────────────────────────────────────
echo "[pre-commit] Step 2: .claude/commands/ sync ..."
if ! "$PYTHON" scripts/sync_commands.py --check; then
  echo "  FAIL: .claude/commands/ is out of sync — run 'python scripts/sync_commands.py --sync'"
  ERRORS=$((ERRORS + 1))
fi

# ── Step 3: .agents/.kilocode/ sync ─────────────────────────────────────────
echo "[pre-commit] Step 3: .agents/.kilocode/ sync ..."
if ! "$PYTHON" scripts/sync_agents.py --check; then
  echo "  FAIL: .agents/ or .kilocode/ mirror is out of sync — run 'python scripts/sync_agents.py --sync'"
  ERRORS=$((ERRORS + 1))
fi

# ── Step 4: Forbidden path guard on staged content files ────────────────────
echo "[pre-commit] Step 4: Forbidden path guard ..."
STAGED_FILES=$(git diff --cached --name-only --diff-filter=ACM 2>/dev/null || true)
# Hard-blocked paths: changes here always require explicit human override
HARD_BLOCKED_PATTERNS=(
  "^themes/"
  "^layouts/"
  "^configs/"
  "^AGENTS\.md$"
  "^CLAUDE\.md$"
  "^CODEX\.md$"
)
# Soft-warned paths: informational only (scripts/skills change frequently during dev)
SOFT_WARNED_PATTERNS=(
  "^\.claude/"
  "^\.agents/"
  "^\.kilocode/"
  "^skills/"
  "^scripts/"
)
for staged_file in $STAGED_FILES; do
  for pattern in "${HARD_BLOCKED_PATTERNS[@]}"; do
    if echo "$staged_file" | grep -qE "$pattern"; then
      echo "  BLOCK: staged file in hard-forbidden path: $staged_file"
      echo "         Remove from staging or use --no-verify for explicit human override."
      ERRORS=$((ERRORS + 1))
      break
    fi
  done
  for pattern in "${SOFT_WARNED_PATTERNS[@]}"; do
    if echo "$staged_file" | grep -qE "$pattern"; then
      echo "  WARN: staged file matches restricted path: $staged_file"
      echo "        If this is intentional (migration, maintenance), this is informational only."
      break
    fi
  done
done

# ── Step 5: README currency ──────────────────────────────────────────────────
echo "[pre-commit] Step 5: README currency ..."
if ! "$PYTHON" scripts/readme_sync.py --check 2>/dev/null; then
  echo "  WARN: README.md may be stale — run 'python scripts/readme_sync.py' to inspect"
  # README staleness is a warning, not a hard blocker
fi

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
if [[ $ERRORS -eq 0 ]]; then
  echo "[pre-commit] PASS: all checks passed"
  exit 0
else
  echo "[pre-commit] FAIL: $ERRORS check(s) failed — commit blocked"
  echo "Fix violations and re-stage before committing."
  exit 1
fi
