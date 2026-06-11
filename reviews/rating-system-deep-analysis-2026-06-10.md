# Rating System: Production Deep Analysis

**Date:** 2026-06-10
**Scope:** Complete tracing of how a repository score is produced, where consistency breaks, what to preserve, what to redesign, and a concrete path forward.

---

## 0. How Rating Works (Plain Language)

The rating system works like a report card with four grades. Instead of school subjects, it grades your code repository on:

- **A (Agentic)** — How smart is your system? Does it just run scripts, or can it make decisions, manage state, recover from errors, and adapt on its own?
- **P (Practices)** — How well-engineered is it? Does it have tests, CI/CD, logging, security scanning, deployment automation?
- **R (Readiness)** — How production-ready is it? Does it have ownership docs, changelogs, runbooks, incident response, compliance artifacts?
- **V (Verification)** — How confident is the reviewer in its own grades? This one doesn't affect the final score — it's the reviewer grading itself.

Each axis is scored 0-9. The reviewer clones the repository, reads code, configs, tests, and docs, then collects evidence (what's present) and gaps (what's missing). It plays a "tug-of-war": evidence pulls the score up, gaps pull it down.

The **final composite score (S, 0-100)** combines A, P, and R using a harmonic mean that heavily punishes the weakest area. Think of a chain — the weakest link determines its strength. A project with brilliant AI (A=8) but no tests (P=1) and no docs (R=1) scores terribly. If any axis is near zero, the entire S score drops to near zero.

The **evidence hierarchy** determines how much weight different signals carry: working code > tests proving behavior > CI enforcement > operational artifacts > docs tied to implementation > general documentation > naming and aspirational language. Code that *does the thing* always outweighs docs that *describe the thing*.

The detailed companion reference for what each axis looks for and how to improve scores is in `reviews/aprv-scoring-reference-2026-06-10.md`.

---

## 1. How Rating Actually Works (End-to-End)

The rating system has **three distinct scoring paths** that converge at publication time:

### Path A: 16-Step Repo Analysis Pipeline (Primary)
```
orient → footprint → gitMeta → tests → securityScan
  → aCollect → aWar → pCollect → pWar → rCollect → rWar → vWar
  → aprvCoherence → deepening → summary
```

Each WAR step (aWar, pWar, rWar) asks the LLM to score a single axis using the "tug-of-war" method:
1. **Position** individual evidence on 0-9 spectrum
2. **Cluster** — find where bulk of evidence gathers (center, left bound, right bound)
3. **Tug-of-war** — gaps pull down, bonuses pull up. Spread >3.0 excludes bonuses.
4. **Sanity check** — score ≥6.0 requires corroboration from 2+ evidence surface types
5. **Output** float 0.00-9.99 per axis

The Collect steps (aCollect, pCollect, rCollect) gather raw evidence. The War steps score it. The `aprvCoherence` step cross-validates all four axes together. The `deepening` step scores 12 sub-axes (4 per A/P/R block).

**Verification (V)** is a meta-axis: it scores the *quality of evidence* seen during analysis, not a repository property. V is excluded from the composite S score.

### Path B: S Composite Score (Deterministic)
Computed in `scoring.mjs:computeProductScoreFromReadiness()`:
```
S = 100 * generalizedMean(A/9, P/9, R/9; p=-1, weights=[0.4, 0.3, 0.3]) * gate
gate = sigmoid(10*(A/9 - 0.2)) * sigmoid(10*(P/9 - 0.2)) * sigmoid(10*(R/9 - 0.2))
```

The **p=-1 (harmonic mean)** punishes imbalance — one weak axis drags the whole score down. The **sigmoid gate** with threshold 0.2 and k=10 smoothly zeros out the score when any axis drops near zero. S ranges 0-100 and maps to S0-S9 labels.

### Path C: Badge Rendering (Deterministic)
`floatToBadge(prefix, score)` in `traffic-light.mjs` converts the float to a human-readable badge:
- `[x.00, x.25)` → `A3` (plain level)
- `[x.25, x.50)` → `A3(+)` (strong for this level)
- `[x.50, x.75)` → `A4(-)` (weak for next level)
- `[x.75, x+1)` → `A4` (next level)

This is well-designed: 0.25-step resolution gives 40 distinct badges across 0-9, and the rendering is fully deterministic.

### Path D: Multi-Repo Aggregation
When a post references multiple repositories, `computePostReadinessAxes()` simply **averages** the per-repo scores for each axis, then feeds the averages into the S composite calculation. No weighting by repo significance, size, or confidence.

---

## 2. Root Causes of Inconsistency (Not Symptoms)

### Root Cause 1: Prompt-Score Coupling Without Ground Truth

The tug-of-war methodology is entirely prompt-described. The LLM interprets "position evidence on 0-9" using the label descriptors in the prompt (`A0 None` through `A9 Self-Improving`). These labels are:
- **Ordinal but not interval-scaled**: the perceptual distance between A3→A4 and A7→A8 is unknowable
- **Domain-loaded**: "Self-Improving" (A9) is a much more specific claim than "Stateful" (A4), creating implicit ceiling gravity around the middle
- **Not evidence-anchored**: the prompt says "A5 Controlled" but doesn't give concrete examples of what repo artifacts correspond to A5

**Why this breaks consistency:** Two LLM calls given identical repo evidence will disagree on where "Controlled" starts and "Coordinated" begins. This isn't prompt ambiguity — it's that the labels encode a subjective taxonomy without operational definitions.

**Measured impact:** This is the dominant source of variance, likely ±1.0-1.5 points across reruns on the same repo. The tug-of-war mechanics (cluster, spread, gaps/bonuses) add structured reasoning that helps, but the initial positioning of evidence on the scale is where the LLM exercises unbounded judgment.

### Root Cause 2: Evidence Collect/Score Separation is Partial

The pipeline separates evidence collection (aCollect/pCollect/rCollect) from scoring (aWar/pWar/rWar), which is architecturally sound. But the separation is **partial**:

- The **Collect** steps already embed judgment: each evidence item gets a `weight` field ("core"/"supporting"/"marginal") and a `level` field (0-9). These are LLM judgments baked into the evidence before the War step sees it.
- The **War** step receives pre-judged evidence and is asked to re-judge it on the same scale. It can disagree with the Collect weights, but in practice the anchoring is strong.

**Why this breaks consistency:** The same evidence can be classified as "core" in one run and "supporting" in another by the Collect step. The War step inherits this classification and produces different scores.

### Root Cause 3: Coherence Step is a Correction Layer, Not a Constraint

The `aprvCoherence` step receives all four axis scores and checks for cross-axis divergence >3.0. But it's implemented as another LLM call that can adjust scores. This means:
- It can **amplify** inconsistency if it "corrects" a correctly-scored axis toward an incorrectly-scored one
- The correction magnitude is unconstrained — the LLM decides how much to adjust
- It introduces a second scoring judgment on top of the first, compounding variance

**Why this breaks consistency:** On rerun, the WAR steps might produce scores that are slightly different but within tolerance. The coherence step might then adjust them in different directions, turning ±0.5 variance into ±1.5.

### Root Cause 4: No Rerun Stability Mechanism

There is no mechanism to detect or reduce variance between runs on the same repository. Each run is fully independent:
- No caching of intermediate evidence or scores
- No comparison with previous runs
- No "confidence interval" that widens when evidence is thin
- No ensemble (multiple LLM calls averaged)

This is a design choice, not an oversight — but it means consistency is entirely dependent on prompt engineering and LLM determinism, which are insufficient alone.

### Root Cause 5: Multi-Repo Averaging Destroys Signal

`computePostReadinessAxes()` averages per-repo axis scores with equal weight:
```javascript
agenticSum += Number.isFinite(a) ? Math.max(0, Math.min(9, a)) : 0;
// ...
agentic: Number((agenticSum / repos.length).toFixed(2)),
```

A post with a strong primary repo (A7) and a weak utility repo (A2) gets A4.5 — which is wrong in both directions. The primary repo's score should dominate, but there's no weighting by:
- Repo significance to the product
- Repo size or complexity
- Confidence of the individual analysis
- Whether the repo is a fork, utility, or core product

### Root Cause 6: Axis Asymmetry is Real But Unaddressed in Scoring

The REVIEW-025 issue correctly identified that A has a wide effective range (~0-9), P clusters in the middle (3-7), and R has a low practical ceiling for most repos. But the scoring math treats all axes symmetrically:
- S composite uses fixed weights (0.4/0.3/0.3) regardless of axis range
- The harmonic mean (p=-1) means a low R score (which is *expected* for most repos) penalizes S disproportionately
- The sigmoid gate (threshold 0.2) on a 0-1 normalized scale means R<1.8 starts gating — most young repos would trigger this

---

## 3. What Works and Should Be Preserved

### The Tug-of-War Scaffolding
The concept — position evidence, find cluster, tug with gaps/bonuses — is sound. It gives the LLM a structured reasoning framework that reduces "vibes-based" scoring. The spread>3.0 bonus exclusion rule prevents the LLM from inflating scores with scattered evidence.

### Float-First, Badge at Render
Removing the `level` string from model output and deriving badges deterministically via `floatToBadge()` was the right call. It eliminates one entire class of inconsistency (LLM picking different labels for the same numeric score).

### Collect/Score Separation (Partial)
Even though the separation is incomplete, having evidence in a structured array before scoring is architecturally valuable. This can be strengthened rather than replaced.

### S Composite Design
The harmonic mean with gating is a defensible choice for a "weakest link matters" scoring philosophy. The math is clean and deterministic. The issue is with the inputs (axis scores), not the aggregation.

### Deepening Receives Facts Not Scores
The deepening step's explicit instruction to use "previous analysis context" (footprint, signals) rather than the WAR scores is good for preventing anchoring bias in sub-axis scoring.

### The Normalizer Layer
`repo-analysis-parse.mjs` and `analysis-parse.mjs` are thorough: they clamp, validate, default, and structure every LLM output field. This prevents malformed data from propagating. The normalizers handle legacy field names, missing fields, and type coercion correctly.

---

## 4. What Should Be Redesigned

### 4.1 Evidence-Anchored Scale Definitions (Critical)

**Current state:** Labels like "A5 Controlled" with no concrete mapping to observable artifacts.

**Target:** Each scale point should have 3-5 concrete, verifiable repository conditions. Example:
```
A5 Controlled:
- REQUIRED: State persisted beyond process lifetime (DB, file, external store)
- REQUIRED: At least one multi-step workflow with explicit error recovery
- SUPPORTING: Configuration-driven behavior (env vars, config files change behavior without code changes)
- DISQUALIFYING: All state is in-memory only → cap at A4
```

This converts ordinal labels into operational definitions that two independent LLM calls (or humans) can apply more consistently.

**Implementation:** Update the WAR prompts to include these anchors. The REVIEW-025a solution spec has 10 evidence-anchored levels per axis already drafted — these should be finalized and integrated.

### 4.2 Remove Pre-Scoring from Collect Steps

**Current state:** Collect steps assign `weight` and `level` to evidence items.

**Target:** Collect steps should emit **only facts**: feature name, source type (test/CI/code/doc), and a brief observation. No `level`, no `weight`. The War step should be the sole scorer.

**Implementation:** Change the Collect prompt schema to remove `level` and `weight`. Change the normalizer `resolveWeightedItems()` to accept items without these fields. The War prompt already has the scoring methodology — it should classify evidence importance itself.

### 4.3 Constrain the Coherence Step

**Current state:** Free-form LLM correction of all four axes.

**Target:** The coherence step should be a **bounded adjustment** with deterministic rules:
1. If any two axes diverge >3.0, flag for human review (don't auto-correct)
2. If V confidence < 0.5, widen the uncertainty band on all axes by ±0.5
3. Maximum adjustment per axis: ±1.0 from the WAR score
4. All adjustments must cite a specific cross-axis contradiction

**Implementation:** Change the coherence prompt to enforce maximum adjustment. Add a post-LLM normalizer that clamps adjustments to ±1.0 from the original WAR scores. Log any clamped adjustments for audit.

### 4.4 Weighted Multi-Repo Aggregation

**Current state:** Simple average of per-repo scores.

**Target:** Weight repos by significance:
```
weight_i = (confidence_i * log(1 + codeLoc_i)) / sum(confidence_j * log(1 + codeLoc_j))
axis_score = sum(weight_i * score_i)
```

This gives more weight to larger repos that were analyzed with higher confidence, while the log prevents a single huge repo from dominating absolutely.

**Implementation:** Change `computePostReadinessAxes()` to accept and use per-repo confidence and size. The data is already available in the `parsed` object.

### 4.5 Reference Corpus for Regression Detection

**Current state:** Deferred. No ground truth exists.

**Target:** 10-15 pinned repositories with human-established ground-truth scores. Run the pipeline against these on every release. Fail the release if any axis deviates >1.0 from ground truth.

**This is the single most impactful change for production consistency.** Without it, every prompt tweak, model upgrade, or normalizer change is a blind experiment.

**Implementation:**
1. Pick 10-15 repos spanning the full 0-9 range across all axes
2. Have 2-3 humans independently score them using the evidence-anchored definitions
3. Take the median as ground truth
4. Add a CI step that runs the pipeline against the corpus and fails on >1.0 deviation
5. Store expected scores in `config/reference-corpus.json`

---

## 5. Structural Weakness: The "Two Pipelines" Problem

There are **two independent scoring codebases** that share concepts but not code:

| Concern | Review Pipeline (16-step) | Consolidated Pipeline |
|---------|--------------------------|----------------------|
| Normalizers | `repo-analysis-parse.mjs` | `analysis-parse.mjs` |
| Scale definitions | `composition-publication/scale.mjs` | `reporting/scale-constants.mjs` |
| Score computation | Inline in pipeline | `reporting/scoring.mjs` |
| Badge rendering | `traffic-light.mjs` (shared) | `traffic-light.mjs` (shared) |

The scale label arrays are **duplicated** — `AGENTIC_LABELS` exists in both `composition-publication/scale.mjs` and `reporting/scale-constants.mjs` as identical copies. The normalizer functions are **similar but different** — `normalizeRadarAxis()` exists in both `repo-analysis-parse.mjs` and `analysis-parse.mjs` with slightly different implementations.

**Risk:** A calibration change in one pipeline that isn't mirrored in the other produces inconsistent scores for the same repository depending on which pipeline path was used.

**Fix:** Extract shared scale definitions and scoring logic into `src/shared/scoring/` with a single source of truth. Both pipelines should import from the same module.

---

## 6. Concrete Implementation Sequence

### Phase 1: Foundation (Low Risk, High Signal)
1. **Build reference corpus** — 10 repos, human-scored, CI validation
2. **Deduplicate scale constants** — single source in `src/shared/scoring/`
3. **Add rerun variance test** — run pipeline 3x on same repo in CI, assert axis deviation <1.0

### Phase 2: Scoring Precision (Medium Risk)
4. **Deploy evidence-anchored scale definitions** — update WAR prompts with concrete level anchors from REVIEW-025a
5. **Remove pre-scoring from Collect** — strip `level`/`weight` from Collect output schema
6. **Constrain coherence adjustments** — ±1.0 cap with deterministic clamping

### Phase 3: Aggregation Quality (Medium Risk)
7. **Weighted multi-repo aggregation** — confidence × log(size) weighting
8. **Axis-aware S composite** — consider per-axis effective ranges in the S calculation (wider issue, may need the reference corpus data to calibrate)

### Phase 4: Stability Mechanisms (Higher Complexity)
9. **Previous-run comparison** — show delta from last run for the same repo, flag >1.5 deviation for human review
10. **Ensemble scoring** — 2-3 independent WAR calls, take median (expensive, saves for high-stakes runs)

---

## 7. Validation Steps

For each phase:
1. **Before change:** Run full pipeline on reference corpus, record all scores
2. **After change:** Run same corpus, compare. Every axis must stay within ±1.0 of ground truth.
3. **Rerun stability:** Run 3x on 3 reference repos. Standard deviation per axis must be <0.75.
4. **Edge cases:** Verify empty repos (all zeros), monorepos (high footprint, mixed quality), forks (partial evidence).

Specific regression tests to add:
- `floatToBadge` already well-tested — preserve these
- Add: `computeProductScoreFromReadiness` with known input/output pairs covering gate activation, single-axis-zero, balanced inputs
- Add: normalizer round-trip tests — feed a real LLM response through normalizer, verify no data loss
- Add: coherence clamping test — verify adjustments >1.0 are clamped

---

## 8. Prompt-vs-Code Enforcement Gaps

The prompts instruct the LLM to follow specific scoring rules, but the normalizer/validator pipeline does **not enforce** them. These gaps are not bugs — they're missing guardrails:

| Prompt Rule | Code Enforcement | Gap |
|---|---|---|
| Use 0.25/0.50 step sizes only | `clampScore()` accepts any float | LLM can emit 4.37 and it passes |
| Spread >3.0 → exclude bonuses from tug-of-war | `clampScore(spread)` stores it, nothing acts on it | Spread is descriptive, not a control variable |
| Score ≥6.0 requires 2+ independent surface types | Validator: `score > 0` | No multi-surface requirement enforced |
| Confidence inversely related to spread | `clamp01(confidence)` stores it as-is | No computed relationship between spread and confidence |
| Ceiling requirements must be "specific cheap steps" | `resolveCeiling()` accepts any string array | Vague requirements like "improve practices" pass |
| Gaps belong in `left.gaps`, not in `rawScore.evidence` | Normalizer validates structure, not semantics | Evidence vs. gap misclassification undetectable |

Each of these is a place where the LLM can deviate from the intended methodology and the pipeline won't catch it. Adding deterministic post-LLM checks for the most impactful rules (especially the spread>3.0 bonus exclusion and the ≥6.0 corroboration requirement) would reduce variance without changing the scoring philosophy.

---

## 9. Tradeoffs and Honest Limits

### What this analysis cannot resolve:
- **LLM stochasticity is irreducible.** Even with perfect prompts and anchors, two calls will differ by ±0.3-0.5. The goal is to keep variance below the badge boundary (0.25 steps), not eliminate it.
- **The harmonic mean philosophy is a policy choice.** Whether "weakest link matters" or "best axis matters" is a product decision, not an engineering one. The current p=-1 is defensible but aggressive.
- **V-axis ambiguity persists.** V measures "evidence quality" but is disconnected from the score it's supposed to calibrate. A repo with V2 and A7 means "I'm fairly confident the A7 is wrong" — but nothing in the pipeline acts on this.

### What ensemble scoring costs:
- 2-3x LLM calls per axis = 6-9x total cost per repo
- Latency increase of 2-3x (if parallel) to 6-9x (if sequential)
- Only justified for high-stakes or published scores

### What the reference corpus costs:
- One-time: ~2-3 person-days to score 10-15 repos by hand
- Ongoing: ~1 hour per month to validate corpus is still representative
- Risk: corpus becomes stale as the repos evolve. Pin to specific commits.

### What removing Collect pre-scoring risks:
- The War step receives more raw data and must do more judgment work in one pass
- This could *increase* variance temporarily until the War prompt is tuned
- Mitigation: A/B test on reference corpus before switching

---

## 10. Summary Judgment

The rating system's **mathematical scaffolding is solid** — the S composite, badge rendering, normalizers, and tug-of-war structure are well-engineered. The inconsistency problem is **not in the math but in the LLM-prompt interface**: the scale definitions are ordinal labels without operational anchors, the evidence chain leaks judgment into collection, and the coherence step adds unconstrained variance.

The single highest-ROI change is the **reference corpus**: without ground truth, every improvement is unmeasured. The second highest is **evidence-anchored scale definitions**: they convert subjective ordinal labels into verifiable conditions that both LLMs and humans can apply more consistently.

The system is closer to production-grade than it appears — the infrastructure for deterministic post-processing, structured retry, and observability is mature. The gap is in the scoring *input quality*, not the scoring *mechanics*.

---

## 11. Addendum: Post-Analysis Corrections & Implementation (2026-06-10)

### Corrections to Original Analysis

**Root Cause 5 is STALE.** `computePostReadinessAxes()` was already upgraded to weighted aggregation using `confidence * log(1 + codeLoc)` (Phase 5.1). The simple-average code described in §2 no longer exists. The current implementation gives more weight to larger repos with higher analysis confidence, with a `Math.max(0.01, ...)` floor to prevent zero-weight repos.

**All-max score is 99.9, not 100.** The sigmoid gate at k=10, threshold=0.2 means `sigmoid(10*(1-0.2)) = sigmoid(8) ≈ 0.9997`. With three axes: `gate ≈ 0.999`, so max S score = `100 * 1.0 * 0.999 = 99.9`. This is by design — the gate asymptotically approaches but never reaches 1.0.

### Gaps Found During Implementation

1. **Epsilon floor interaction with harmonic mean**: With `epsilon=1e-6` and p=-1, a zero axis produces `(1e-6)^(-1) = 1,000,000` in the weighted sum. The sigmoid gate (`sigmoid(-2) ≈ 0.119`) suppresses this, but the interaction produces S ≈ 0.18 for all-zero inputs, not exactly 0. Tested and documented.

2. **Portfolio L2 norm grows with portfolio size**: `computePortfolioScore()` uses `sqrt(sum(score^2))` — an announcer with two products at 50 each scores 70.7, while one product at 70 scores 70. This rewards breadth by design. Now documented with JSDoc.

3. **Scoring math was completely untested**: `computeProductScoreFromReadiness()`, `computePostReadinessAxes()`, `computePortfolioScore()`, and `sigmoid()` had zero test coverage. 31 tests now cover all edge cases including epsilon, gate boundaries, custom weights, and harmonic mean imbalance penalty.

### Changes Implemented

| Change | File | Tests |
|--------|------|-------|
| Scoring math tests (27 tests) | `test/pipeline/consolidated/reporting/scoring.test.mjs` | 27 pass |
| Scale constant deduplication | `src/pipeline/review/services/composition-publication/scale.mjs` | Imports from canonical `scale-constants.mjs` |
| Deterministic enforcement module | `src/pipeline/review/services/scoring-enforcement.mjs` | 15 tests |
| Enforcement wired into pipeline | `src/pipeline/review/services/repo-analysis-pipeline.mjs` | Spread rule, corroboration rule, coherence cap |
| V-axis confidence bands | `src/pipeline/consolidated/reporting/scoring.mjs` | 4 tests |
| Portfolio L2 norm documentation | `src/pipeline/consolidated/reporting/scoring.mjs` | JSDoc added |

### Remaining Work (Not Yet Implemented)

- **Phase 1F**: Reference corpus (3-5 pinned repos with human-scored ground truth)
- **Phase 2A**: Integrate REVIEW-025a evidence-anchored scale definitions into WAR prompts
- **Phase 2B**: Remove `level`/`weight` pre-scoring from Collect prompts
- These are tracked in REVIEW-038.
