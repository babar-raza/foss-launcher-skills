#!/usr/bin/env bash
# simulate_pr_checks.sh — Local simulation of content-audit.yml CI checks.
#
# SYNC: This script mirrors .github/workflows/content-audit.yml step-for-step,
# including conditional logic. Last synchronized: 2026-04-25 (TC-03, TC-04, TC-05).
# When content-audit.yml changes, update this file to match.
#
# Runs the same scripts as the GitHub Actions workflow against the current branch,
# producing per-step pass/fail output. Results are stored in reports/proofs/
# for later audit.
#
# Usage:
#   bash scripts/ci/hooks/simulate_pr_checks.sh [--base <branch>] [--slug <slug>]
#
# Options:
#   --base <branch>  Base branch to compare against (default: origin/main)
#   --slug <slug>    Suffix for the proof bundle directory (default: pr-simulation-{date})
#
# The script captures per-step exit codes and writes them to a structured proof bundle.
# This provides local evidence of CI behavior without opening a real PR.
#
# Security: no eval, no unquoted variables. File lists use mapfile arrays.

set -uo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

# Resolve Python: prefer repo venv, fall back to python3
if [ -f "$REPO_ROOT/.venv/Scripts/python.exe" ]; then
    PYTHON="$REPO_ROOT/.venv/Scripts/python"
elif [ -f "$REPO_ROOT/.venv/bin/python" ]; then
    PYTHON="$REPO_ROOT/.venv/bin/python"
else
    PYTHON="python3"
fi
export PYTHON

BASE_BRANCH="origin/main"
DATE=$(date -u +"%Y%m%d")
SLUG="pr-simulation"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --base) BASE_BRANCH="$2"; shift 2 ;;
        --slug) SLUG="$2"; shift 2 ;;
        *) echo "Unknown argument: $1" >&2; exit 1 ;;
    esac
done

BUNDLE_DIR="${REPO_ROOT}/reports/proofs/${DATE}-${SLUG}"
mkdir -p "${BUNDLE_DIR}"
LOG_FILE="${BUNDLE_DIR}/commands.log"
RESULTS_FILE="${BUNDLE_DIR}/step-results.json"

echo "# PR Simulation — content-audit.yml steps" > "${LOG_FILE}"
echo "# Base: ${BASE_BRANCH}" >> "${LOG_FILE}"
echo "# Started: $(date -u +"%Y-%m-%dT%H:%M:%SZ")" >> "${LOG_FILE}"
echo "# Repo SHA: $(git rev-parse HEAD)" >> "${LOG_FILE}"
echo "" >> "${LOG_FILE}"

# Get changed files as arrays — safe for filenames with spaces
mapfile -t CHANGED_FILES < <(git diff --name-only "${BASE_BRANCH}...HEAD" -- 'content/**/*.md' 2>/dev/null || true)
mapfile -t CHANGED_ALL_FILES < <(git diff --name-only "${BASE_BRANCH}...HEAD" 2>/dev/null || true)
mapfile -t COMMIT_SHAS < <(git log "${BASE_BRANCH}...HEAD" --format='%H' -- 'content/**/*.md' 2>/dev/null || true)

# EVAL_FILES: English-only subset of CHANGED_FILES for content_eval (TC-05).
# Locale paths (e.g. content/docs.aspose.org/ar/..., content/kb.aspose.org/de/...) are
# excluded because content_eval has no locale knowledge artifacts and always emits a
# PIPELINE FAIL "Knowledge unavailable" for them, producing false blocking signals.
# blog.aspose.org and products.aspose.org and reference.aspose.org do not use locale
# prefixes, so they pass through unchanged.
mapfile -t EVAL_FILES < <(
    for f in "${CHANGED_FILES[@]}"; do
        # Skip locale paths: content/(docs|kb).aspose.org/{2-letter-code}/...
        # but keep content/(docs|kb).aspose.org/en/... (English)
        if [[ "$f" =~ ^content/(docs|kb)\.aspose\.org/([a-z]{2})/ ]]; then
            locale="${BASH_REMATCH[2]}"
            [[ "$locale" == "en" ]] && echo "$f"
        else
            echo "$f"
        fi
    done
)

echo "Changed content files: ${#CHANGED_FILES[@]}" >> "${LOG_FILE}"
echo "Eval-eligible content files (English-only): ${#EVAL_FILES[@]}" >> "${LOG_FILE}"
echo "All changed files: ${#CHANGED_ALL_FILES[@]}" >> "${LOG_FILE}"
echo "" >> "${LOG_FILE}"

# --------------------------------------------------------------------------
# Step runner — NO eval; commands passed as arrays via "$@"
# --------------------------------------------------------------------------

declare -A STEP_RESULTS
PASS=0
FAIL=0
WARN=0

run_step() {
    local name="$1"
    local blocking="$2"  # "blocking" or "advisory"
    shift 2
    # Execute command directly as an array — no eval, no word-splitting surprises.
    # Callers must pass the command as separate words (not a quoted string).

    echo ">>> STEP: $name ($blocking)" >> "${LOG_FILE}"
    echo "    command: $*" >> "${LOG_FILE}"
    echo "    started: $(date -u +"%Y-%m-%dT%H:%M:%SZ")" >> "${LOG_FILE}"

    set +e
    output=$("$@" 2>&1)
    exit_code=$?
    set -e

    echo "    exit_code: $exit_code" >> "${LOG_FILE}"
    echo "$output" >> "${LOG_FILE}"
    echo "" >> "${LOG_FILE}"

    if [ $exit_code -eq 0 ]; then
        echo "  PASS [$blocking]: $name"
        STEP_RESULTS["$name"]="PASS"
        PASS=$((PASS + 1))
    elif [ "$blocking" = "advisory" ]; then
        echo "  WARN [advisory]: $name (exit $exit_code)"
        STEP_RESULTS["$name"]="WARN"
        WARN=$((WARN + 1))
    else
        echo "  FAIL [blocking]: $name (exit $exit_code)"
        STEP_RESULTS["$name"]="FAIL"
        FAIL=$((FAIL + 1))
    fi
}

# --------------------------------------------------------------------------
# Run each workflow step
# --------------------------------------------------------------------------

cd "${REPO_ROOT}"

echo "=== Running content-audit.yml step simulation ==="
echo ""

run_step "Check reports/ not tracked (local-only boundary)" "blocking" \
    bash -c 'count=$(git ls-files reports/ | wc -l | tr -d " \t\r\n"); if [ "$count" -gt 0 ]; then echo "ERROR: $count file(s) tracked under reports/ -- violates local-only boundary:"; git ls-files reports/; exit 1; fi; echo "OK: reports/ contains 0 tracked files"'

run_step "Check blog slug hygiene" "blocking" \
    "$PYTHON" scripts/ci/checks/check-blog-slugs.py

run_step "Check content filename conventions" "blocking" \
    "$PYTHON" scripts/ci/checks/check_content_filenames.py

run_step "Run API accuracy audit" "advisory" \
    bash -c "\"$PYTHON\" scripts/pipeline/commands/content/audit.py all --json > /tmp/audit-results.json"

# Mirror CI: always run regression check regardless of audit exit code
run_step "Check for audit regressions" "blocking" \
    "$PYTHON" scripts/ci/checks/check_audit_regression.py /tmp/audit-results.json reports/audit/baseline-fail-counts.json

if [ "${#CHANGED_FILES[@]}" -gt 0 ]; then
    run_step "Check grade presence" "advisory" \
        env PYTHONPATH=scripts/pipeline "$PYTHON" scripts/pipeline/commands/governance/check_grade_presence.py --scope modified "${CHANGED_FILES[@]}"

    run_step "Check grade block integrity" "blocking" \
        env PYTHONPATH=scripts/pipeline "$PYTHON" scripts/pipeline/commands/governance/check_grade_integrity.py --files "${CHANGED_FILES[@]}"

    run_step "Check grade downgrade" "blocking" \
        env PYTHONPATH=scripts/pipeline "$PYTHON" scripts/pipeline/commands/governance/check_grade_downgrade.py "${CHANGED_FILES[@]}"

    run_step "Check manifest/frontmatter consistency (GUARD-04)" "blocking" \
        env PYTHONPATH=scripts/pipeline "$PYTHON" scripts/ci/checks/check_manifest_consistency.py "${CHANGED_FILES[@]}"

    run_step "Check grade churn (GUARD-02)" "blocking" \
        env PYTHONPATH=scripts/pipeline "$PYTHON" scripts/ci/checks/check_grade_churn.py --mode pr --base-branch "${BASE_BRANCH}"

    run_step "Check evaluator freeze (FREEZE-04)" "blocking" \
        env PYTHONPATH=scripts/pipeline "$PYTHON" scripts/ci/checks/check_evaluator_freeze.py

    if [ "${#EVAL_FILES[@]}" -gt 0 ]; then
        run_step "Strict content eval on modified files (TC-05)" "blocking" \
            env PYTHONPATH=scripts/pipeline "$PYTHON" -m content_eval evaluate --files "${EVAL_FILES[@]}" --strict
    else
        echo "  SKIP [TC-05]: No eval-eligible content files (all changed files are locale translations)"
    fi

    run_step "Validate frontmatter" "advisory" \
        env PYTHONPATH=scripts/pipeline "$PYTHON" scripts/pipeline/commands/content/validate_frontmatter.py "${CHANGED_FILES[@]}"
else
    echo "  SKIP: No changed content files -- skipping content-only checks"
fi

run_step "Translation coverage" "advisory" \
    env PYTHONPATH=scripts/pipeline "$PYTHON" scripts/pipeline/commands/ops/translation_coverage.py --json-out /tmp/translation_coverage.json

run_step "Check skill sync parity" "blocking" \
    env PYTHONPATH=scripts/pipeline "$PYTHON" scripts/pipeline/commands/ops/sync_skills.py --check

run_step "Check skill registry completeness" "advisory" \
    "$PYTHON" scripts/ci/checks/check_skill_registry.py

run_step "Check agent governance surface" "advisory" \
    "$PYTHON" scripts/ci/checks/check_agent_governance_surface.py --check-baseline

if [ "${#COMMIT_SHAS[@]}" -gt 0 ]; then
    # Skills invoked check -- inline (no subshell needed)
    missing=0
    for sha in "${COMMIT_SHAS[@]}"; do
        msg=$(git log -1 --format='%B' "$sha")
        if ! echo "$msg" | grep -qiE 'skills?\s*invoked'; then
            echo "  WARN: Commit $sha lacks 'Skills invoked:' field"
            missing=$((missing + 1))
        fi
    done
    if [ "$missing" -gt 0 ]; then
        STEP_RESULTS["Check Skills invoked declaration"]="WARN"
        WARN=$((WARN + 1))
        echo "  WARN [advisory]: Check Skills invoked declaration ($missing commits missing)"
    else
        STEP_RESULTS["Check Skills invoked declaration"]="PASS"
        PASS=$((PASS + 1))
        echo "  PASS [advisory]: Check Skills invoked declaration"
    fi
else
    echo "  SKIP: No content commits in range"
fi

if [ "${#CHANGED_ALL_FILES[@]}" -gt 0 ]; then
    run_step "Check forbidden-path override tokens" "blocking" \
        env PYTHONPATH=scripts/pipeline "$PYTHON" scripts/ci/checks/check_forbidden_overrides.py "${CHANGED_ALL_FILES[@]}"
fi

run_step "Check compliance proof bundles" "advisory" \
    "$PYTHON" scripts/ci/checks/check_proof_bundles.py

if [ "${#COMMIT_SHAS[@]}" -gt 0 ]; then
    run_step "Validate skill run records" "advisory" \
        "$PYTHON" scripts/ci/checks/check_skill_run_records.py --commits "${COMMIT_SHAS[@]}"
fi

# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------

echo ""
echo "=== Simulation complete ==="
echo "  PASS: $PASS"
echo "  FAIL: $FAIL  (blocking)"
echo "  WARN: $WARN  (advisory)"
echo ""

if [ $FAIL -gt 0 ]; then
    echo "  RESULT: This PR would FAIL CI ($FAIL blocking step(s) failed)"
    echo "  (See ${LOG_FILE} for details)"
    EXIT_CODE=1
else
    echo "  RESULT: This PR would PASS CI (all blocking steps passed)"
    EXIT_CODE=0
fi

# Write structured results and register bundle in INDEX.json
"$PYTHON" - <<PYEOF
import json
from pathlib import Path

bundle_id = "${DATE}-${SLUG}"
repo_root = Path("${REPO_ROOT}")
results_file = Path("${RESULTS_FILE}")
index_file = repo_root / "reports" / "proofs" / "INDEX.json"

results = {
    "bundle_id": bundle_id,
    "base_branch": "${BASE_BRANCH}",
    "repo_sha": "$(git rev-parse HEAD)",
    "simulated_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
    "changed_content_files": ${#CHANGED_FILES[@]},
    "summary": {"pass": ${PASS}, "fail": ${FAIL}, "warn": ${WARN}},
    "overall_result": "FAIL" if ${FAIL} > 0 else "PASS",
    "plan_reference": "2026-04-25-taskcard-codebase-verification-and-gap-healing.md (TC-03)"
}
with open(results_file, "w") as f:
    json.dump(results, f, indent=2)
print(f"Wrote results to {results_file}")

# Register bundle in INDEX.json (idempotent)
try:
    index = json.loads(index_file.read_text(encoding="utf-8")) if index_file.exists() else []
    if not isinstance(index, list):
        index = []
except (json.JSONDecodeError, OSError):
    index = []

if not any(e.get("bundle_id") == bundle_id for e in index):
    overall = "FAIL" if ${FAIL} > 0 else "PASS"
    entry = {
        "bundle_id": bundle_id,
        "path": f"reports/proofs/{bundle_id}/",
        "retroactive": False,
        "summary": (
            f"PR simulation: ${PASS} pass, ${FAIL} fail, ${WARN} warn. "
            f"Overall: {overall}. Base: ${BASE_BRANCH}. "
            f"SHA: $(git rev-parse HEAD)."
        ),
    }
    index.append(entry)
    index_file.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    print(f"Registered bundle {bundle_id} in INDEX.json")
else:
    print(f"Bundle {bundle_id} already registered in INDEX.json (skipped)")
PYEOF

exit $EXIT_CODE
