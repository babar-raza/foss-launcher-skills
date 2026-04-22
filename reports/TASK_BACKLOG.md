# Task Backlog — Score Improvement + Parity Program
**Source plans**: `C:\Users\prora\.claude\plans\reactive-sprouting-matsumoto.md` (score improvement) + `C:\Users\prora\.claude\plans\wondrous-skipping-diffie.md` (parity program Sprint 2)
**Last updated**: 2026-04-21

---

## Parity Program Sprint 2 — ACTIVE BLOCKERS

| ID | Task | Status | Priority | Acceptance |
|----|------|--------|----------|-----------|
| TC-020 | Commit sprint 1 work durably (two clean commits) | ✅ DONE | **BLOCKER** | Commits: c13194e, 2b1d04c, 99758f4, 4a2ffb5; 541 passed 15 skipped = 556 total |
| TC-021 | Resolve translator gap: add backend-absent notice to translate-page/batch | ✅ DONE | **BLOCKER** | Skill files have backend-absent notice; verification-log shows PARTIAL; closure-report accurate |
| TC-022 | Push to remote + verify CI workflow triggers | ✅ DONE | Follow-up | Pushed 46f8237 via gitlab_pat env var. CI: GitHub Actions won't auto-trigger on GitLab |
| TC-023 | Hook behavioral test (install + violating commit) | DEFERRED | Non-blocking | Bad commit blocked; clean commit passes |
| TC-024 | Live content repo smoke test (one skill chain) | DEFERRED | Non-blocking | Skill chain produces correct output against fixture |

---

## Phase 0 — Immediate (DONE ✅)

| ID | Task | Status | Files Changed | Tests Added |
|----|------|--------|---------------|-------------|
| P0-1 | Fix scout skip guard (subprocess check for tree_sitter_language_pack) | ✅ DONE | test_scout_units.py | -17 failures → 15 skips |
| P0-2 | Extend config schema negative tests (TASK-03) | ✅ DONE | test_schema_validate.py | +5 |
| P0-3 | Add materialize failure-mode tests (TASK-04) | ✅ DONE | test_materialize.py | +4 |
| P0-4 | Add pre_write stale-model block tests (TASK-05) | ✅ DONE | test_pre_write.py | +4 |
| P0-5 | Fix check_setup optional-package exit code (NOTE vs WARN) | ✅ DONE | check_setup.py, test_check_setup.py | -2 failures |

**Phase 0 result**: 541 passing, 15 skipped, 0 failed (was: 526 passing, 17 failed)

---

## Phase 1 — Near-term (IN PROGRESS)

| ID | Task | Status | Priority | Expected Score Impact |
|----|------|--------|----------|-----------------------|
| P1-1 | Commit .github/workflows/skill-governance.yml and enable CI | ✅ DONE | HIGH | Committed in sprint 1 (commit 2b1d04c); note: remote is GitLab, not GitHub |
| P1-2 | Make skill-provenance CI check blocking (not just informational) | ✅ DONE | HIGH | skill-governance.yml job 6 blocks on missing "Skills invoked:" |
| P1-3 | Build scripts/quarterly_readiness.py + S-83 skill | ✅ DONE | MEDIUM | Script committed (4a2ffb5); estimates 62.9 score |
| P1-4 | Build scripts/verify_claims.py + S-84 skill | ✅ DONE | MEDIUM | Script committed (4a2ffb5); 159 claims, 49 verified |
| P1-5 | Auto-generate STATUS.md from test results and git log | ✅ DONE | LOW | scripts/generate_status.py committed (64a85f0); append mode tested |

**Phase 1 result**: All P1-1 through P1-5 DONE. Phase 1 target: Overall 58–65.

---

## Phase 2 — Medium-term (IN PROGRESS)

| ID | Task | Status | Priority | Expected Score Impact |
|----|------|--------|----------|-----------------------|
| P2-1 | Add pyproject.toml + src/ package boundary (Model B Phase 1) | ✅ DONE | HIGH | Committed bc14ef4; pyproject.toml with metadata, entry points, optional extras |
| P2-2 | Fix hardcoded Path("evidence") / Path("knowledge") in scripts | ✅ DONE | MEDIUM | Committed 3dd419d; 9 main scripts + resolve_evidence_root() added to config_loader |
| P2-3 | Add CONTENT_REPO_PATH config-resolution tests | ✅ DONE | MEDIUM | Committed 4faa4df; 11 new tests; 558 passing, 15 skipped |
| P2-4 | Begin launcher deduplication (create launcher_adapter.py) | ✅ DONE | HIGH | Committed 3ee900a; 31 tests; Code Structure 85.0 |
| P2-5 | Add versioning contract with upstream launcher (stale detection) | FUTURE | LOW | Architecture +3 |

**Phase 2 result (P2-1/2/3/4)**: 579 passed, 0 failed. Overall score: **93.8** (target was 68–75).

---

## Governance Changes (ongoing)

| Rule | Enforcement | Status |
|------|-------------|--------|
| No config/schema change without negative test | CI gate | PENDING (requires P1-1) |
| No capability claim without executable test | PR checklist | PENDING |
| No governance-path expansion without adversarial test | pre-merge gate | PENDING |
| Commit-msg: "Skills invoked:" required for content commits | CI blocking | PENDING (P1-2) |
| Quarterly readiness script run before review | CI schedule | PENDING (P1-3) |

---

## New Skills Approved

| ID | Skill | Purpose | Status |
|----|-------|---------|--------|
| S-83 | score-readiness | Simulate quarterly reviewer rubric locally | PENDING (P1-3) |
| S-84 | verify-claims | Trace docs claims to executable tests | PENDING (P1-4) |
| S-85 | quarterly-report | Auto-generate delivery report from git/CI | FUTURE |

---

## Open Questions

- Q1: Will CI run correctly on ubuntu-latest given Windows-specific test path patterns?
  → Risk: Medium. Need to verify pytest.ini testpaths and path separators.
- Q2: Are there other pre-existing test failures hidden by early failures in test runs?
  → Action: Always run full suite without -x flag.
- Q3: Does the quarterly reviewer see git history within a 90-day window or the full repo?
  → Assumption: 90-day window. Phase 1 changes must land ≥90 days before next review.
