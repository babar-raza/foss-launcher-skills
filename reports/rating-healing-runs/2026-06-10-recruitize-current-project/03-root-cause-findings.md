# Phase 3 — Root Cause Findings

**Sprint:** 2026-06-10-recruitize-current-project

---

## RC-RATE-001 — Coverage Threshold Discrepancy

**SCORE DIMENSION DAMAGED:** Engineering / qualityGating

**CURRENT SCORE:** 4/9

**SURFACE SYMPTOM:** pyproject.toml has `fail_under = 11` while the project targets 70% in intent.

**BASE CAUSE:** pyproject.toml was not updated when CI was hardened. Earlier commit `fix(ci): install git globally, lower coverage threshold to 11%` lowered the threshold temporarily. The package-level config was never restored.

**CAUSAL CHAIN:** Reviewer sees 11% package-level threshold → infers quality gate is weak → qualityGating stays at ~4/9 instead of 6/9.

**TARGET PROJECT EVIDENCE:** `pyproject.toml` line 68: `fail_under = 11`

**REVIEWER MODEL EVIDENCE:** qualityGating subdimension penalizes absence of enforced coverage thresholds.

**REALITY CLASSIFICATION:** real source/logic weakness (configuration)

**RATING IMPACT:** qualityGating ~4→6/9 (+2 points)

**REMEDIATION TYPE:** source fix (pyproject.toml)

**PROOF NEEDED:** `python -m pytest --cov=scripts --cov-fail-under=70 tests/` exits 0

---

## RC-RATE-002 — CI Coverage Gate Not Explicit

**SCORE DIMENSION DAMAGED:** Engineering / qualityGating

**CURRENT SCORE:** 4/9

**SURFACE SYMPTOM:** CI pytest command lacks `--cov-fail-under=70` flag.

**BASE CAUSE:** When threshold was lowered to 11%, the CI command was not updated to enforce 70%. The CI currently relies on pyproject.toml's threshold (11%).

**CAUSAL CHAIN:** Without explicit `--cov-fail-under` in CI, the reviewer sees no hard coverage gate in the workflow file.

**TARGET PROJECT EVIDENCE:** `.github/workflows/pipeline-tests.yml` line 29: no `--cov-fail-under` in pytest command

**REVIEWER MODEL EVIDENCE:** qualityGating checks for explicit quality gates in CI.

**REALITY CLASSIFICATION:** CI/local gate weakness

**RATING IMPACT:** qualityGating subdimension improvement (combined with RC-RATE-001)

**REMEDIATION TYPE:** CI/local gate fix

**PROOF NEEDED:** CI command shows `--cov-fail-under=70`

---

## RC-RATE-003 — Missing CHANGELOG.md

**SCORE DIMENSION DAMAGED:** Readiness / releaseDiscipline

**CURRENT SCORE:** 2/9

**SURFACE SYMPTOM:** No CHANGELOG.md in the repository root.

**BASE CAUSE:** Release discipline was not formalized despite 30+ commits of active development.

**CAUSAL CHAIN:** Reviewer checks for CHANGELOG → not found → releaseDiscipline stays at 2/9.

**TARGET PROJECT EVIDENCE:** `ls *.md` — no CHANGELOG.md exists. `pyproject.toml`: `version = "0.1.0"` but no corresponding change history.

**REVIEWER MODEL EVIDENCE:** releaseDiscipline: "Versioned releases with changelog and process docs" = 4-5/9 minimum.

**REALITY CLASSIFICATION:** documentation trust weakness

**RATING IMPACT:** releaseDiscipline 2→5/9 (+3 points)

**REMEDIATION TYPE:** docs/source consistency fix (creates CHANGELOG.md)

**PROOF NEEDED:** CHANGELOG.md exists at repo root with Keep A Changelog format

---

## RC-RATE-004 — Observability Lacks Correlation IDs and Metrics Summary

**SCORE DIMENSION DAMAGED:** Engineering / observability

**CURRENT SCORE:** 2/9

**SURFACE SYMPTOM:** `run_outcome_log.py` appends structured JSONL but each entry lacks a `correlation_id` linking entries to a run session. No `summarize_run()` function for run-level aggregation.

**BASE CAUSE:** Observability module was designed for audit trail only; correlation and metrics were deferred.

**CAUSAL CHAIN:** Without correlation IDs, runs cannot be grouped; without metrics summary, operational visibility is limited. Reviewer scores observability at ~2/9 (no correlation IDs in structured logs).

**TARGET PROJECT EVIDENCE:** `scripts/pipeline/commands/ops/run_outcome_log.py` — no `correlation_id` in `log_outcome()`, no `summarize_run()` function.

**REVIEWER MODEL EVIDENCE:** observability P5 requirement: "Consistent logging with correlation IDs, basic metrics"

**REALITY CLASSIFICATION:** real source/logic weakness

**RATING IMPACT:** observability 2→5/9 (+3 points)

**REMEDIATION TYPE:** source fix

**PROOF NEEDED:** `log_outcome()` accepts `correlation_id`, `summarize_run(correlation_id)` exists and returns aggregated metrics, tests pass

---

## RC-RATE-005 — State Management Lacks Checkpoint/Recovery

**SCORE DIMENSION DAMAGED:** Agentic / stateManagement

**CURRENT SCORE:** 3/9

**SURFACE SYMPTOM:** `run_outcome_log.py` is append-only with no checkpoint/restore, no resume-from-failure path.

**BASE CAUSE:** Original design focused on audit; checkpoint semantics were not implemented.

**CAUSAL CHAIN:** Reviewer rates stateManagement at 3/9 (append-only logs → no recovery paths → no replay).

**TARGET PROJECT EVIDENCE:** `scripts/pipeline/commands/ops/run_outcome_log.py` — no checkpoint/resume functions.

**REVIEWER MODEL EVIDENCE:** stateManagement 4-5/9 requires "Checkpointed state with recovery paths"

**REALITY CLASSIFICATION:** real source/logic weakness

**RATING IMPACT:** stateManagement 3→5/9 (+2 points)

**REMEDIATION TYPE:** source fix

**PROOF NEEDED:** `checkpoint_run()` and `resume_from_checkpoint()` exist, tests cover checkpoint/resume cycle, including resume-after-partial-failure

---

## RC-RATE-006 — Key Governance Files Untracked

**SCORE DIMENSION DAMAGED:** Readiness / ownershipClarity, incidentReadiness, compliancePosture

**CURRENT SCORE:** ~3-4/9 average for these subdimensions

**SURFACE SYMPTOM:** CODEOWNERS, CONTRIBUTING.md, SECURITY.md, docs/governance/incident-response.md, docs/governance/reviewer-readiness-checklist.md all exist on disk but are untracked in git.

**BASE CAUSE:** Files were created in this healing session but not yet committed. Reviewer git-based checks won't find them in commit history.

**CAUSAL CHAIN:** Reviewer filesystem scan WILL see the files. Git blame/history-based scoring will miss them. Mixed signals.

**REALITY CLASSIFICATION:** governance/evidence weakness — files exist, git history absent

**RATING IMPACT:** Partial (files visible on disk; history-based evidence absent until committed)

**REMEDIATION TYPE:** governance/taskcard fix — verify files are complete and correct

**PROOF NEEDED:** Files are present, complete, internally consistent, not placeholder content

---

## RC-RATE-007 — New Test Files Untracked; CI Scope Unconfirmed

**SCORE DIMENSION DAMAGED:** Engineering / testDepth

**CURRENT SCORE:** 5/9

**SURFACE SYMPTOM:** test_property_based.py, test_security_basics.py, test_adaptive_retry.py, test_run_outcome_log.py are untracked. CI test command uses `tests/` glob — likely covers them but not confirmed.

**BASE CAUSE:** New test modules added to disk but not yet staged.

**CAUSAL CHAIN:** If CI catches `tests/` glob, all tests run. If not, testDepth may not see property-based/security tests.

**REALITY CLASSIFICATION:** governance/evidence weakness

**RATING IMPACT:** Minor (glob likely covers them; confirming prevents regression)

**REMEDIATION TYPE:** CI/local gate fix — confirm glob covers new test files

**PROOF NEEDED:** `pytest tests/ -q` shows test_property_based.py and test_security_basics.py collected

---

## RC-RATE-008 — No Release Process in CONTRIBUTING.md

**SCORE DIMENSION DAMAGED:** Readiness / releaseDiscipline

**CURRENT SCORE:** 2/9

**SURFACE SYMPTOM:** CONTRIBUTING.md has PR process but no release/versioning section.

**BASE CAUSE:** Release workflow was never documented.

**CAUSAL CHAIN:** Reviewer checks CONTRIBUTING for release process → absent → releaseDiscipline score stays low.

**REALITY CLASSIFICATION:** documentation trust weakness

**RATING IMPACT:** releaseDiscipline (combined with RC-RATE-003): 2→5/9

**REMEDIATION TYPE:** docs/source consistency fix

**PROOF NEEDED:** CONTRIBUTING.md has "Release Process" section with semantic versioning, CHANGELOG update, and foss-gate check
