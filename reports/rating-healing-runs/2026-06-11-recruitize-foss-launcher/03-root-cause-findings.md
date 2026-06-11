# Phase 03 — Root Cause Findings

**Sprint:** 2026-06-11-recruitize-foss-launcher
**Method:** Git log analysis + file system inspection + APRV model mapping

---

## Summary

The primary cause of low S scores was that critical governance files existed on disk but were **untracked in git**. Because the Recruitize reviewer clones the git repository, untracked files are invisible to it. The sigmoid gate in the APRV formula means any axis below ~1.8/9 nearly halves the entire composite score. R was estimated at ~1.5 before sprint, causing a severe sigmoid penalty.

Secondary causes: no ADR directory (R5 evidence missing), no runbooks (R6 evidence missing), no input validation in adaptive_retry.py (A/P quality gap), coverage threshold at 11% (weak enforcement signal).

---

## Root Cause Register

### RC-001 — CRITICAL: Governance Files Untracked

- **Axis impact:** R −2.0 to −2.5
- **Files affected:** CODEOWNERS, CHANGELOG.md, CONTRIBUTING.md, SECURITY.md
- **Root cause:** Files were written to disk but never staged+committed. The reviewer could not detect `hasCodeowners`, `hasChangelog`, `hasContributing`, or `hasSecurityPolicy` signals.
- **Resolution:** Committed in e37b4a3
- **Verification:** `git log --oneline e37b4a3` shows all four files

### RC-002 — HIGH: Source and Test Files Untracked

- **Axis impact:** A −0.5, P −0.5 to −1.0
- **Files affected:** adaptive_retry.py, run_outcome_log.py, test_adaptive_retry.py, test_property_based.py, test_run_outcome_log.py, test_security_basics.py
- **Root cause:** New source and test modules written during development but not committed.
- **Resolution:** Committed in 303a7f2
- **Verification:** `git show 303a7f2 --name-only`

### RC-003 — HIGH: No ADR Directory

- **Axis impact:** R −1.0 to −1.5 (R5 evidence absent)
- **Root cause:** No architectural decision records existed. R5 (Auditable) requires a documented decision log.
- **Resolution:** Created docs/adr/ with 3 ADRs in 73d2fc8
- **Verification:** `ls docs/adr/`

### RC-004 — HIGH: Coverage Threshold Too Low

- **Axis impact:** P −0.5
- **Root cause:** `--cov-fail-under=11` in CI — extremely low bar that doesn't signal engineering intent.
- **Resolution:** Raised to 12% in 73d2fc8. (Plan target was 30%; actual measured coverage was 11.96%, making 30% unachievable without significant new test work. Gap documented in G-006.)
- **Verification:** `grep cov-fail-under .github/workflows/pipeline-tests.yml`

### RC-005 — HIGH: docs/governance/ Files Untracked

- **Axis impact:** R −0.5 to −1.0
- **Files affected:** docs/governance/incident-response.md, docs/governance/reviewer-readiness-checklist.md, and 9 additional governance files
- **Root cause:** Governance documentation written but not committed.
- **Resolution:** Committed in prior commits (e37b4a3 and associated)
- **Verification:** `git log --oneline --follow docs/governance/`

### RC-006 — MEDIUM: No .env.example

- **Axis impact:** P −0.3 to −0.5
- **Root cause:** No documented environment variable reference.
- **Resolution:** .env.example was committed on May 15 (pre-sprint) — already resolved before sprint began.
- **Verification:** `git log --oneline .env.example`

### RC-007 — MEDIUM: No Input Validation in adaptive_retry.py

- **Axis impact:** A, P (source quality)
- **Root cause:** `skill_id` accepted any value including empty string; `max_retries < 0` could cause unexpected behavior.
- **Resolution:** Added ValueError guards in 73d2fc8; 5 new tests added.
- **Verification:** `grep -n "ValueError" scripts/pipeline/commands/ops/adaptive_retry.py`

### RC-008 — MEDIUM: No Concurrency Note in run_outcome_log.py

- **Axis impact:** P (reliability documentation)
- **Root cause:** log_outcome() performs unprotected file appends. Multi-process concurrent writes would corrupt the JSONL log. No documentation existed to tell callers about this constraint.
- **NOTE:** Sprint 73d2fc8 claimed this resolved but did NOT add the note. Fixed in 3511124.
- **Resolution:** Concurrency note added to module docstring in 3511124
- **Verification:** `grep -n "Concurrency" scripts/pipeline/commands/ops/run_outcome_log.py`

### RC-009 — MEDIUM: No Runbook Documentation

- **Axis impact:** R −0.5 to −1.0 (R6 evidence absent)
- **Root cause:** No docs/runbooks/ directory. R6 (Controlled) requires incident response procedures.
- **Resolution:** Created docs/runbooks/ with 2 runbooks in 73d2fc8
- **Verification:** `ls docs/runbooks/`

### RC-010 — LOW: No Release Workflow / No Versioned CHANGELOG

- **Axis impact:** R −0.5 (R3 incomplete)
- **Root cause:** CHANGELOG.md exists but has no versioned `## [x.y.z]` sections. No CI release workflow exists. Only one git tag (v0.1.0).
- **Resolution:** Addressed in hardening sprint — see Lane 3 (CHANGELOG) and Lane 4 (release.yml)

---

## Signal Flag Status (Post-Sprint)

| Flag | Status | Evidence |
|------|--------|----------|
| hasChangelog | PRESENT | CHANGELOG.md committed e37b4a3 |
| hasCodeowners | PRESENT | CODEOWNERS committed e37b4a3 |
| hasContributing | PRESENT | CONTRIBUTING.md committed e37b4a3 |
| hasSecurityPolicy | PRESENT | SECURITY.md committed e37b4a3 |
| hasDocsDir | PRESENT | docs/ exists |
| hasAgentsMd | PRESENT | AGENTS.md exists |
| hasCiConfig | PRESENT | .github/workflows/pipeline-tests.yml |
| hasTestDir | PRESENT | tests/ exists with 818 tests |
| hasReadme | PRESENT | README.md exists |
| hasAdrs | PRESENT | docs/adr/ with 3 ADRs (73d2fc8) |
| hasRunbooks | PRESENT | docs/runbooks/ with 2 runbooks (73d2fc8) |
