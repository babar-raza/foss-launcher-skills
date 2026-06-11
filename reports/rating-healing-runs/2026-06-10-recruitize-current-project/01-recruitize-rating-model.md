# Phase 1 — Recruitize Rating Model Extraction

**Source:** C:\Users\prora\OneDrive\Documents\GitHub\recruitize-ai-review-agent (read-only)
**Files inspected:** src/core/, src/pipeline/, src/lib/, docs/

## Three Core Dimensions

### A — Agentic (weight: 0.4 / 40%)
Evaluates how much work is turned into repeatable system behavior.

| Subdimension | 0-3 (Red) | 4-6 (Yellow) | 7-9 (Green) |
|---|---|---|---|
| stateManagement | No state persistence | Checkpointed state with recovery | Full stateful with replay |
| flowOrchestration | Linear execution | Multi-step with retry/error handling | Adaptive graph with reconfiguration |
| boundaryEnforcement | No boundary awareness | Policy-driven scope control | Formal authority envelope |
| adaptationCapability | Fixed strategy | Automated re-plan on known failures | Self-directed experimentation |

### E — Engineering/Practices (weight: 0.3 / 30%)
Evaluates engineering hygiene and delivery discipline.

| Subdimension | 0-3 (Red) | 4-6 (Yellow) | 7-9 (Green) |
|---|---|---|---|
| ciCdPractice | Manual builds/tests | Multi-stage CI with quality gates | Self-service deploy with canary/rollback |
| testDepth | No tests / smoke only | Unit + integration in CI | Full pyramid incl. contract + mutation |
| observability | No structured logging | Consistent logging + correlation IDs | Full SLO monitoring + anomaly detection |
| qualityGating | No gates | Lint + test gates with coverage threshold | Policy-as-code blocking releases |

### R — Readiness/Enterprise (weight: 0.3 / 30%)
Evaluates broader reuse and organizational readiness.

| Subdimension | 0-3 (Red) | 4-6 (Yellow) | 7-9 (Green) |
|---|---|---|---|
| ownershipClarity | No CODEOWNERS | Clear ownership + review paths | Verified coverage + SLA enforcement |
| releaseDiscipline | No versioning | Versioned releases + changelog + process docs | Automated pipeline with audit trail |
| incidentReadiness | No incident process | Runbooks for common failures + escalation | Automated detection + triage |
| compliancePosture | No compliance consideration | Core requirements documented + partial controls | Policy-as-code with automated checks |

## Scoring Formula

```
# Normalize each dimension to 0-1
a = agentic / 9
e = engineering / 9
r = readiness / 9

# Weighted generalized mean (p=-1, harmonic-like, balance-seeking)
agg = (0.4*a^(-1) + 0.3*e^(-1) + 0.3*r^(-1))^(-1) / (0.4+0.3+0.3)

# Gating factor — suppresses score if any dimension < 0.2 threshold
gate = sigmoid(10*(a - 0.2)) * sigmoid(10*(e - 0.2)) * sigmoid(10*(r - 0.2))

# Final score
score = 100 * agg * gate  # clamped 0-100
```

## Critical Insight: Imbalance Penalty

The harmonic mean variant penalizes imbalance. A project with A=9, E=9, R=2 will score
significantly lower than a project with A=6, E=6, R=6 even though the latter has lower peak scores.

## Gating Rule

If ANY dimension drops below 0.2 (score < 1.8/9), the sigmoid gate collapses the final score
near zero. This is the most dangerous failure mode.

## Score Buckets

| Score | Label |
|-------|-------|
| 0-10 | S0 Minimal |
| 10-20 | S1 Early Signals |
| 20-30 | S2 Emerging Structure |
| 30-40 | S3 Functional Baseline |
| 40-50 | S4 Usable Readiness |
| 50-60 | S5 Operational Baseline |
| 60-70 | S6 Strong Readiness |
| 70-80 | S7 Advanced Readiness |
| 80-90 | S8 Strategic Readiness |
| 90-100 | S9 Exceptional Readiness |

## High-Score Signals
- Checkpointed state with recovery paths
- Full observability with correlation IDs
- Versioned releases with CHANGELOG
- Blocking quality gates (not continue-on-error)
- Property-based + security tests in CI
- Incident runbooks with severity levels
- CODEOWNERS with complete coverage

## Low-Score Signals
- Append-only logs without replay/checkpoint
- Non-blocking security scans (allow_failure)
- Missing CHANGELOG
- No release process documented
- Coverage threshold inconsistency (package vs CI)
- Governance files untracked (no git history)
- No correlation IDs in structured logs
