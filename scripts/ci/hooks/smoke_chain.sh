#!/bin/bash
set -e
REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

# Resolve Python: repo .venv only (DR-01 — no system Python fallback).
# Source find_python.sh which sets $PYTHON and exits 1 if .venv absent.
# shellcheck source=scripts/ci/hooks/find_python.sh
if ! source "$REPO_ROOT/scripts/ci/hooks/find_python.sh" 2>/dev/null; then
    echo "ERROR: .venv Python not found. Run: bash scripts/ci/hooks/repair_venv.sh" >&2
    exit 1
fi
if [ -z "${PYTHON:-}" ]; then
    echo "ERROR: .venv Python not resolved. Run: bash scripts/ci/hooks/repair_venv.sh" >&2
    exit 1
fi

echo "=== 1. Knowledge discovery ==="
(cd scripts/pipeline && $PYTHON -c "import sys; sys.path.insert(0,'.'); from lib.content_discovery import discover_products; assert len(discover_products()) >= 13, 'Expected 13+ products'")

echo "=== 2. Site planner ==="
$PYTHON scripts/pipeline/commands/launch/site_planner.py note python --dry-run > /dev/null

echo "=== 3. Audit single product ==="
$PYTHON scripts/pipeline/commands/content/audit.py note python 2>&1 | grep -q "files"

echo "=== 4. Content eval ==="
$PYTHON -m scripts.pipeline.content_eval evaluate note python --evaluators structure 2>&1 | grep -q "Pages:"

echo "=== 5. Path guard ==="
$PYTHON scripts/pipeline/commands/governance/path_guard.py "content/docs.aspose.org/en/note/python/index.md" > /dev/null
! $PYTHON scripts/pipeline/commands/governance/path_guard.py "themes/base.html" 2>/dev/null

echo "=== 6. Grade integrity ==="
$PYTHON scripts/pipeline/commands/governance/check_grade_integrity.py --json 2>/dev/null | $PYTHON -c "import json,sys; d=json.load(sys.stdin); assert d['anomaly_count']==0, f'Anomalies: {d[\"anomaly_count\"]}'"

echo "=== 6b. Evaluator freeze gate ==="
$PYTHON scripts/ci/checks/check_evaluator_freeze.py

echo "=== 7. Skill sync parity ==="
$PYTHON scripts/pipeline/commands/ops/sync_skills.py --check 2>&1 | grep -q "PASS"

echo "=== 8. Agent governance surface baseline ==="
$PYTHON scripts/ci/checks/check_agent_governance_surface.py --check-baseline > /dev/null

echo "=== 9. Phase store round-trip ==="
$PYTHON scripts/pipeline/commands/ops/project_phase_store.py set __smoke__ __smoke__ test_key true --state-file /tmp/smoke_state.json 2>/dev/null
$PYTHON scripts/pipeline/commands/ops/project_phase_store.py get __smoke__ __smoke__ test_key --state-file /tmp/smoke_state.json 2>/dev/null | grep -qi "true"
$PYTHON scripts/pipeline/commands/ops/project_phase_store.py clear __smoke__ __smoke__ --state-file /tmp/smoke_state.json 2>/dev/null

echo ""
echo "SMOKE CHAIN: ALL PASSED"
