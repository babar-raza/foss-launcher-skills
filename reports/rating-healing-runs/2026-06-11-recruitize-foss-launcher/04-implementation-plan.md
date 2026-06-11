# Phase 04 — Implementation Plan

**Sprint:** 2026-06-11-recruitize-foss-launcher
**Approach:** Lane-based execution ordered by axis impact

---

## Execution Lanes (Original Sprint 73d2fc8)

### Lane 1: Commit Critical Untracked Files (RC-001, RC-002, RC-005)
**Committed in:** e37b4a3, 303a7f2
**Files:** CODEOWNERS, CHANGELOG.md, CONTRIBUTING.md, SECURITY.md, docs/governance/ (11 files),
adaptive_retry.py, run_outcome_log.py, 4 test files

### Lane 2: Create ADR Directory (RC-003)
**Committed in:** 73d2fc8
**Files created:**
- docs/adr/001-skill-chain-design.md
- docs/adr/002-path-guard-governance.md
- docs/adr/003-evidence-first-content.md

### Lane 3: Fix Input Validation (RC-007)
**Committed in:** 73d2fc8
**Files modified:**
- scripts/pipeline/commands/ops/adaptive_retry.py (added ValueError guards)
- tests/test_adaptive_retry.py (added 5 new tests)

### Lane 4: CI Coverage Threshold (RC-004)
**Committed in:** 73d2fc8
**Change:** .github/workflows/pipeline-tests.yml — raised --cov-fail-under from 11 to 12
**Note:** Plan target was 30%; actual coverage measured at 11.96%, making 30% unachievable
without substantial new test work. Threshold raised to achievable 12%.

### Lane 5: Runbook Documentation (RC-009)
**Committed in:** 73d2fc8
**Files created:**
- docs/runbooks/skill-failure-recovery.md
- docs/runbooks/stale-knowledge-recovery.md

---

## Hardening Sprint (Post-73d2fc8)

After the initial sprint, a hardening audit identified gaps. The following lanes were added:

### Lane H1: RC-008 Concurrency Note
**Committed in:** 3511124
**File:** scripts/pipeline/commands/ops/run_outcome_log.py
**Change:** Added Concurrency section to module docstring (RC-008 was claimed done in 73d2fc8 but was not)

### Lane H2: Evidence Bundle Completion
**Files:** 13 missing phase artifacts in reports/rating-healing-runs/

### Lane H3: CHANGELOG Versioned Entry
**File:** CHANGELOG.md — add ## [0.1.0] section

### Lane H4: Release Workflow
**File:** .github/workflows/release.yml — semver tag triggered release

### Lane H5: SLA Definitions
**File:** docs/governance/sla.md

### Lane H6: Structured Logging
**Files:** scripts/pipeline/utils/structured_log.py, tests/test_structured_log.py

---

## Score Impact Target

| Axis | Pre-Sprint | Post-73d2fc8 | Post-Hardening |
|------|-----------|-------------|----------------|
| A | ~4.0 | ~5.0 | ~5.0 |
| P | ~3.0 | ~4.0 | ~4.5 |
| R | ~1.5 | ~3.5 | ~4.0 |
| S | ~8-15 | ~35-45 | ~40-50 |
