# Phase 07 — Validator Log Summary

**Date:** 2026-06-11
**Sprint:** Hardening sprint post-73d2fc8

---

## GATE-0 Results

### local_gate.py

**Command:** `python scripts/local_gate.py`

```
============================================================
GATE: Skill Registry Validation
============================================================
  -> PASS

============================================================
GATE: Test Suite
============================================================
  -> PASS

============================================================
GATE: SAST (bandit)
============================================================
  -> PASS

============================================================
GATE: Dependency Audit
============================================================
  -> PASS

============================================================
LOCAL GATE SUMMARY
============================================================
  [PASS] Skill Registry Validation
  [PASS] Test Suite
  [PASS] SAST (bandit)
  [PASS] Dependency Audit

All gates passed.
```

**Verdict:** ALL GATES PASS

---

### pytest with --cov-fail-under=12

**Command:** `.venv/Scripts/python -m pytest tests/ -q --cov=scripts --cov-fail-under=12 -m "not scout" --ignore=tests/test_e2e_pipeline.py`

**Result:** 818 passed, 17 deselected in 113.94s
**Coverage:** 11.96% (TOTAL: 39,412 statements, 34,698 missed)
**Threshold check:** FAIL — 11.96% < 12.00% (margin: 0.04%)

**Note:** This is a pre-existing condition, not a regression introduced by this sprint.
The 12% threshold was set in 73d2fc8. The measured coverage at that time was also ~11.96%.
The pytest command requires exactly 12.00% or above; 11.96% fails by a rounding issue.
local_gate.py does not use --cov-fail-under and therefore passes.
The structured logging module added in Lane 6 adds new testable code that may push
coverage above 12.00%.

---

## GATE-1 Results (Post-Hardening)

### pytest with --cov-fail-under=12 (post-Lane-6)

**Command:** `.venv/Scripts/python -m pytest tests/ -q --cov=scripts --cov-fail-under=12 -m "not scout" --ignore=tests/test_e2e_pipeline.py`

**Result:** 827 passed, 17 deselected
**Coverage:** 12.01% (TOTAL: 39,433 statements)
**Threshold check:** PASS — 12.01% >= 12.00%

Note: Coverage crossed the threshold after adding structured_log.py (Lane 6).
The 9 new tests in test_structured_log.py cover the structured_log module,
adding 21 new covered statements to push total from 11.96% to 12.01%.

### local_gate.py (post-all-lanes)

All 4 gates PASS (same as GATE-0).

### Artifact Verification

| Check | Command | Result |
|-------|---------|--------|
| RC-008 concurrency note | `grep -c "Concurrency" run_outcome_log.py` | 1 |
| CHANGELOG versioned entry | `grep "## \[0.2.0\]" CHANGELOG.md` | MATCH |
| Release workflow | `ls .github/workflows/release.yml` | EXISTS |
| SLA definitions | `ls docs/governance/sla.md` | EXISTS |
| Structured logger | `ls scripts/pipeline/utils/structured_log.py` | EXISTS |
| Evidence bundle | `ls reports/.../ \| wc -l` | 25 files |
| Clean working tree | `git status --short` | CLEAN |
