# APRV Scoring Reference: How Projects Are Rated

**Purpose:** Operational reference for understanding exactly how this reviewer scores repositories. Use this to know what the system looks for, what moves each axis, and what concrete artifacts produce higher scores.

**Audience:** Project owners who want to understand and improve their scores under the current rating mechanism.

---

## How Scoring Works

Each repository is scored on **four axes** (A/P/R/V) using floats from 0.0 to 9.0. A fifth composite score **S** is derived deterministically from A, P, and R.

The reviewer **clones your repo**, reads your code, configs, tests, CI, docs, and operational artifacts. It runs a 16-step analysis pipeline. Six of those steps directly produce scores:

1. **aCollect** — gather evidence of agentic capabilities (facts only, no score)
2. **aWar** — score the Agentic (A) axis using collected evidence
3. **pCollect** → **pWar** — same for Practices (P)
4. **rCollect** → **rWar** — same for Readiness (R)
5. **vWar** — score Verification (V), the meta-axis measuring analysis confidence
6. **aprvCoherence** — cross-check all four axes for consistency
7. **deepening** — score 12 sub-axes (4 per A/P/R block) for the radar profile

### The Tug-of-War Method

Each axis is scored using a structured "tug-of-war":
1. **Position** — each observed fact is placed on the 0-9 scale
2. **Cluster** — the reviewer finds where the bulk of evidence gathers (center, left bound, right bound)
3. **Tug-of-war** — gaps (missing expected capabilities) pull the score down; bonuses (unexpected strengths) pull it up
4. **Spread rule** — if the evidence spread exceeds 3.0, bonuses are excluded from the tug-of-war (scattered evidence can't inflate scores)
5. **Sanity check** — scores >= 6.0 require corroboration from 2+ independent evidence surface types

### Evidence Hierarchy

The reviewer weights evidence types in this order (strongest to weakest):

1. **Implemented runtime behavior** — actual running code, state machines, control loops
2. **Tests proving behavior** — test files that exercise the claimed capability
3. **CI/CD enforcement** — pipeline configs that enforce the practice
4. **Persisted operational artifacts** — lock files, audit logs, release receipts
5. **Operator/release/contract docs tied to implementation** — ADRs, runbooks linked to real code
6. **General documentation** — README descriptions, architecture docs
7. **Naming/diagrams/aspirational language** — the weakest signal

**Key insight:** Code that *does the thing* always outweighs docs that *describe the thing*. A working state machine in code beats a README that says "we use state machines."

### The S Composite Score

S is computed deterministically from A, P, R (V excluded):

```
S = 100 * harmonicMean(A/9, P/9, R/9; weights=[0.4, 0.3, 0.3]) * gate
```

- **Harmonic mean (p=-1):** Punishes imbalance. One weak axis drags the whole score down.
- **Sigmoid gate (threshold=0.2, k=10):** If any axis drops near zero (below ~1.8 on the 0-9 scale), the entire S score is heavily penalized.
- **Weights:** A=40%, P=30%, R=30%.

**Practical consequence:** Raising your weakest axis has more impact on S than raising your strongest. A balanced A5/P5/R5 scores higher than an unbalanced A8/P2/R5.

### Badge Rendering

Float scores map to badges with sub-level precision:
- `[x.00, x.25)` = plain level: `A5`
- `[x.25, x.50)` = strong for level: `A5(+)`
- `[x.50, x.75)` = weak for next: `A6(-)`
- `[x.75, x+1)` = next level: `A6`

### Tone (Traffic Light)

Every badge gets a tone: **bad** (0-2), **mid** (3-6), **good** (7-9).

---

## A (Agentic) — What It Measures

**Definition:** Agentic architecture maturity: control flow, state management, branching, approval gates, agent coordination, adaptive behavior.

This is the axis with the **widest effective range**. Every code structure change — adding a state machine, an approval gate, a retry loop — shifts the score. It's also the most directly tied to architectural decisions.

### The Scale

| Score | Level | What the reviewer looks for in your repo |
|-------|-------|------------------------------------------|
| 0.0-0.4 | **None** | No runtime control, no stateful decisions, no branching. Library, CLI tool, static site, README-only repo. |
| 0.5-1.4 | **Deterministic** | Scripts, task runners, hardcoded pipeline, no runtime state. Makefile, npm scripts, shell scripts, batch jobs. |
| 1.5-2.4 | **Reactive** | Code responds to input but holds no state between invocations. Single-turn prompt wrappers, stateless API calls, simple RAG without chain. |
| 2.5-3.4 | **Workflow** | AI inside a defined multi-step flow, but flow ownership is outside the AI layer. Pipeline YAML, DAG definitions, step sequences without dynamic branching. |
| 3.5-4.4 | **Stateful** | Persistent control loop with state, branching on results, retry logic. Event loop, state machine, checkpoint/retry logic, state persistence layer. |
| 4.5-5.4 | **Controlled** | Stateful + approval gates, bounded action scope, escalation paths, policy-driven limits. Approval API, hold/publish gates, action enums, scope control. |
| 5.5-6.4 | **Coordinated** | Multiple specialized agents with coordinated runtime. Agent registry, dispatcher/router, shared context store, specialization boundaries. |
| 6.5-7.4 | **Adaptive** | Mid-execution strategy revision based on intermediate results. Dynamic plan revision, strategy selector, conditional re-routing, self-correction. |
| 7.5-8.4 | **Autonomous** | Self-directed execution in explicit bounded scope with goal representation. Goal/plan objects, termination conditions, autonomous iteration loops. |
| 8.5-9.0 | **Self-Improving** | Feedback-driven evolution of strategies between runs. Feedback ingestion pipeline, evaluation framework, strategy/prompt versioning, A/B infrastructure. |

### What concretely moves A up

| From | To | Add these to your repo |
|------|----|------------------------|
| A0-A1 | A2 | A request-response handler that processes input and returns output (even if stateless) |
| A2 | A3 | Multi-step pipeline with defined stages (even if linear). Pipeline YAML, step-runner scripts. |
| A3 | A4 | **State persistence between steps** (DB, file, external store). Branching based on intermediate results. Retry with state recovery. This is the first major jump. |
| A4 | A5 | **Approval/HITL gates** (hold before publish, human review checkpoints). Bounded action scope (the agent can't do everything — explicit limits). Escalation paths. |
| A5 | A6 | **Multiple agents cooperating at runtime.** Agent registry, routing/dispatch, shared context. Not just one agent calling another — runtime coordination. |
| A6 | A7 | **Strategy revision mid-execution.** The system changes its plan based on what happened so far. Self-correction with rollback. |
| A7 | A8 | **Goal representation.** The agent reasons about outcomes, not just steps. Termination conditions. Autonomous iteration within bounded scope. |
| A8 | A9 | **Cross-run learning.** Feedback pipeline that collects outcomes and adjusts strategies for future runs. Evaluation framework, versioned strategies. |

### A Sub-Axes (Deepening Radar)

| Sub-axis | What it measures | Key evidence |
|----------|-----------------|--------------|
| **State Management** | Where and how runtime state is persisted and synchronized | State persistence layer, checkpointing, recovery from partial failure |
| **Flow Orchestration** | How multi-step processes are defined, coordinated, recovered | Pipeline definitions, DAG configs, stage boundaries, retry logic |
| **Boundary Enforcement** | How agent scope, permissions, and resource access are constrained | Approval gates, action enums, policy files, scope control, escalation |
| **Adaptation Capability** | How behavior adjusts without code changes | Strategy selectors, dynamic re-routing, self-correction, feedback loops |

---

## P (Practices) — What It Measures

**Definition:** Observable engineering practice maturity: CI/CD, testing, quality gates, observability, deployment automation, security scanning, resilience patterns.

This axis tends to **cluster in the middle** (3-7 for most real projects). The reviewer looks for *evidence that practices are implemented and enforced*, not just configured.

### The Scale

| Score | Level | What the reviewer looks for in your repo |
|-------|-------|------------------------------------------|
| 0.0-0.4 | **None** | No CI, no tests, no quality tools, no deployment process. Code may exist but practices are absent. |
| 0.5-1.4 | **Sparse** | At least one practice present but thin and inconsistent. One test file, or minimal CI script, or one linter config without enforcement. |
| 1.5-2.4 | **Structured** | Test framework chosen, CI pipeline multi-stage (lint+test+build), code quality tools configured. Jest/Vitest config, `.eslintrc`, `.prettierrc`. |
| 2.5-3.4 | **Gated** | CI enforced via branch protection, coverage thresholds configured, PR quality gates. Required checks, coverage config, PR template with checklist. |
| 3.5-4.4 | **Automated** | Containerized build + automated deploy pipeline (CD). Dockerfile, deploy workflow, smoke test stage, staging environment config. |
| 4.5-5.4 | **Observable** | Structured logging + metrics + basic tracing + configuration/secrets hygiene. Structured logger, OpenTelemetry config, `.env.example`, vault/secrets manager config. |
| 5.5-6.4 | **Verified** | Comprehensive test suite (unit + integration + e2e) + performance/load tests + security scanning in CI. e2e tests, k6/artillery config, SAST/DAST scanner, coverage >= 80%. |
| 6.5-7.4 | **Resilient** | Release automation with rollback + recovery testing + environment parity + canary/staged rollout. Rollback scripts, blue-green config, staging/prod parity, recovery tests. |
| 7.5-8.4 | **Proactive** | Contract tests + mutation testing + automated dependency updates + feature flags. Pact/contract tests, Stryker config, Dependabot/Renovate, feature flag config. |
| 8.5-9.0 | **Self-Sustaining** | SLO/SLI monitoring + auto-remediation + incident response as code + postmortem automation. SLO config, auto-rollback triggers, incident playbooks, on-call config. |

### What concretely moves P up

| From | To | Add these to your repo |
|------|----|------------------------|
| P0 | P1 | A single test file. Any linter config. Any CI file (even a basic one). |
| P1 | P2 | **Multi-stage CI** (lint + test + build as separate steps). Test framework config (`jest.config`, `vitest.config`). ESLint/Prettier configured. |
| P2 | P3 | **Branch protection.** CI checks required for merge. Coverage threshold configured. PR template. |
| P3 | P4 | **Dockerfile + CD pipeline.** Automated deployment to at least one environment. Smoke test in CI. |
| P4 | P5 | **Structured logging** (JSON logs, not console.log). Metrics/tracing config (OpenTelemetry). `.env.example` documenting required config. Secrets handled via env vars or vault, not hardcoded. |
| P5 | P6 | **e2e tests alongside unit tests.** Security scanning in CI (SAST). Performance/load test config. Coverage at or above 80%. |
| P6 | P7 | **Rollback automation.** Blue-green or canary deployment config. Recovery testing. Staging environment that mirrors production. |
| P7 | P8 | **Contract tests** (Pact or similar). Mutation testing (Stryker). Dependabot/Renovate configured and active. Feature flags. |
| P8 | P9 | **SLO/SLI definitions** in config. Auto-remediation triggers. Incident response playbooks as code. Postmortem templates with filled examples. |

### P Sub-Axes (Deepening Radar)

| Sub-axis | What it measures | Key evidence |
|----------|-----------------|--------------|
| **CI/CD Practice** | Breadth and reliability of CI/CD pipelines | CI config complexity, multi-stage, deploy automation, rollback capability |
| **Test Depth** | Unit, integration, e2e coverage approach | Test files, framework config, coverage reports, test types present |
| **Observability** | Logging, metrics, tracing depth | Structured logger setup, OpenTelemetry, metrics config, tracing |
| **Quality Gating** | Enforcement at PR, build, and release boundaries | Branch protection, required checks, lint in CI, security scanning |

---

## R (Readiness) — What It Measures

**Definition:** Operational governance maturity: deployment documentation, ownership tracking, release process, SLAs, incident response, compliance artifacts, change management.

This axis has a **low practical ceiling for most repos** (~R5-R6). Scores above R6 require organizational-level artifacts (compliance frameworks, audit trails, incident automation) that many repos legitimately don't need. The reviewer cannot verify things that exist outside the repo (PagerDuty configs, external audit reports) — it can only see what's in the repo.

### The Scale

| Score | Level | What the reviewer looks for in your repo |
|-------|-------|------------------------------------------|
| 0.0-0.4 | **None** | No deployment story, no ownership, no operational artifacts. Personal script with no operational context. |
| 0.5-1.4 | **Deployed** | Basic deployment documentation, runtime known. Deploy instructions, Dockerfile, runtime requirements documented. |
| 1.5-2.4 | **Owned** | Explicit ownership mapped, deployment process documented, basic runbook exists. CODEOWNERS, deploy docs, basic runbook. |
| 2.5-3.4 | **Released** | Versioned releases, changelog, release process documented. `CHANGELOG.md`, version tags, release workflow, release notes. |
| 3.5-4.4 | **Governed** | Governance surfaces: operator/admin dashboard, approval gates, documented SLAs. Admin API/UI, hold-publish gates, SLA definitions, service catalog entry. |
| 4.5-5.4 | **Auditable** | Key decisions recorded (ADRs), audit artifacts, release receipts persisted. ADR directory, decision logs, release attestations, approval trails. |
| 5.5-6.4 | **Controlled** | Change management documented, incident response defined, runbooks for failure modes. Incident response docs, severity tiers, runbooks, on-call config. |
| 6.5-7.4 | **Compliant** | Compliance artifacts: data handling, access control, audit trail, security policies. Data classification docs, access control matrix, audit log config. |
| 7.5-8.4 | **Verified** | Compliance verifiable through automated checks. Policy-as-code, compliance automation in CI, automated audit artifacts. |
| 8.5-9.0 | **Assured** | Every change traceable, every failure triggers auditable incident, compliance continuously verified. End-to-end traceability, incident automation, continuous compliance. |

### What concretely moves R up

| From | To | Add these to your repo |
|------|----|------------------------|
| R0 | R1 | **Deployment documentation.** How to deploy, what runtime is needed, any Dockerfile or docker-compose. |
| R1 | R2 | **`CODEOWNERS` file.** Document who owns what. Basic deploy process documented in a runbook or README section. |
| R2 | R3 | **`CHANGELOG.md` maintained per release.** Semantic version tags. Release workflow in CI. Release notes. |
| R3 | R4 | **Approval gates in the workflow.** SLA definitions (even informal). Admin/operator surface for managing the system. Service catalog entry or equivalent. |
| R4 | R5 | **ADR directory** (`docs/adr/` or similar). Decision logs with dates and rationale. Release receipts. Approval trails. |
| R5 | R6 | **Incident response documentation.** Severity tier definitions. Runbooks for known failure modes. On-call configuration or rotation docs. |
| R6 | R7 | **Compliance artifacts.** Data handling documentation. Access control matrix. Audit log configuration. Security policy documents. |
| R7 | R8 | **Policy-as-code.** Compliance checks automated in CI. Audit artifacts generated automatically. |
| R8 | R9 | **Full traceability.** Every change produces an audit record. Incident automation. Continuous compliance monitoring. |

### R Sub-Axes (Deepening Radar)

| Sub-axis | What it measures | Key evidence |
|----------|-----------------|--------------|
| **Ownership Clarity** | How responsibilities are tracked and documented | CODEOWNERS, maintainer lists, escalation paths, component-level ownership |
| **Release Discipline** | Versioning, changelog, release process rigor | CHANGELOG, semver tags, release workflow, release verification |
| **Incident Readiness** | Runbooks, on-call, recovery automation | Runbooks, severity tiers, on-call config, alerting rules, postmortem templates |
| **Compliance Posture** | Regulatory, security, and audit artifacts | Data handling docs, access control, audit trail config, policy-as-code |

---

## V (Verification) — What It Measures

**Definition:** Evidence quality of the analysis run. How thoroughly the reviewer could verify its own A/P/R conclusions.

V is a **meta-axis** — it measures the analysis confidence, not a property of your repository. You don't directly "improve V" by adding repo artifacts. V goes up when your repo makes it *easy for the reviewer to verify its claims*: clear structure, accessible code, running tests, CI output.

V is **excluded from the S composite score.** It does not affect your ranking. But low V signals that the A/P/R scores themselves may be unreliable.

| Score | Level | What it means for this analysis run |
|-------|-------|-------------------------------------|
| 0.0-0.4 | **Claim-Only** | Conclusions from description only. No file inspection. |
| 0.5-1.4 | **Sparse** | One or two surface-level checks. |
| 1.5-2.4 | **Sampled** | Key claims spot-checked, no systematic coverage. |
| 2.5-3.4 | **Partial** | Most claims checked from 2+ surface types. Gaps documented. |
| 3.5-4.4 | **Sufficient** | Enough evidence for reasonable A/P/R confidence. 3+ surface types. |
| 4.5-5.4 | **Broad** | All relevant surface types examined (code, CI, config, docs, runtime). |
| 5.5-6.4 | **Strong** | Claims corroborated by independent evidence sources. |
| 6.5-7.4 | **Deep** | Systematic full-surface inspection. Cross-axis consistency verified. |
| 7.5-8.4 | **Traceable** | Every score claim maps to a specific artifact or command output. |
| 8.5-9.0 | **Audit-Grade** | Every claim verifiable. Schema clean. Fully reproducible. |

### What makes V higher (indirectly)

- **Clear directory structure** — `src/`, `test/`, `config/`, `docs/` make it easy for the reviewer to find evidence
- **Tests that actually run** — passing tests provide runtime verification for code claims
- **CI that produces artifacts** — coverage reports, security scan results, build logs
- **Documentation linked to code** — ADRs that reference specific files, runbooks that describe actual commands

---

## What Gets Scanned Before Scoring

Before any axis is scored, the pipeline runs these pre-scoring steps that **directly feed into every axis score**:

### Orient
The reviewer classifies your repo archetype (application, library, monorepo, etc.) and identifies entry points, core deliverable, and which axes deserve deepest scrutiny. **A well-structured repo with clear entry points gets better orient output, which improves all downstream steps.**

### Footprint
Counts files, LOC, languages, test files. Detects **repo signals** — boolean flags that feed directly into scoring:

| Signal | What triggers it | Axes affected |
|--------|-----------------|---------------|
| `hasReadme` | README at root or first nesting level | R (documentation existence) |
| `hasChangelog` | CHANGELOG file present | R (release discipline) |
| `hasDocsDir` | `docs/` directory exists | R, V (documentation depth) |
| `hasContributing` | CONTRIBUTING guide present | R (ownership/process) |
| `hasAgentsMd` | AI agent policy file present | A (agent boundary documentation) |
| `hasPromptDir` | Prompt directory exists | A (prompt-driven architecture evidence) |
| `hasCiConfig` | Any CI/CD config file | P (CI existence) |
| `hasDockerFiles` | Dockerfile or docker-compose | P (containerization), R (deployment) |
| `hasCodeowners` | CODEOWNERS/OWNERS file | R (ownership) |
| `hasTestDir` | Test directory exists | P (testing), V (verifiability) |
| `hasEntryPoints` | package.json main, CLI, Docker CMD | All (structural clarity) |
| `hasSourceDir` | `src/` or equivalent | All (structural clarity) |

### Security Scan
Heuristic triage for secret/credential exposure. Flags:
- `hasTrackedSecrets` — API keys/tokens/passwords in tracked files (**critical**)
- `hasHardcodedCredentials` — inline credentials in source code (**critical**)
- `hasTrackedEnvFiles` — real `.env` files committed (not `.env.example`) (**warning**)
- `hasInsecureDefaults` — disabled auth, wildcard trust in config (**warning**)
- `hasRiskyDockerOrCiConfig` — secrets in Docker/CI files (**warning**)
- `hasSensitiveLogsOrFixtures` — PII or secrets in committed logs (**low**)

Security findings **don't directly lower A/P/R scores** but they trigger negative signals in the composition stage and can trigger HITL review flags.

---

## S Composite: The Math

Given scores A, P, R on the 0-9 scale:

```
a = A / 9      (normalized to 0-1)
p = P / 9
r = R / 9

harmonicMean = (0.4*a^-1 + 0.3*p^-1 + 0.3*r^-1) ^ -1

gate = sigmoid(10*(a - 0.2)) * sigmoid(10*(p - 0.2)) * sigmoid(10*(r - 0.2))

S = 100 * harmonicMean * gate
```

### Worked Examples

| A | P | R | S | Why |
|---|---|---|---|-----|
| 5.0 | 5.0 | 5.0 | 55.6 | Balanced mid-range |
| 7.0 | 7.0 | 7.0 | 77.8 | Balanced strong |
| 9.0 | 9.0 | 9.0 | 100.0 | Maximum |
| 8.0 | 2.0 | 5.0 | 29.3 | P=2 drags S down hard (harmonic mean) |
| 5.0 | 5.0 | 1.0 | 16.4 | R=1 triggers gate penalty |
| 5.0 | 5.0 | 0.5 | 3.2 | R near zero almost zeroes S |
| 6.0 | 4.0 | 4.0 | 42.5 | Moderate imbalance |
| 4.0 | 6.0 | 6.0 | 47.9 | A=4 still penalized (40% weight) |

### Key Takeaways

1. **Your weakest axis dominates S.** Raising P from 2 to 4 does more for S than raising A from 7 to 9.
2. **Anything below ~1.8 on any axis triggers the sigmoid gate** and sharply reduces S.
3. **A has 40% weight** — at equal levels, A matters more than P or R individually.
4. **V does not affect S.** It's informational only.

---

## Multi-Repo Aggregation

When a post references multiple repositories, the reviewer **averages** per-repo axis scores with equal weight. This means:

- A weak utility repo dilutes the score of a strong primary repo
- Small helper repos count equally to large core repos
- **If you announce multiple repos, every repo contributes equally to your score**

Practical advice: If your announcement links to repos of varying importance, ensure even your utility/helper repos have basic hygiene (tests, CI, README) — or consider whether they need to be linked at all.

---

## What Gets You Classified as an Announcement

Before any scoring happens, the query engine decides if your post is a "matched announcement." Posts that aren't matched are never scored.

**Match criteria (all must be true):**
1. The post announces a concrete deliverable (not just a concept or trend)
2. The deliverable is materially central to the post
3. Concrete signals present: release/launch wording, scope of what the system does, what's new, architecture indicators, or repo/product links

**Strong positive signals:** New product/tool/integration, newly available functionality, implementation links, what users can now do.

**Strong negative signals (will cause rejection):** Generic AI commentary, tutorials, documentation mirrors, aspirational language without evidence of delivery, minor maintenance notes.

**Classification labels that trigger full scoring:**
- `ai-agent-announcement` — clear evidence of iterative multi-step loop with state
- `ai-agent-portfolio-announcement` — portfolio of multiple AI agents with repo links
- `ai-product-announcement` — AI-powered system (no agentic loop)
- `product-announcement` — non-AI product/system

---

## Common Score Patterns and What They Mean

| Pattern | What it signals | Typical cause |
|---------|----------------|---------------|
| A7/P2/R1 | Strong architecture, no engineering practices | Prototype with sophisticated agent logic but no CI, tests, or operational docs |
| A3/P6/R5 | Mature engineering, weak agentic architecture | Well-run project that doesn't have agentic features (workflow-only) |
| A5/P5/R2 | Balanced mid-range but weak governance | Good project that hasn't invested in operational readiness |
| A*/P*/R0 | Any A/P with R=0 | Missing deployment docs, no CODEOWNERS, no changelog — gate penalty zeros S |
| High A, low V | Strong agent claims, weak evidence | The reviewer couldn't verify agent capabilities — likely unclear code structure or inaccessible artifacts |

---

## Highest-Impact Actions by Current Score Range

### If your S is 0-20 (one or more axes near zero)
**Priority: Eliminate zeros.** The sigmoid gate means any axis below ~1.8 crushes S.
- Add a README with deployment instructions (R: 0 -> 1)
- Add one test file with a test framework config (P: 0 -> 1)
- Ensure the repo has runnable code, not just docs (A: 0 -> 1)

### If your S is 20-40 (weak axis pulling down)
**Priority: Raise your weakest axis.** Harmonic mean means the weakest axis dominates.
- If P is weak: add multi-stage CI (lint + test + build) and a Dockerfile
- If R is weak: add CODEOWNERS, CHANGELOG, and basic deploy docs
- If A is weak: add state persistence and branching logic (even simple retry/state-machine)

### If your S is 40-60 (balanced mid-range)
**Priority: Push all axes past 5.** This is where incremental improvements compound.
- A: Add approval gates or HITL checkpoints (A4 -> A5)
- P: Add structured logging and observability config (P4 -> P5)
- R: Add ADR directory and release receipts (R4 -> R5)

### If your S is 60-80 (strong baseline)
**Priority: Differentiate through depth.** Each additional point requires more specialized evidence.
- A: Multi-agent coordination or mid-execution strategy revision (A5 -> A6-7)
- P: e2e tests + security scanning + rollback automation (P5 -> P6-7)
- R: Incident response docs + compliance artifacts (R5 -> R6-7)

### If your S is 80+ (advanced)
**Priority: Sustain and prove.** Scores above 80 require evidence from 2+ independent source types for every claim.
- Contract tests, mutation testing, SLO definitions
- Compliance-as-code, continuous audit artifacts
- Feedback pipelines, strategy versioning, A/B infrastructure
- Every claim must have a verifiable artifact — assertions without evidence are penalized at this level

---

## Rerun Variance: What to Expect

The scoring system has inherent variance of approximately **+/-0.5 to 1.5 points per axis** across reruns on the same repository. This is because:

1. **LLM stochasticity** — the model that scores your repo produces slightly different outputs each time
2. **Evidence collection variance** — the collect steps may emphasize different evidence on different runs
3. **Coherence step adjustment** — the cross-axis coherence check can adjust scores differently

**What this means practically:**
- A score of 5.0 might come back as 4.2 or 5.8 on rerun
- Badge boundaries at 0.25 intervals mean small variance can flip a badge (A5 vs A5(+) vs A6(-))
- The S composite amplifies axis variance through the harmonic mean

**What you can do about it:**
- Focus on evidence that is unambiguous and discoverable (tests, CI configs, concrete artifacts)
- Avoid relying on documentation-only claims for high scores
- Structural clarity (clean directory layout, clear entry points) reduces evidence collection variance

---

## Quick Checklist: Maximum Score Impact Per Artifact

| Artifact | Primary Axis | Score Impact | Notes |
|----------|-------------|-------------|-------|
| `CODEOWNERS` | R | +0.5-1.0 | Ownership signal (R2 requirement) |
| `CHANGELOG.md` | R | +0.5-1.0 | Release discipline (R3 requirement) |
| `docs/adr/` directory with entries | R | +1.0-1.5 | Auditability (R5 requirement) |
| `.gitlab-ci.yml` / `.github/workflows/` | P | +1.0-2.0 | CI existence + multi-stage |
| Dockerfile + docker-compose | P, R | +0.5-1.0 each | Containerization (P4) + deployment (R1) |
| Test directory with framework config | P, V | +1.0-2.0 P, +0.5 V | Testing existence + verifiability |
| `.env.example` (not `.env`) | P | +0.3-0.5 | Secrets hygiene (P5 component) |
| Structured logger (JSON logs) | P | +0.5-1.0 | Observability (P5 component) |
| State machine / checkpoint code | A | +1.0-2.0 | Stateful execution (A4 requirement) |
| Approval gate / HITL code | A | +0.5-1.0 | Controlled execution (A5 requirement) |
| Runbooks / incident docs | R | +0.5-1.0 | Incident readiness (R6 component) |
| Security scanning in CI | P | +0.5-1.0 | Security practice (P6 component) |
| OpenTelemetry / metrics config | P | +0.5-1.0 | Observability (P5 component) |

---

## What the Reviewer Cannot See

The reviewer only analyzes what's in your **git-tracked repository at the commit it clones**. It cannot:

- Access private registries, external dashboards, or monitoring systems
- See PagerDuty/Opsgenie configurations unless they're in the repo
- Verify claims about uptime, user count, or business impact
- Read wikis or documentation hosted outside the repo
- Access environment variables, secrets managers, or runtime configuration
- Evaluate the quality of code it can't read (binary artifacts, minified code)

**If it's not in the repo, it doesn't count.** Compliance docs hosted in Confluence, SLO dashboards in Grafana, incident runbooks in Notion — none of these will be scored unless they're represented in the repository.
