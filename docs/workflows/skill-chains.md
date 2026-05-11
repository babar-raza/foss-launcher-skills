---
# Governance child document — extracted from AGENTS.md
# Source: AGENTS.md §6
# Plan: delightful-wondering-hartmanis (TC-04)
# Extracted: 2026-04-28
---

# Skill Chains by Task

Skills are the **only sanctioned execution mechanism** for the task types listed below. When your requirement matches a listed task type, you must follow the corresponding chain — invoking each skill in order, passing outputs forward, and not substituting manual reasoning for any step that has a registered skill. If your requirement does not match any listed task type, follow the protocol in §6b before doing anything else.

### Initial generation (new page)

```
S-10 (project-phase-store) → S-18 (page-plan) → S-19 (page-draft) → S-22 (faq-generate)
→ S-23 (content-check / audit.py) → S-38 (truth-audit, deep) → S-24 (evidence-cite) → S-01 (path-guard) → write
```

### Knowledge bootstrap

```
S-34 (repo-scout) → S-37 (knowledge-enrich) → S-35 (truth-merge) → S-31 (truth-index)
```

### Full-product launch (5-subdomain)

```
S-54 (knowledge-bootstrap) → S-47 (site-plan) → S-49 (launch-product stages 1–8)
```

Every launch MUST run `/site-plan` after knowledge bootstrap and BEFORE any content generation.
The site plan output (`reports/plans/{family}/{platform}/site_plan.yaml`) is the authoritative
slug manifest for blog posts, developer-guide pages, and KB how-to articles. Stages that skip
site-plan and hardcode or re-derive slugs are in violation of this chain.

### Maintenance (repo changed)

Use S-84 (refresh-product) to run the full maintenance cycle in one command:
```
/refresh-product {family} {platform}
```

S-84 orchestrates the 14-step chain internally:
```
S-12 (knowledge-diff — detect + fetch)       [exits early if no SHA change]
→ S-14 (knowledge-update — refresh + write knowledge_delta.json)
→ S-82 (delta-site-plan — site_planner --mode update)
→ S-20 (page-update — update stale pages from knowledge_delta.json)
→ delta-dispatch (generate pages_to_add by type)
→ S-83 (page-retire --from-plan — retire pages_to_remove; dry-run first)
→ S-62 --update (batch-reference — regenerate modified_apis reference pages)
→ S-48 (family-sync)
→ S-23 (content-check on all changed files)
→ S-65 (link-validate)
→ S-53 (translate-batch — content_hash-changed pages only)
→ post_refresh_verify --step (progress tracking after each step)
→ post_refresh_verify --verify (verification gate; must exit 0 before commit)
→ S-76 (commit)
```

Progress is tracked at `reports/refresh_state/{family}/{platform}/progress.json`.
Check status: `python scripts/pipeline/commands/ops/post_refresh_verify.py {family} {platform} --status`

> **Refresh is complete only when** `reports/refresh_review/{family}/{platform}/coverage_report.md`
> shows all 5 subdomains with `assessed > 0` and `post_refresh_verify --verify` exits 0 (Check 6).
> "Evidence refreshed" alone is not sufficient — body accuracy requires per-page PIA scoring.

### Audit-driven healing (content wrong but upstream SHA unchanged)

Use when S-84 exits early ("no SHA change") but content is known or suspected to be wrong.
S-87 (system-heal) is the canonical path — do not run gap-eval manually and then patch files:

```
/system-heal {family} {platform} [--scope all|docs|products|kb|blog|reference]
```

S-87 orchestrates the 8-phase chain internally:
```
S-43 --no-llm (deterministic baseline)          [halts if > 50 findings → use S-44+S-46]
→ S-43 (extended baseline: LLM + tier3_cache)
→ origin_map.py (classify CONTENT / PIPELINE / UPSTREAM / AMBIGUOUS)
→ Phase 4: CONTENT findings → S-74 (broken-link) | S-46 (wrong-pkg/wapi) | S-26 (wrong-claim/missing)
→ pipeline-evidence.md (PIPELINE + HOLD bucket — human action required)
→ S-43 (re-verify healed files; regression guard)
→ S-76 (commit) [only if fixed > 0 and regressions == 0]
→ final-report.md
→ S-88 /backlog harvest (automatic on final-report.md — extracts unresolved items to backlog)
```

AMBIGUOUS findings and findings with `tier3_non_determinism_flag: true` are never auto-repaired.
If finding count > 50, S-87 halts and directs to S-44 (gap-plan) + S-46 (gap-apply).

### Post-launch content enrichment (cross-subdomain gap fill)

```
S-54 (knowledge-bootstrap) → S-47 (site-plan) → S-98 audit → S-98 plan → S-98 execute
→ S-56/S-57/S-58/S-20 (via handoff manifest) → S-23 (content-check) → S-76 (commit)
```

S-98 operates in three modes:
- `audit`: read-only coverage matrix across products/docs/kb/blog/reference
- `plan` / `dry-run`: candidate generation with denominator invariant; no content writes
- `execute`: conservative handoff manifest for downstream skill invocation; requires `--allow-local-content-write`

Blog candidates are quality-gated (deferred to backlog unless score >= generate threshold).
Denominator invariant enforced: `total = generate_now + update_existing + deferred + rejected + blocked`.

### Enhancement (below rubric quality)

```
S-17 (rubric-align) → S-21 (page-enhance) → S-23 → S-01 → write
```

### Healing (grade D or below)

```
S-25 (eval-page) → S-26 (heal-page) → S-23 → S-25 → S-01 → write (or escalate)
```

#### Healing/Enhancement dispatch — grade-to-skill mapping

| Grade | Required skill | Rationale |
|-------|---------------|-----------|
| **A or B** | None (or S-21 for optional polish) | Meets quality bar |
| **C** | S-21 (page-enhance) only | No false claims; improve depth and structure |
| **D** | S-26 (heal-page) → check grade → if now C, optionally S-21 | False claims present; must heal before enhancing |
| **F** | S-26 (heal-page) → if no improvement after 2 passes → human escalation (§8) | Critical violations |

**Rule:** S-26 must precede S-21 when grade is D or below. S-21 alone is correct only for grade C. S-21 applied to a grade-D page without prior healing may suppress false claims that should be removed.

### 6d. Heal-Enabled Policy Table

The healing automation system (`scripts/pipeline/lib/heal_controller.py`) uses a
policy table (`scripts/pipeline/lib/heal_policy.py`) to route triaged findings to
the correct healing strategy. This section documents the binding between
evaluation findings and healing actions.

#### Heal modes

| Mode | Meaning | Automated? |
|------|---------|------------|
| `auto` | Deterministic fixer available (frontmatter, placeholder, code fence) | Yes |
| `llm` | Requires LLM-assisted rewrite grounded in knowledge artifacts | Yes |
| `regen` | Requires upstream causal backtracking before local fix | Yes |
| `human` | No automated path — escalate to operator | No |
| `skip` | INFO-level or not worth fixing | No |

#### Policy resolution order

1. **Exact match** on `(fix_type, category)` — e.g., `(llm, FC)` routes
   forbidden-claim findings to S-21 with FC-specific prompt constraints.
2. **Wildcard match** on `(fix_type, *)` — default for that fix type.
3. **Fallback** to `human` mode if neither matches.

#### Category-specific LLM policies

| Category | Description | Skill | Effort |
|----------|-------------|-------|--------|
| AA | API accuracy — verify against api_surface.json | S-21 | medium |
| FC | Forbidden claims — remove and rewrite | S-21 | medium |
| PC | Platform contamination — replace with correct platform code | S-21 | medium |
| PT | Prose truth — correct against enriched_claims.json | S-21 | medium |
| CP | Code plausibility — replace snippet from clone cache | S-21 | medium |
| RL | Risk language — context-aware rewrite | S-21 | medium |
| ST | Structure — regenerate missing sections | S-21 | medium |
| RV | Role violations (LLM bucket) — restructure page | S-21 | medium |

#### Non-LLM policies

| Fix type | Mode | Skill | Regen after? | Effort |
|----------|------|-------|--------------|--------|
| `auto` | auto | — | No | low |
| `upstream` | regen | S-80 (causal-backtrack) | Yes | high |
| `human` | human | — | No | high |
| `skip` | skip | — | No | low |

#### Governance rules

- **Only `auto`, `llm`, and `regen` modes are heal-enabled.** `human` and
  `skip` are excluded from automated healing pipelines.
- **The policy table is the single source of truth** for heal-mode routing.
  Do not hard-code heal-mode decisions outside `heal_policy.py`.
- **Regression detection is mandatory.** After any healing pass, run
  `verify.py` to compare before/after findings. If regression severity is
  `critical` (grade decreased), revert the healing and escalate.
- **Regen-after findings** (upstream mode) must complete causal backtracking
  via S-80 before local fixes run. The heal controller enforces this ordering.

### 6e. Terminal-Success State (ceiling-reached)

A page is **ceiling-reached** when ALL of the following are true:

1. `audit.py --files {path}` exits 0 (no FAIL findings)
2. `validate_frontmatter.py --files {path}` exits 0
3. Grade is A or B (0 FAIL, ≤5 WARN)
4. All remaining WARN findings have been explicitly classified as one of:
   - Evaluator/linter conflict artifacts (prose softening triggers linter revert;
     WARN is restored; no stable prose edit resolves it)
   - Known false positives (token collision, etc.) with a classification record
     in `reports/skill-gaps/`
5. A skill run has been attempted to address each WARN and confirmed that no further
   content change improves the stable outcome

**When a page is ceiling-reached, agents MUST**:
- Classify it as ceiling-reached in session notes or plan artifacts
- NOT re-apply prose softening that a prior session confirmed the linter reverts
- NOT invoke S-21 (page-enhance) again without a changed pre-condition (e.g., new
  knowledge model, updated evaluator, linter rule change)
- NOT invoke S-78 (evidence-enhance) again if a prior S-78 run returned ESCAPED and
  the manual evidence panel is richer than auto-detection output

**Ceiling-reached is not a failure state.** Grade B with 0 FAIL and known
evaluator-conflict WARNs is publish-ready per the quality rubric. The WARNs are
system artifacts, not content defects.

**Reopening conditions** (any one of these allows retry):
- `prose_truth` evaluator updated to consult evidence panel (Option P1 from
  `reports/skill-gaps/2026-04-06-prose-truth-evaluator-claim-check.md`)
- Linter rule is identified and found to be configurable or removable
- `attach_evidence.py` gains merge-safe mode that preserves manual `apis`
- Knowledge model is updated (re-run S-12 → S-14 first; re-evaluate; if grade
  drops, use appropriate skill chain)
- Human explicitly authorizes a retry with specific rationale

#### Quality gate dispatch — development vs launch

| Use case | Correct skill | When to use |
|----------|---------------|-------------|
| Iterative development (page-by-page improvement) | S-25 (eval-page) or S-51 (content-eval) | During generation/enhancement loops; many times per session |
| Pre-launch publishability gate | S-43 (gap-eval) | Once per launch cycle; verifies against clone cache truth |
| Cross-product quality summary | S-45 (gap-report) | Post-launch or periodic; cluster analysis across families |

**Rule:** Use S-43 at most once per launch cycle (expensive; requires clone cache). Use S-25/S-51 during development. Do not use S-43 as a development-loop quality check — it is a launch-readiness gate, not a rapid-iteration tool.

### Gap remediation (clone-cache verification + wave-ordered fixes)

```
S-43 (gap-eval) → S-44 (gap-plan) → S-46 (gap-apply) → S-23 (content-check) → S-01 (path-guard) → write
```

Wave 4 items from S-46 are escalated to human review. Address each item via S-73 (manual-edit) with the operator-specified fix — do not apply ad hoc fixes outside the skill chain.

### Evidence gap recovery (validator-blocked commits)

Triggered when `validate_frontmatter.py` (P-03) or `audit.py` (evidence FAIL) blocks a commit.

```
S-72 (evidence-repair) → S-23 (content-check) → S-01 (path-guard) → write
```

S-72 runs `attach_evidence.py --force` first (Stage 1). If claims or apis remain empty, it performs a knowledge-grounded reasoning pass (Stage 2). If evidence cannot be confidently populated, it applies the `manual-remediation` escape (P-03 exempt) and writes an escalation entry to `reports/evidence-repair/needs-human-{date}.md`.

Wave 4 analogue: ESCAPED files are routed to human for manual evidence population — do not guess.

### Operator-directed targeted edit (specific change specified by operator)

```
S-73 (manual-edit) → embedded S-01 (path-guard) → embedded S-24 (evidence-cite) → write
```

Use when the operator knows exactly what to change (a specific sentence, frontmatter field, code block, or section) and can specify it. Do not use when the agent should decide what to fix — use S-26 (heal-page), S-21 (page-enhance), or S-20 (page-update) instead.

Wave 4 items from S-46 (gap-apply) must be addressed via S-73. Do not apply ad hoc fixes.

### Grade semantics and publication readiness

**Grade A means automated checks passed — it does NOT mean publication-ready.**

The evaluator suite covers approximately 60% of known defect classes. A grade of A or B confirms that no automated evaluator detected a violation. It does not confirm that a human reviewer would accept the page for publication.

| Grade | Automated check result | Publication implication |
|-------|----------------------|-------------------------|
| A | All default evaluators passed | Eligible for automated-pass status; still requires human review for Tier 1 content (§7b) |
| B | No FAIL; some WARN (capped categories) | Eligible for spot-check review |
| C | Category ceiling applied (TA/FT/NC/SX/FM ceiling) | Must resolve WARN findings before promotion |
| D | One or more WARN → FAIL escalation | Requires heal-page (S-26) before publishing |
| F | Critical finding (FC/PC/TA FAIL) or grade ceiling forced | Blocked from publication; must heal and re-evaluate |

**Manual-edit decision rule**: When content appears wrong, apply this decision tree before editing:

1. Is the knowledge artifact (api_surface.json, formats.json, claims.json) wrong?
   → Fix upstream: re-run repo-scout (S-34) or knowledge-update (S-14), then regenerate.
2. Is the content page wrong but the knowledge is correct?
   → Use S-73 (manual-edit) for targeted fixes.
3. Is the page below quality bar (grade C or below) but factually correct?
   → Use S-21 (page-enhance) for grade C, S-26 (heal-page) for grade D/F.
4. Do not patch content manually for quality issues that should be fixed in the generator —
   file a skill gap report (§6b) and let the system generate correctly next time.

### Batch reference page generation

```
batch-reference → /truth-audit (spot-check) → S-24 (evidence-cite) → S-01 (path-guard) → write
```

Platform scope rules enforced by `batch-reference`:
- **cpp / python**: concrete classes only (skip `^I[A-Z].*` abstract types and known C++ base classes); enums included
- **java / net**: interfaces, concrete classes, structs, and enums all included
- **Idempotency**: existing pages are never overwritten; re-runs skip already-present slugs

**Known limitation — Grade C floor for FOSS reference pages without XML docstrings**: FOSS
libraries (e.g. Aspose.Cells_FOSS for .NET) do not contain XML documentation comments.
`batch_reference.py` correctly extracts an empty `doc` field for these classes.
`DescriptionCompletenessEvaluator` fires DC FAIL when >70% of description cells in a method
table are empty, which floors the grade at C (`compute_grade()`: 1+ FAIL → C).

**Grade C is the accepted publish floor for reference pages from FOSS libraries with no
docstrings, provided the method/property tables are structurally complete (all extracted
members listed).** Do not attempt to heal these pages by fabricating descriptions — the empty
descriptions are correct and reflect the source truth. Do not gate publication on Grade B for
this class of page. The evaluator FAIL is expected and acknowledged.

To distinguish acceptable Grade C from a genuine structural gap: a Grade C reference page is
acceptable only if it has a non-empty `evidence.apis` block. A reference page with an empty
`evidence.apis` block is a structural gap regardless of grade and requires investigation.

### Provenance contract for creation-path skills (Control 1 — Phase N)

> **MANDATORY — do not remove this requirement from any creation-path skill.**

Every skill that creates a new English content page MUST write a `provenance:` block in the
page's frontmatter template as part of the same `Write` tool call that creates the page. This
is a provenance contract — removing it breaks `verified_at_creation` classification.

**For content-generating skills** (`new-docs-page`, `new-blog-post`, `new-kb-howto`, `new-kb-faq`,
`new-reference-page`, `page-draft`, `new-products-page`, `batch-reference`):

```yaml
provenance:
  content_origin: skill-generated
  last_mechanism: skill
  auto_updatable: true
  content_created_at: '{today as YYYY-MM-DD}'
```

**For structural-scaffold skills** (`new-docs-index`, `new-kb-index`, `new-reference-index`):

```yaml
provenance:
  content_origin: unknown
  last_mechanism: skill
  auto_updatable: false
  provenance_recovery_note: structural-page
  content_created_at: '{today as YYYY-MM-DD}'
```

**`content_created_at` is required**: `validate_frontmatter.py` enforces this field on any page
whose `graded_at` falls within the last 7 days. All creation-path skills MUST include it. It is
set once at creation and is protected by a write-once guard in `provenance.py` — subsequent
evidence or grade writes will not overwrite it.

**Why this matters:** Without a concurrent provenance write at creation time, every new page
enters the corpus as `content_origin: unknown`. Post-hoc classification via
`content_origin_recover.py` produces only `pipeline_signal_only` status — it cannot
produce `verified_at_creation`. Only a concurrent write (skill writes `content_origin` in
the same `Write` call as the frontmatter) achieves `verified_at_creation` per §10b taxonomy.

**Launch gate enforcement:** `launch_gate.py` Check 2b (L-02b) blocks launch for any English
page missing `content_origin` in its provenance block. This check fires at the launch gate
to prevent pages that bypassed the skill contract from reaching production.

### Plan execution gate

Before executing any plan that meets one or more of the following conditions, run
`/plan-normalize {plan-file}` (S-91) first:

- Inherited from another agent or session
- Contains archive, postmortem, sprint, or completed-work sections
- Last modified more than 7 days ago
- Contains capability claims without explicit maturity labels
- Not immediately executed after the planning skill produced it

If S-91 returns `execution-ready-as-is: no`, do not proceed until the blocking
conditions are resolved. S-91 replaces manual "re-read and judge" reasoning for
plan-normalization. It does not replace specialized planning skills.

