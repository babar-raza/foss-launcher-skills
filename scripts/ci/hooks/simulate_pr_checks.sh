#!/usr/bin/env bash
# simulate_pr_checks.sh — Local simulation of content-governance-checks.yml CI checks.
#
# SYNC: This script mirrors .github/workflows/content-governance-checks.yml
# step-for-step, including advisory (continue-on-error) vs. blocking framing.
# Re-synchronized 2026-08-16 (repo usability/operability hardening pass) — the
# previous version mirrored .github/workflows/content-audit.yml, which is
# pull_request-triggered only and structurally never fires against this repo's
# real push-to-main workflow (confirmed via that workflow's own header comment,
# dated 2026-08-14, TC-CIA-06/TC-CIR-02). content-governance-checks.yml is the
# live push-triggered gate; several content-audit.yml-era steps below were
# deliberately dropped because they either have another live local/push
# enforcement point already (filename conventions, reports/ boundary, skill
# run records via commit-msg-skills.sh, forbidden-path override tokens via
# pre-commit-audit.sh Step 21) or were advisory-only and not migrated
# upstream either (translation coverage, agent governance surface, compliance
# proof bundles) — see content-governance-checks.yml's own header for the
# full accounting. When content-governance-checks.yml changes, update this
# file to match.
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

echo "Changed content files: ${#CHANGED_FILES[@]}" >> "${LOG_FILE}"
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

echo "=== Running content-governance-checks.yml step simulation ==="
echo ""

run_step "Check blog slug hygiene" "blocking" \
    "$PYTHON" scripts/ci/checks/check-blog-slugs.py

run_step "Check blog family route coverage" "blocking" \
    "$PYTHON" scripts/ci/checks/check_blog_family_routes.py

# advisory in CI (continue-on-error: true, landing state 2026-08-14 — 7 blog
# platform dirs are missing _index.md; promote to blocking once fixed)
run_step "Check blog platform indexes" "advisory" \
    "$PYTHON" scripts/ci/checks/check_blog_platform_indexes.py

run_step "Check family icon uniqueness (V-I-01..04)" "blocking" \
    "$PYTHON" scripts/ci/checks/check_family_icon_uniqueness.py

# advisory in CI (continue-on-error: true)
run_step "Run API accuracy audit (full corpus)" "advisory" \
    bash -c "\"$PYTHON\" scripts/pipeline/commands/content/audit.py all --json > /tmp/audit-results.json"

# advisory in CI (continue-on-error: true, landing state 2026-08-14 — real
# pre-existing regressions in tex/python, words/python not yet reconciled)
run_step "Check for audit regressions (landing state)" "advisory" \
    "$PYTHON" scripts/ci/checks/check_audit_regression.py /tmp/audit-results.json reports/audit/baseline-fail-counts.json

if [ "${#CHANGED_FILES[@]}" -gt 0 ]; then
    run_step "Check grade presence on changed files" "blocking" \
        env PYTHONPATH=scripts/pipeline "$PYTHON" scripts/pipeline/commands/governance/check_grade_presence.py --scope modified "${CHANGED_FILES[@]}"

    # advisory in CI (continue-on-error: true, landing state 2026-08-14)
    run_step "Check grade block integrity (landing state)" "advisory" \
        env PYTHONPATH=scripts/pipeline "$PYTHON" scripts/pipeline/commands/governance/check_grade_integrity.py --files "${CHANGED_FILES[@]}"

    run_step "Check manifest/frontmatter consistency (GUARD-04)" "blocking" \
        env PYTHONPATH=scripts/pipeline "$PYTHON" scripts/ci/checks/check_manifest_consistency.py "${CHANGED_FILES[@]}"

    run_step "Validate frontmatter structure, all locales" "blocking" \
        env PYTHONPATH=scripts/pipeline "$PYTHON" scripts/pipeline/commands/content/validate_frontmatter.py "${CHANGED_FILES[@]}"
else
    echo "  SKIP: No changed content files -- skipping content-diff-gated checks"
fi

# advisory in CI (continue-on-error: true, landing state 2026-08-14 — a
# suspected EVALUATOR_FREEZE_VERSION string-handling bug, not a real freeze
# violation; needs its own root-cause fix)
run_step "Check evaluator freeze (FREEZE-04, landing state)" "advisory" \
    env PYTHONPATH=scripts/pipeline "$PYTHON" scripts/ci/checks/check_evaluator_freeze.py

run_step "Check skill documentation coverage" "blocking" \
    "$PYTHON" scripts/ci/checks/check_skill_readme_coverage.py

run_step "Check skill registry completeness" "blocking" \
    "$PYTHON" scripts/ci/checks/check_skill_registry.py

# advisory in CI (continue-on-error: true, landing state 2026-08-14 — real
# pre-existing DAR gaps not yet reconciled)
run_step "Check DAR coverage alignment (landing state)" "advisory" \
    "$PYTHON" scripts/ci/checks/check_dar_coverage.py

run_step "Check DAR-table skill-ID accuracy (RPR-G-02)" "blocking" \
    "$PYTHON" scripts/ci/checks/check_dar_table_accuracy.py

run_step "Check pipeline path integrity" "blocking" \
    "$PYTHON" scripts/ci/checks/check_pipeline_path_integrity.py

run_step "Check clone cache refs (no foss-launcher)" "blocking" \
    "$PYTHON" scripts/ci/checks/check_clone_cache_refs.py

# advisory in CI (continue-on-error: true, landing state 2026-08-14 — 2 real
# pre-existing registration gaps not yet reconciled)
run_step "Check pipeline script registration (landing state)" "advisory" \
    "$PYTHON" scripts/ci/checks/check_pipeline_registration.py --fail-test-gaps

run_step "Hugo build verification (products.aspose.org)" "blocking" \
    bash scripts/ci/hooks/check_hugo_build.sh products.aspose.org

# Forbidden-path override tokens and "Skills invoked" commit provenance are
# NOT part of content-governance-checks.yml (its own header: already enforced
# locally at commit time — pre-commit-audit.sh Step 21 for override tokens,
# commit-msg-skills.sh for the Skills-invoked trailer). Not re-run here to
# keep this script an honest mirror of the live push gate; run
# `bash scripts/pre-commit-audit.sh` / `bash scripts/pre-push-audit.sh`
# separately for those.

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
    "plan_reference": "reports/skill-gaps/2026-08-16-repo-usability-operability-audit.md (re-mirrored to content-governance-checks.yml)"
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
