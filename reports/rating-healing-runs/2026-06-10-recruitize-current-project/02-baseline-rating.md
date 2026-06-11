# Phase 2 — Baseline Rating

**Status:** REVIEWER_RUN_NOT_EXECUTED (reviewer read-only, cannot safely invoke against target)
**Confidence:** MEDIUM — inferred from rating model + target project evidence
**Date:** 2026-06-10

## Baseline Scores (Inferred)

| Dimension | Raw Score (/9) | Normalized | Notes |
|-----------|---------------|------------|-------|
| Agentic | ~5/9 | ~0.56 | Above gating threshold |
| Engineering | ~4/9 | ~0.44 | Above gating threshold, near borderline |
| Readiness | ~3/9 | ~0.33 | Above gating threshold but weak |

**Estimated final score: ~42-48 (S4 Usable Readiness)**

## Per-Subdimension Baseline

### Agentic
| Subdimension | Score | Evidence |
|---|---|---|
| stateManagement | 3/9 | run_outcome_log.py: append-only JSONL, no checkpoint/resume |
| flowOrchestration | 6/9 | Multi-step skill pipeline, session limits, role-based routing |
| boundaryEnforcement | 7/9 | path_guard.py, pre_write.py, path guard tests, FORBIDDEN_PREFIXES enforced |
| adaptationCapability | 5/9 | adaptive_retry.py: static fallback map (S-21→S-26 etc), exponential backoff |

**Agentic avg: ~5.25/9**

### Engineering
| Subdimension | Score | Evidence |
|---|---|---|
| ciCdPractice | 5/9 | GitHub Actions + GitLab CI, multi-stage, security scan |
| testDepth | 5/9 | 810 tests, property-based (hypothesis), security tests — but pyproject.toml says fail_under=11 |
| observability | 2/9 | ops.log (append-only), run_outcome_log.py (no correlation IDs, no metrics aggregation) |
| qualityGating | 4/9 | Security scan is blocking (fixed in pipeline-tests.yml), but coverage threshold 11% in pyproject.toml |

**Engineering avg: ~4/9**

### Readiness
| Subdimension | Score | Evidence |
|---|---|---|
| ownershipClarity | 4/9 | CODEOWNERS exists (on disk, untracked), but no git history evidence |
| releaseDiscipline | 2/9 | No CHANGELOG.md, no release process docs, pyproject.toml version=0.1.0 but no changelog |
| incidentReadiness | 4/9 | incident-response.md exists (on disk, untracked), severity tiers defined |
| compliancePosture | 3/9 | SECURITY.md exists (on disk, untracked), bandit/pip-audit but limited controls |

**Readiness avg: ~3.25/9**

## Formula Estimate

```
a = 5.25/9 = 0.583
e = 4.00/9 = 0.444
r = 3.25/9 = 0.361

# Harmonic mean weighted approximation:
agg ≈ 1 / (0.4/0.583 + 0.3/0.444 + 0.3/0.361)
    ≈ 1 / (0.686 + 0.676 + 0.831)
    ≈ 1 / 2.193
    ≈ 0.456

# Gate: all dims > 0.2, so gate ≈ 1.0 (no suppression)
score ≈ 100 * 0.456 * 1.0 ≈ 45.6
```

**Estimated baseline: ~45-46 (S4 Usable Readiness)**

## Top Low-Score Causes (ordered by impact)

1. **observability**: 2/9 — no correlation IDs, no metrics summary → RC-RATE-004
2. **releaseDiscipline**: 2/9 — no CHANGELOG.md, no release process → RC-RATE-003, RC-RATE-008
3. **stateManagement**: 3/9 — no checkpoint/resume → RC-RATE-005
4. **qualityGating**: 4/9 — pyproject.toml fail_under=11 inconsistency → RC-RATE-001
5. **compliancePosture**: 3/9 — governance files untracked → RC-RATE-006
