#!/usr/bin/env bash
# verify_llm_routing.sh — Post-implementation verification for LLM router migration.
#
# Runs all checks defined in TC-06. Exit 0 = all passed, exit 1 = failure.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$REPO_ROOT"

PASS=0
FAIL=0

check() {
    local desc="$1"
    shift
    echo -n "  [$desc] ... "
    if "$@" > /dev/null 2>&1; then
        echo "PASS"
        PASS=$((PASS + 1))
    else
        echo "FAIL"
        FAIL=$((FAIL + 1))
    fi
}

echo "=== LLM Routing Verification ==="
echo

# 1. LLM router unit tests
echo "1. LLM Router tests"
check "test_llm_router.py" python -m pytest -q scripts/pipeline/tests/test_llm_router.py -k "not Live"

# 2. Tier3Result tests
echo "2. Tier3Result tests"
check "test_tier3_result.py" python -m pytest -q scripts/pipeline/tests/test_tier3_result.py

# 3. Existing tier3 tests (regression)
echo "3. Tier3 regression tests"
check "test_tier3_demotion.py" python -m pytest -q scripts/pipeline/tests/test_tier3_demotion.py

# 4. Enrich tests
echo "4. Enrich tests"
check "test_enrich.py" python -m pytest -q scripts/pipeline/tests/test_enrich.py

# 5. Probe with no key → not_configured
echo "5. Probe (no key)"
check "probe_no_key" bash -c 'PROFESSIONALIZE_API_KEY="" python scripts/pipeline/commands/ops/llm_router.py --probe --provider professionalize 2>&1 | grep -q "not_configured"'

# 6. _TIER3_UNAVAILABLE deleted
echo "6. _TIER3_UNAVAILABLE deleted"
check "no_sentinel" bash -c '! grep -n "_TIER3_UNAVAILABLE" scripts/gap-eval/src/run.py | grep -v "docstring\|Replaces"'

# 7. Governance text fixed
echo "7. Governance alignment"
check "no_old_text" bash -c '! grep -q "empty enrichment is valid" .claude/commands/knowledge-enrich.md'

# 8. Probe writes artifact
echo "8. Probe artifact"
check "probe_artifact" bash -c 'python scripts/pipeline/commands/ops/llm_router.py --probe 2>&1 | grep -q "Probe artifact"'

echo
echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
