# Phase 02 — Baseline Rating

**Status:** REVIEWER_RUN_NOT_EXECUTED
**Reason:** The Recruitize reviewer is a Node.js pipeline requiring external blog/announcement context and live repo access.
**Confidence:** MEDIUM — scores inferred from APRV model applied to observed git-tracked state.

---

## Critical Finding: Governance Files Are Untracked

The Recruitize reviewer **clones the git repo**. Untracked files are invisible.

```
?? CHANGELOG.md        ← R axis: release discipline signal MISSING
?? CODEOWNERS          ← R axis: ownership signal MISSING
?? CONTRIBUTING.md     ← R axis: process signal MISSING
?? SECURITY.md         ← R axis: security policy signal MISSING
?? docs/governance/incident-response.md
?? docs/governance/reviewer-readiness-checklist.md
?? scripts/pipeline/commands/ops/adaptive_retry.py   ← A axis: state mgmt MISSING
?? scripts/pipeline/commands/ops/run_outcome_log.py  ← A axis: checkpoint/resume MISSING
?? tests/test_adaptive_retry.py   ← P axis: test evidence MISSING
?? tests/test_property_based.py
?? tests/test_run_outcome_log.py
?? tests/test_security_basics.py
```

---

## Estimated Axis Scores (Git-Tracked State)

### A (Agentic) — ~4.0

Evidence in git: multi-step skill chain, path_guard boundary enforcement, local_gate quality gate, retry logic in fetch_aspose_com_targets.py.
Missing from git: adaptive_retry.py (explicit retry wrapper), run_outcome_log.py (outcome persistence + checkpoint).
Anchors at A4.0 (Stateful: pipeline with retry, not yet Controlled with explicit approval gates in git).

### P (Practices) — ~3.0

Evidence in git: 4 GitHub Actions workflows, GitLab CI, pytest.ini, bandit + pip-audit in CI.
Missing from git: 4 new test files, .env.example, structured logging.
Coverage threshold: 11% (extremely low).
Anchors at P3.0 (Gated: CI present, but enforcement threshold too weak to signal P4+).

### R (Readiness) — ~1.5

Evidence in git: AGENTS.md, README.md, docs/ directory, pyproject.toml.
Missing from git: CODEOWNERS, CHANGELOG.md, CONTRIBUTING.md, SECURITY.md, incident docs, ADRs, runbooks.
Anchors at R1.5 (between Deployed and Owned: basic runtime docs but ownership invisible to reviewer).

---

## Estimated S Composite

```
A=4.0, P=3.0, R=1.5
a=0.444, p=0.333, r=0.167
harmonic = (0.4/0.444 + 0.3/0.333 + 0.3/0.167)^-1 = (0.901 + 0.901 + 1.796)^-1 = 0.278
gate = sigmoid(2.44) * sigmoid(1.33) * sigmoid(-0.33) ≈ 0.920 * 0.791 * 0.418 ≈ 0.304
S = 100 * 0.278 * 0.304 ≈ 8.5
```

**Estimated S: 8–15** (R near zero triggers gate penalty)
