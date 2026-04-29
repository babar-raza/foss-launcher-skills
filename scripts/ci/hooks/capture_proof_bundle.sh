#!/usr/bin/env bash
# capture_proof_bundle.sh — Capture a structured proof bundle for a governance operation.
#
# Usage:
#   scripts/ci/hooks/capture_proof_bundle.sh <slug> [command1] [command2] ...
#
# Creates: reports/proofs/{YYYYMMDD}-{slug}/
#   manifest.json           — structured metadata
#   commands.log            — verbatim stdout+stderr per command with exit codes
#   diff.patch              — git diff at time of bundle creation
#   referenced_files.json  — placeholder; populate manually after the run
#
# Example:
#   scripts/ci/hooks/capture_proof_bundle.sh family-sync-verify \
#     "python scripts/pipeline/commands/governance/path_guard.py AGENTS.md" \
#     "python scripts/ci/checks/check_dar_coverage.py"
#
# The bundle is written to reports/proofs/ which is in the git allowlist.

set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 <slug> [command1] [command2] ..." >&2
    exit 1
fi

SLUG="$1"
shift

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
DATE=$(date -u +"%Y%m%d")
BUNDLE_DIR="${REPO_ROOT}/reports/proofs/${DATE}-${SLUG}"
mkdir -p "${BUNDLE_DIR}"

LOG_FILE="${BUNDLE_DIR}/commands.log"
MANIFEST_FILE="${BUNDLE_DIR}/manifest.json"
DIFF_FILE="${BUNDLE_DIR}/diff.patch"
REFS_FILE="${BUNDLE_DIR}/referenced_files.json"

# --------------------------------------------------------------------------
# Capture commands
# --------------------------------------------------------------------------

echo "# Proof bundle: ${DATE}-${SLUG}" > "${LOG_FILE}"
echo "# Captured: $(date -u +"%Y-%m-%dT%H:%M:%SZ")" >> "${LOG_FILE}"
echo "# Repo SHA: $(git rev-parse HEAD 2>/dev/null || echo 'unknown')" >> "${LOG_FILE}"
echo "" >> "${LOG_FILE}"

OVERALL_STATUS=0
for CMD in "$@"; do
    echo ">>> COMMAND: ${CMD}" >> "${LOG_FILE}"
    echo "    started: $(date -u +"%Y-%m-%dT%H:%M:%SZ")" >> "${LOG_FILE}"
    # Run the command, capture stdout+stderr, record exit code
    set +e
    OUTPUT=$(eval "${CMD}" 2>&1)
    EXIT_CODE=$?
    set -e
    echo "    exit_code: ${EXIT_CODE}" >> "${LOG_FILE}"
    echo "${OUTPUT}" >> "${LOG_FILE}"
    echo "" >> "${LOG_FILE}"
    if [ ${EXIT_CODE} -ne 0 ]; then
        OVERALL_STATUS=${EXIT_CODE}
    fi
done

echo "# Bundle overall status: ${OVERALL_STATUS}" >> "${LOG_FILE}"

# --------------------------------------------------------------------------
# Capture git diff
# --------------------------------------------------------------------------

git diff HEAD > "${DIFF_FILE}" 2>/dev/null || echo "# no diff available" > "${DIFF_FILE}"
git diff --staged >> "${DIFF_FILE}" 2>/dev/null || true

# --------------------------------------------------------------------------
# Write manifest
# --------------------------------------------------------------------------

REPO_SHA=$(git rev-parse HEAD 2>/dev/null || echo "unknown")
# Try to detect agent model from env; fall back to unknown
MODEL="${CLAUDE_MODEL:-unknown}"

cat > "${MANIFEST_FILE}" << MANIFEST_EOF
{
  "bundle_id": "${DATE}-${SLUG}",
  "created_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "repo_sha": "${REPO_SHA}",
  "agent_model": "${MODEL}",
  "plan_references": [],
  "tools_used": [],
  "findings_summary": "",
  "gaps_identified": [],
  "related_observation": "",
  "retroactive": false
}
MANIFEST_EOF

# --------------------------------------------------------------------------
# Write placeholder referenced_files.json
# --------------------------------------------------------------------------

echo "[]" > "${REFS_FILE}"

echo "Proof bundle created: ${BUNDLE_DIR}"
echo "  commands.log: $(wc -l < "${LOG_FILE}") lines"
echo "  diff.patch: $(wc -l < "${DIFF_FILE}") lines"
echo "  Edit manifest.json to add plan_references, findings_summary, etc."
exit ${OVERALL_STATUS}
