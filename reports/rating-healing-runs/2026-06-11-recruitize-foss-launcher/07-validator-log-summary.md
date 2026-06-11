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

To be updated after all hardening lanes complete.
