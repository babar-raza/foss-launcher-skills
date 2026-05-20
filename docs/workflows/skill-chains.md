<!-- Adapted from aspose.org docs/workflows/ for standalone use -->

# Skill Chains by Task

Skills are the **only sanctioned execution mechanism** for the task types listed below. When your requirement matches a listed task type, you must follow the corresponding chain -- invoking each skill in order, passing outputs forward, and not substituting manual reasoning for any step that has a registered skill. If your requirement does not match any listed task type, follow the gap escalation protocol before doing anything else.

### Initial generation (new page)

```
page-plan -> page-draft -> faq-generate
-> content-check / audit -> truth-audit (deep) -> evidence-cite -> path-guard -> write
```

### Knowledge bootstrap

```
repo-scout -> knowledge-enrich -> truth-merge -> truth-index
```

### Full-product launch (multi-subdomain)

```
knowledge-bootstrap -> site-plan -> launch-product (stages 1-8)
```

Every launch MUST run site-plan after knowledge bootstrap and BEFORE any content generation.
The site plan output (`reports/plans/{family}/{platform}/site_plan.yaml`) is the authoritative
slug manifest for blog posts, developer-guide pages, and how-to articles. Stages that skip
site-plan and hardcode or re-derive slugs are in violation of this chain.

### Maintenance (repo changed)

Use refresh-product to run the full maintenance cycle in one command:
```
/refresh-product {family} {platform}
```

The refresh-product skill orchestrates the 14-step chain internally:
```
knowledge-diff (detect + fetch)       [exits early if no SHA change]
-> knowledge-update (refresh + write knowledge_delta.json)
-> delta-site-plan (site_planner --mode update)
-> page-update (update stale pages from knowledge_delta.json)
-> delta-dispatch (generate pages_to_add by type)
-> page-retire (retire pages_to_remove; dry-run first)
-> batch-reference --update (regenerate modified_apis reference pages)
-> family-sync
-> content-check (on all changed files)
-> link-validate
-> translate-batch (content_hash-changed pages only)
-> post_refresh_verify --step (progress tracking after each step)
-> post_refresh_verify --verify (verification gate; must exit 0 before commit)
-> commit
```

Progress is tracked at `reports/refresh_state/{family}/{platform}/progress.json`.

> **Refresh is complete only when** the coverage report
> shows all subdomains with `assessed > 0` and `post_refresh_verify --verify` exits 0.
> "Evidence refreshed" alone is not sufficient -- body accuracy requires per-page scoring.

### Audit-driven healing (content wrong but upstream SHA unchanged)

Use when refresh exits early ("no SHA change") but content is known or suspected to be wrong.
System-heal is the canonical path -- do not run gap-eval manually and then patch files:

```
/system-heal {family} {platform} [--scope all|docs|products|kb|blog|reference]
```

System-heal orchestrates the 8-phase chain internally:
```
gap-eval --no-llm (deterministic baseline)          [halts if > 50 findings]
-> gap-eval (extended baseline: LLM + tier3_cache)
-> origin_map.py (classify CONTENT / PIPELINE / UPSTREAM / AMBIGUOUS)
-> Phase 4: CONTENT findings -> broken-link | wrong-pkg/wapi | wrong-claim/missing
-> pipeline-evidence.md (PIPELINE + HOLD bucket -- human action required)
-> gap-eval (re-verify healed files; regression guard)
-> commit [only if fixed > 0 and regressions == 0]
-> final-report.md
-> backlog harvest (automatic on final-report -- extracts unresolved items to backlog)
```

AMBIGUOUS findings and findings with `tier3_non_determinism_flag: true` are never auto-repaired.
If finding count > 50, system-heal halts and directs to gap-plan + gap-apply.

### Post-launch content enrichment (cross-subdomain gap fill)

```
knowledge-bootstrap -> site-plan -> content-enrichment audit -> plan -> execute
-> downstream skill invocation (via handoff manifest) -> content-check -> commit
```

Content enrichment operates in three modes:
- `audit`: read-only coverage matrix across all content subdomains
- `plan` / `dry-run`: candidate generation with denominator invariant; no content writes
- `execute`: conservative handoff manifest for downstream skill invocation; requires `--allow-local-content-write`

Blog candidates are quality-gated (deferred to backlog unless score >= generate threshold).
Denominator invariant enforced: `total = generate_now + update_existing + deferred + rejected + blocked`.

### Enhancement (below rubric quality)

```
rubric-align -> page-enhance -> content-check -> path-guard -> write
```

### Healing (grade D or below)

```
eval-page -> heal-page -> content-check -> eval-page -> path-guard -> write (or escalate)
```

#### Healing/Enhancement dispatch -- grade-to-skill mapping

| Grade | Required skill | Rationale |
|-------|---------------|-----------|
| **A or B** | None (or page-enhance for optional polish) | Meets quality bar |
| **C** | page-enhance only | No false claims; improve depth and structure |
| **D** | heal-page -> check grade -> if now C, optionally page-enhance | False claims present; must heal before enhancing |
| **F** | heal-page -> if no improvement after 2 passes -> human escalation | Critical violations |

**Rule:** heal-page must precede page-enhance when grade is D or below. page-enhance alone is correct only for grade C. page-enhance applied to a grade-D page without prior healing may suppress false claims that should be removed.

### Heal-Enabled Policy Table

The healing automation system uses a policy table to route triaged findings to
the correct healing strategy. See [heal-policy.md](heal-policy.md) for the full
binding between evaluation findings and healing actions.

### Gap remediation (clone-cache verification + wave-ordered fixes)

```
gap-eval -> gap-plan -> gap-apply -> content-check -> path-guard -> write
```

Wave 4 items are escalated to human review. Address each item via manual-edit with the operator-specified fix -- do not apply ad hoc fixes outside the skill chain.

### Evidence gap recovery (validator-blocked commits)

Triggered when frontmatter validation or evidence audit blocks a commit.

```
evidence-repair -> content-check -> path-guard -> write
```

Evidence-repair runs `attach_evidence.py --force` first (Stage 1). If claims or apis remain empty, it performs a knowledge-grounded reasoning pass (Stage 2). If evidence cannot be confidently populated, it applies the `manual-remediation` escape and writes an escalation entry to `reports/evidence-repair/needs-human-{date}.md`.

### Operator-directed targeted edit (specific change specified by operator)

```
manual-edit -> path-guard -> evidence-cite -> write
```

Use when the operator knows exactly what to change (a specific sentence, frontmatter field, code block, or section) and can specify it. Do not use when the agent should decide what to fix -- use heal-page, page-enhance, or page-update instead.

### Grade semantics and publication readiness

**Grade A means automated checks passed -- it does NOT mean publication-ready.**

The evaluator suite covers approximately 60% of known defect classes. A grade of A or B confirms that no automated evaluator detected a violation. It does not confirm that a human reviewer would accept the page for publication.

| Grade | Automated check result | Publication implication |
|-------|----------------------|-------------------------|
| A | All default evaluators passed | Eligible for automated-pass status; still requires human review for Tier 1 content |
| B | No FAIL; some WARN (capped categories) | Eligible for spot-check review |
| C | Category ceiling applied | Must resolve WARN findings before promotion |
| D | One or more WARN -> FAIL escalation | Requires heal-page before publishing |
| F | Critical finding or grade ceiling forced | Blocked from publication; must heal and re-evaluate |

**Manual-edit decision rule**: When content appears wrong, apply this decision tree before editing:

1. Is the knowledge artifact (api_surface.json, formats.json, claims.json) wrong?
   -> Fix upstream: re-run repo-scout or knowledge-update, then regenerate.
2. Is the content page wrong but the knowledge is correct?
   -> Use manual-edit for targeted fixes.
3. Is the page below quality bar (grade C or below) but factually correct?
   -> Use page-enhance for grade C, heal-page for grade D/F.
4. Do not patch content manually for quality issues that should be fixed in the generator --
   file a skill gap report and let the system generate correctly next time.

### Batch reference page generation

```
batch-reference -> truth-audit (spot-check) -> evidence-cite -> path-guard -> write
```

Platform scope rules enforced by batch-reference:
- **cpp / python (typed languages)**: concrete classes only (skip abstract types and known C++ base classes); enums included
- **java / net**: interfaces, concrete classes, structs, and enums all included
- **Idempotency**: existing pages are never overwritten; re-runs skip already-present slugs

**Known limitation -- Grade C floor for FOSS reference pages without XML docstrings**: FOSS
libraries that do not contain XML documentation comments will have empty `doc` fields.
The description completeness evaluator fires DC FAIL when >70% of description cells in a method
table are empty, which floors the grade at C.

**Grade C is the accepted publish floor for reference pages from FOSS libraries with no
docstrings, provided the method/property tables are structurally complete.** Do not attempt
to heal these pages by fabricating descriptions -- the empty descriptions are correct and
reflect the source truth. Do not gate publication on Grade B for this class of page.

### Provenance contract for creation-path skills

> **MANDATORY -- do not remove this requirement from any creation-path skill.**

Every skill that creates a new English content page MUST write a `provenance:` block in the
page's frontmatter template as part of the same write call that creates the page.

**For content-generating skills**:

```yaml
provenance:
  content_origin: skill-generated
  last_mechanism: skill
  auto_updatable: true
  content_created_at: '{today as YYYY-MM-DD}'
```

**For structural-scaffold skills**:

```yaml
provenance:
  content_origin: unknown
  last_mechanism: skill
  auto_updatable: false
  provenance_recovery_note: structural-page
  content_created_at: '{today as YYYY-MM-DD}'
```

**`content_created_at` is required**: frontmatter validation enforces this field on any page
whose `graded_at` falls within the last 7 days. All creation-path skills MUST include it.

**Why this matters:** Without a concurrent provenance write at creation time, every new page
enters the corpus as `content_origin: unknown`. Post-hoc classification produces only
`pipeline_signal_only` status -- it cannot produce `verified_at_creation`. Only a concurrent
write achieves `verified_at_creation`.

**Launch gate enforcement:** The launch gate blocks launch for any English page missing
`content_origin` in its provenance block.

### Plan execution gate

Before executing any plan that meets one or more of the following conditions, run
`/plan-normalize {plan-file}` first:

- Inherited from another agent or session
- Contains archive, postmortem, sprint, or completed-work sections
- Last modified more than 7 days ago
- Contains capability claims without explicit maturity labels
- Not immediately executed after the planning skill produced it

If plan-normalize returns `execution-ready-as-is: no`, do not proceed until the blocking
conditions are resolved.
