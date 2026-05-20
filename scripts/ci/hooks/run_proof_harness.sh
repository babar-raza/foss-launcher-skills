#!/bin/bash
# run_proof_harness.sh — Local CI behavior proof harness.
# Tests each scenario independently and captures outcomes to a proof bundle.
#
# Usage: bash scripts/ci/hooks/run_proof_harness.sh
#
# Exit codes:
#   0  All scenarios matched expected outcomes
#   1  One or more scenarios had unexpected outcomes

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)

# Resolve Python: prefer repo venv, fall back to python3
if [ -f "$REPO_ROOT/.venv/Scripts/python.exe" ]; then
    PYTHON="$REPO_ROOT/.venv/Scripts/python"
elif [ -f "$REPO_ROOT/.venv/bin/python" ]; then
    PYTHON="$REPO_ROOT/.venv/bin/python"
else
    PYTHON="python3"
fi
# Export so subshells spawned by bash -c in run_scenario() can resolve $PYTHON
export PYTHON
BUNDLE_DIR="$REPO_ROOT/reports/proof-bundles"
TODAY=$(date -u +%Y-%m-%d)
OUTPUT_BUNDLE="$BUNDLE_DIR/ci-harness-$TODAY.json"

mkdir -p "$BUNDLE_DIR"

echo "=== PR-Path Proof Harness ==="
echo "Running $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo ""

pass_count=0
fail_count=0
results_json="["
first_result=true

run_scenario() {
    local name="$1"
    local expected="$2"  # PASS or FAIL
    local description="$3"
    local test_cmd="$4"

    echo "--- Scenario: $name ($expected expected) ---"
    echo "  $description"

    # Capture output and exit code safely without set -e interference
    actual_output=$(bash -c "$test_cmd" 2>&1)
    actual_exit=$?

    if [ "$expected" = "PASS" ] && [ $actual_exit -eq 0 ]; then
        actual="PASS"
        correct="true"
        echo "  RESULT: PASS (correct)"
        pass_count=$((pass_count + 1))
    elif [ "$expected" = "FAIL" ] && [ $actual_exit -ne 0 ]; then
        actual="FAIL"
        correct="true"
        echo "  RESULT: FAIL (correct)"
        pass_count=$((pass_count + 1))
    else
        actual=$([ $actual_exit -eq 0 ] && echo "PASS" || echo "FAIL")
        correct="false"
        echo "  RESULT: $actual (UNEXPECTED — expected $expected)"
        fail_count=$((fail_count + 1))
    fi

    # Build JSON entry
    escaped_desc=$(echo "$description" | sed 's/"/\\"/g')
    escaped_out=$(echo "$actual_output" | head -3 | sed 's/"/\\"/g' | tr '\n' '|')
    entry="{\"name\":\"$name\",\"description\":\"$escaped_desc\",\"expected\":\"$expected\",\"actual\":\"$actual\",\"correct\":$correct,\"exit_code\":$actual_exit,\"output_preview\":\"$escaped_out\"}"

    if [ "$first_result" = "true" ]; then
        results_json="${results_json}${entry}"
        first_result=false
    else
        results_json="${results_json},${entry}"
    fi

    echo ""
}

# ---------------------------------------------------------------------------
# Scenario 1: Path guard allows content files
# ---------------------------------------------------------------------------
run_scenario \
    "path-guard-allows-content" \
    "PASS" \
    "path_guard.py must ALLOW content/ files" \
    "$PYTHON '$REPO_ROOT/scripts/pipeline/commands/governance/path_guard.py' 'content/docs.aspose.org/en/3d/python/developer-guide/rendering.md'"

# ---------------------------------------------------------------------------
# Scenario 2: Path guard blocks AGENTS.md
# ---------------------------------------------------------------------------
run_scenario \
    "path-guard-blocks-agents-md" \
    "FAIL" \
    "path_guard.py must DENY AGENTS.md (exit 2)" \
    "$PYTHON '$REPO_ROOT/scripts/pipeline/commands/governance/path_guard.py' 'AGENTS.md'"

# ---------------------------------------------------------------------------
# Scenario 3: Path guard blocks skills/ prefix
# ---------------------------------------------------------------------------
run_scenario \
    "path-guard-blocks-skills-dir" \
    "FAIL" \
    "path_guard.py must DENY skills/family-sync.md (exit 2)" \
    "$PYTHON '$REPO_ROOT/scripts/pipeline/commands/governance/path_guard.py' 'skills/family-sync.md'"

# ---------------------------------------------------------------------------
# Scenarios 4–5 removed (2026-04-17, plan compiled-giggling-hippo.md TC-01/TC-04):
# check_override.py reads the legacy overrides/active-override.json path at repo root.
# The active override mechanism uses reports/overrides/pending/ via override_manager.py.
# The overrides/ directory no longer exists; scenario 5 was broken (cat write failed
# silently, leaving no file → always BLOCKED → scenario expected PASS but got FAIL).
# check_override.py is called only from this harness; it is not part of any active hook
# or workflow. Both scenarios are removed rather than updated.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Scenario 6: validate_skill_ids.py accepts valid IDs
# ---------------------------------------------------------------------------
run_scenario \
    "skill-validator-accepts-valid-ids" \
    "PASS" \
    "validate_skill_ids.py must exit 0 for S-01 S-23 S-48" \
    "$PYTHON '$REPO_ROOT/scripts/ci/checks/validate_skill_ids.py' S-01 S-23 S-48"

# ---------------------------------------------------------------------------
# Scenario 7: validate_skill_ids.py rejects unknown IDs
# ---------------------------------------------------------------------------
run_scenario \
    "skill-validator-rejects-unknown-ids" \
    "FAIL" \
    "validate_skill_ids.py must exit 1 for S-999" \
    "$PYTHON '$REPO_ROOT/scripts/ci/checks/validate_skill_ids.py' S-999"

# ---------------------------------------------------------------------------
# Scenario 8: check_pr_override_compliance.py passes for allowed files
# ---------------------------------------------------------------------------
run_scenario \
    "pr-override-passes-for-allowed-files" \
    "PASS" \
    "check_pr_override_compliance.py must exit 0 for content/ files" \
    "PYTHONPATH='$REPO_ROOT/scripts/pipeline' $PYTHON '$REPO_ROOT/scripts/ci/checks/check_pr_override_compliance.py' 'content/docs.aspose.org/en/3d/python/developer-guide/rendering.md'"

# ---------------------------------------------------------------------------
# Scenario 9: check_pr_override_compliance.py fails for forbidden files without archived token
# ---------------------------------------------------------------------------
run_scenario \
    "pr-override-fails-for-forbidden-without-token" \
    "FAIL" \
    "check_pr_override_compliance.py must exit 1 for themes/ file without archived token" \
    "PYTHONPATH='$REPO_ROOT/scripts/pipeline' $PYTHON '$REPO_ROOT/scripts/ci/checks/check_pr_override_compliance.py' 'themes/hypothetical/style.css'"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
results_json="${results_json}]"
total=$((pass_count + fail_count))

echo "=== Harness Summary ==="
echo "  Total scenarios: $total"
echo "  Correct: $pass_count"
echo "  Incorrect: $fail_count"

if [ $fail_count -eq 0 ]; then
    all_correct="true"
    echo "  All correct: true"
else
    all_correct="false"
    echo "  All correct: false"
fi

# Write proof bundle
cat > "$OUTPUT_BUNDLE" << BUNDLE_EOF
{
  "schema_version": "1.0",
  "event_type": "pr_path_proof_harness",
  "harness_run_at": "$(date -u '+%Y-%m-%dT%H:%M:%SZ')",
  "total_scenarios": $total,
  "pass_count": $pass_count,
  "fail_count": $fail_count,
  "all_correct": $all_correct,
  "scenarios": $results_json
}
BUNDLE_EOF

echo "  Proof bundle written: $OUTPUT_BUNDLE"

if [ $fail_count -gt 0 ]; then
    echo ""
    echo "HARNESS FAILED: $fail_count scenario(s) had unexpected outcomes."
    exit 1
fi

echo ""
echo "HARNESS PASSED: all $total scenarios matched expected outcomes."
exit 0
