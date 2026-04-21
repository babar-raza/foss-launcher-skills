#!/usr/bin/env bash
# commit-msg-skills.sh — Commit message skill provenance check
#
# Validates that commits touching content/ include a "Skills invoked:" line
# citing the skill IDs used. This creates an audit trail linking content
# changes to the skills that generated or modified them.
#
# Exempt commits:
#   - Commits that touch ONLY non-content paths (docs/, scripts/, skills/, etc.)
#   - Merge commits
#   - Revert commits
#   - WIP / fixup! / squash! commits
#
# Expected format in commit message:
#   Skills invoked: S-19, S-23, S-24
#
# Usage: called automatically by .git/hooks/commit-msg
#        receives the path to the commit message file as $1

set -uo pipefail

COMMIT_MSG_FILE="${1:-}"
if [[ -z "$COMMIT_MSG_FILE" ]]; then
  echo "commit-msg-skills: no commit message file provided" >&2
  exit 1
fi

COMMIT_MSG=$(cat "$COMMIT_MSG_FILE")
REPO_ROOT="$(git rev-parse --show-toplevel)"

# ── Exempt commit types ──────────────────────────────────────────────────────
first_line=$(echo "$COMMIT_MSG" | head -1)
if echo "$first_line" | grep -qE "^(Merge|Revert|WIP|fixup!|squash!|chore:)"; then
  exit 0
fi

# ── Check if this commit touches content/ files ──────────────────────────────
STAGED_FILES=$(git diff --cached --name-only --diff-filter=ACM 2>/dev/null || true)
TOUCHES_CONTENT=0
for f in $STAGED_FILES; do
  if echo "$f" | grep -qE "^content/"; then
    TOUCHES_CONTENT=1
    break
  fi
done

# Only enforce provenance for content commits
if [[ $TOUCHES_CONTENT -eq 0 ]]; then
  exit 0
fi

# ── Check for Skills invoked: line ───────────────────────────────────────────
if ! echo "$COMMIT_MSG" | grep -qE "^Skills invoked:"; then
  echo "" >&2
  echo "commit-msg-skills: content commit is missing skill provenance." >&2
  echo "" >&2
  echo "Add a 'Skills invoked:' line to your commit message:" >&2
  echo "" >&2
  echo "  Skills invoked: S-19, S-23, S-24" >&2
  echo "" >&2
  echo "List every skill ID used to generate or modify the committed content." >&2
  echo "Use skill IDs from skills/registry.yaml (e.g. S-19, S-23, S-38)." >&2
  echo "" >&2
  echo "If you edited content manually without using skills, write:" >&2
  echo "  Skills invoked: manual" >&2
  echo "" >&2
  exit 1
fi

# ── Validate cited skill IDs against registry ────────────────────────────────
PYTHON="${VIRTUAL_ENV:+$VIRTUAL_ENV/bin/python}"
PYTHON="${PYTHON:-python}"

SKILLS_LINE=$(echo "$COMMIT_MSG" | grep -E "^Skills invoked:" | head -1)
# Extract all S-\d+ tokens from the line
CITED_IDS=$(echo "$SKILLS_LINE" | grep -oE "S-[0-9]+" || true)

if [[ -n "$CITED_IDS" ]]; then
  # Load registered IDs from registry.yaml
  REGISTERED_IDS=$("$PYTHON" -c "
import yaml, sys
with open('$REPO_ROOT/skills/registry.yaml') as f:
    data = yaml.safe_load(f)
ids = {e['id'] for e in data.get('skills', [])}
print(' '.join(sorted(ids)))
" 2>/dev/null || true)

  UNKNOWN_IDS=""
  for id in $CITED_IDS; do
    if ! echo " $REGISTERED_IDS " | grep -q " $id "; then
      UNKNOWN_IDS="$UNKNOWN_IDS $id"
    fi
  done

  if [[ -n "$UNKNOWN_IDS" ]]; then
    echo "" >&2
    echo "commit-msg-skills: unrecognized skill ID(s) in commit message:$UNKNOWN_IDS" >&2
    echo "" >&2
    echo "Valid IDs are listed in skills/registry.yaml." >&2
    echo "If you added a new skill, register it first." >&2
    echo "" >&2
    exit 1
  fi
fi

exit 0
