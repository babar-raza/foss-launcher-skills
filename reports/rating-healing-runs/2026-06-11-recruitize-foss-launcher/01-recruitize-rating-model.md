# Phase 01 — Recruitize Rating Model

**Source:** Reverse-engineered from `C:\Users\prora\OneDrive\Documents\GitHub\recruitize-ai-review-agent` (read-only)
**Date inspected:** 2026-06-11

---

## Scoring System: APRV

The Recruitize AI review agent scores repositories on four axes:

| Axis | Weight | Description |
|------|--------|-------------|
| A (Agentic) | 40% | How agentic/autonomous the code is — stateful execution, approval gates, retry logic, bounded action scope |
| P (Practices) | 30% | Engineering practices — tests, CI enforcement, coverage thresholds, security scanning, observability |
| R (Readiness) | 30% | Operational readiness — governance docs, release discipline, ADRs, runbooks, CODEOWNERS |
| V (Verification) | excluded | Manual verification score; excluded from composite S calculation |

---

## Composite Score Formula

```
S = 100 × harmonicMean(A/9, P/9, R/9) × sigmoidGate(A/9, P/9, R/9)
```

Where:
- `harmonicMean(a, p, r)` = weighted harmonic mean with weights 0.4/0.3/0.3
- `sigmoidGate(a, p, r)` = product of three sigmoid functions, one per axis

### Harmonic Mean (weighted)

```
harmonic = (0.4/a + 0.3/p + 0.3/r)^-1
```

where `a = A/9`, `p = P/9`, `r = R/9` (normalized 0-1 scale).

The harmonic mean punishes weak axes heavily — one very low value dominates the result.

### Sigmoid Gate

```
gate = sigmoid(10*(a-0.2)) × sigmoid(10*(p-0.2)) × sigmoid(10*(r-0.2))
sigmoid(x) = 1 / (1 + exp(-x))
```

Each axis passes through a sigmoid centered at 0.2 (normalized), which corresponds to raw score ~1.8/9.

- At raw score 1.8: sigmoid ≈ 0.5 (50% gate)
- At raw score 1.5: sigmoid ≈ 0.42 (42% gate — fires noticeably)
- At raw score 1.0: sigmoid ≈ 0.27 (73% penalty)
- At raw score 3.5: sigmoid ≈ 0.87 (only 13% penalty)
- At raw score 5.0: sigmoid ≈ 0.97 (near-full gate)

**Key insight:** A single axis below 1.8/9 nearly halves the entire composite score.

---

## Axis Scale Anchors

### A (Agentic) — Raw 0-9

| Level | Score | Description |
|-------|-------|-------------|
| A1 | 1.0 | Simple script execution |
| A2 | 2.0 | Multi-step automation |
| A3 | 3.0 | Conditional branching + config-driven |
| A4 | 4.0 | Stateful execution (persistent state + retry) |
| A5 | 5.0 | Controlled: approval gates + bounded action scope |
| A6 | 6.0 | Multi-agent orchestration |
| A7+ | 7+ | Autonomous decision-making with human oversight |

### P (Practices) — Raw 0-9

| Level | Score | Description |
|-------|-------|-------------|
| P1 | 1.0 | Ad-hoc, no tests |
| P2 | 2.0 | Some tests, manual CI |
| P3 | 3.0 | Gated: CI enforced + coverage thresholds |
| P4 | 4.0 | Automated: multi-stage pipeline + security scan |
| P5 | 5.0 | Observable: structured logging + metrics |
| P6 | 6.0 | 80%+ coverage + property-based tests |

### R (Readiness) — Raw 0-9

| Level | Score | Description |
|-------|-------|-------------|
| R1 | 1.0 | No governance artifacts |
| R2 | 2.0 | Owned: CODEOWNERS + basic deploy docs |
| R3 | 3.0 | Released: CHANGELOG + semver + release workflow |
| R4 | 4.0 | Governed: SLA definitions + change management |
| R5 | 5.0 | Auditable: ADRs + decision logs with dates |
| R6 | 6.0 | Controlled: incident runbooks + recovery procedures |

---

## Evidence Hierarchy

Reviewers weigh evidence from strongest to weakest:

1. **Runtime code** — actual implementation behavior
2. **Tests proving behavior** — tests that assert the behavior
3. **CI enforcement** — automated gates that block on failure
4. **Operational artifacts** — runbooks, ADRs, incident docs
5. **Documentation tied to implementation** — docstrings, inline comments
6. **General docs** — README, CONTRIBUTING
7. **Naming/aspiration** — file names, aspirational language

---

## Key Signal Flags

These boolean flags are detected by the reviewer from the git-tracked repo state:

- `hasChangelog` — CHANGELOG.md exists and has content
- `hasCodeowners` — CODEOWNERS file exists
- `hasContributing` — CONTRIBUTING.md exists
- `hasSecurityPolicy` — SECURITY.md exists
- `hasDocsDir` — docs/ directory exists
- `hasAgentsMd` — AGENTS.md exists
- `hasCiConfig` — .github/workflows/ has .yml files
- `hasTestDir` — tests/ directory exists
- `hasReadme` — README.md exists
- `hasAdrs` — docs/adr/ directory exists with ≥1 ADR
- `hasRunbooks` — docs/runbooks/ directory exists with ≥1 runbook

**Critical:** The reviewer clones the git repository. Untracked files are invisible.
