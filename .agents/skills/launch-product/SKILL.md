<!-- CONTRACT: agent-executed
     purpose: orchestrate 5-subdomain full documentation launch (products, blog, docs, kb, reference)
     preconditions: knowledge bootstrapped; clone cache populated
     postcondition: all 5 subdomains populated, graded, and readiness scorecard produced
     idempotent: yes — checkpoint-based resume skips completed stages
     verified: 2026-04-11
-->
# S-49: Launch Product — 5-Subdomain Full Documentation Launch

**Arguments**: $ARGUMENTS
**Expected format**: `{family} {platform}` — e.g. `3d java` or `slides python`

## Purpose

Orchestrate a full 5-subdomain documentation launch for a FOSS product: products, blog, docs,
kb, and reference pages. Uses `project-phase-store` (S-10) for checkpoint-based resume.

## Pre-conditions

- All Phase 0 skills must be fixed (P0-1 through P0-5) — HTML comment evidence violation fixed
- `no-downgrade-guard` skill must exist
- `new-products-page` skill must exist
- `site-plan` skill must exist (S-47) — required for Stage 0.5

## Stages

### STAGE 0 — Knowledge Bootstrap
**Command**: `/knowledge-bootstrap {family} {platform}`
**Checkpoint**: `knowledge_ready`

**On completion**:
- `KNOWLEDGE: STOP:partial` → halt and explain; do not proceed
- `KNOWLEDGE: REFRESHED` → halt: "Knowledge refreshed from upstream changes. Run `/knowledge-diff`
  to review what changed, then re-run `/launch-product {family} {platform}`."
- Any other status → continue to Stage 0.5

**Save checkpoint**: `python scripts/pipeline/commands/ops/project_phase_store.py set {family} {platform} knowledge_ready true`

---

### STAGE 0.5 — Site Plan
**Command**: `/site-plan {family} {platform}`
**Output**: `reports/plans/{family}/{platform}/site_plan.yaml`
**Checkpoint**: `site_plan_done`

**Skip condition**: If checkpoint `site_plan_done` is already `true` AND
`reports/plans/{family}/{platform}/site_plan.yaml` exists, skip this stage.

**Failure handling**: If `/site-plan` (site_planner) exits non-zero, **STOP**.
Print the error output and do not proceed to Stage 1. Resolve the site-plan
failure before continuing the launch.

This stage computes all content slugs from the knowledge model via `site_planner.py`:
- **Blog slugs**: 2 mandatory posts + 1 optional deep-dive (present when total_claims >= 500
  and top cluster has snippet_count >= 3)
- **Developer-guide page slugs**: one per eligible cluster
  (threshold: `claim_count >= 5, api_method_count >= 1, not in_limitations, not in KB_SKIP_CLUSTERS`)
- **KB how-to slugs**: up to 7 eligible clusters
  (pattern: `how-to-{verb}-{noun}-{platform_suffix}`)

**After running**, read and record from `reports/plans/{family}/{platform}/site_plan.yaml`:
- `sections.blog.pages[*]` — blog slugs (mandatory first, then optional deep-dive)
- `sections.docs.pages` where `cluster` field is set and `page_class: generated` — developer-guide slugs
- `sections.kb.pages` where `type: topic` and `page_class: generated` — KB how-to slugs

**All subsequent content generation stages MUST read slugs from this plan output.**
Slug patterns in stage descriptions below are documentation examples only — use actual
values from the site plan. Do not re-derive or hardcode slugs.

**Save checkpoint**: `python scripts/pipeline/commands/ops/project_phase_store.py set {family} {platform} site_plan_done true`

---

### STAGE 1 — Products Page
**Command**: `/new-products-page {family} {platform}`
**Checkpoint**: `products_done`

**Skip condition**: `content/products.aspose.org/en/{family}/{platform}/_index.md` already exists AND
passes `python scripts/pipeline/commands/content/audit.py --files content/products.aspose.org/en/{family}/{platform}/_index.md`
(0 FAIL)

**Save checkpoint** when done.

---

### STAGE 1.5 — Family Page Sync

**Condition**: Run ONLY when >= 2 platform subdirectories exist under
`content/products.aspose.org/en/{family}/` after Stage 1 completes.

If only 1 platform subdirectory exists (first launch), skip — family page was just created fresh.

**Command**: `/family-sync {family}`

**Checkpoint**: `family_sync_done`

**Skip condition**: only 1 platform subdirectory exists under the family

**Save checkpoint**: `python scripts/pipeline/commands/ops/project_phase_store.py set {family} {platform} family_sync_done true`

---

### STAGE 2 — Blog Posts
**Pre-condition**: Verify `reports/plans/{family}/{platform}/site_plan.yaml` exists.
If missing, STOP and re-run Stage 0.5.

**Read**: `reports/plans/{family}/{platform}/site_plan.yaml` → `sections.blog.pages`

**Commands**: For each entry with `page_class: generated`, run in order:
```
/new-blog-post {family} {platform} {slug}
```

Mandatory posts (always present in site plan — example slugs shown, use actual plan values):
1. Intro post — e.g. `introducing-{family}-foss-{platform}`
2. Key features post — e.g. `{family}-key-features-{platform}`

Optional 3rd post (present in site plan only when `total_claims >= 500` and top cluster
`snippet_count >= 3`):
3. Deep-dive post — e.g. `{top_cluster_slug}-in-{platform}`

**Skip condition per slug**: directory `content/blog.aspose.org/{family}/{platform}/{slug}/`
already exists AND its `index.md` passes audit (0 FAIL)

**Checkpoint**: `blog_done`

---

### STAGE 3 — Documentation Pages
**Pre-condition**: Verify `reports/plans/{family}/{platform}/site_plan.yaml` exists.
If missing, STOP and re-run Stage 0.5.

**Read**: `reports/plans/{family}/{platform}/site_plan.yaml` → `sections.docs.pages`

**Commands**:
1. `/new-docs-index {family} {platform}`
2. Fixed pages (always generate if missing):
   - `/new-docs-page {family} {platform} getting-started installation`
   - `/new-docs-page {family} {platform} getting-started quickstart`
   - If site plan includes `getting-started/license`:
     `/new-docs-page {family} {platform} getting-started license`
3. Cluster-derived developer-guide pages — for each entry in site plan docs section
   where `cluster` field is set and `page_class: generated`:
   - `/new-docs-page {family} {platform} developer-guide {slug}`
   - Use slug **exactly as given in site plan** — do not re-derive from claims.json

**Command per content page**: `/new-docs-page {family} {platform} {section} {slug}`

**Skip condition**: files already exist AND pass audit (step 1 is self-idempotent — it skips
automatically if `_index.md` already has `linktitle`, `layout: list`, and `{{< sections >}}`)

**Checkpoint**: `docs_done`

---

### STAGE 4 — KB Articles
**Pre-condition**: Verify `reports/plans/{family}/{platform}/site_plan.yaml` exists.
If missing, STOP and re-run Stage 0.5.

**Read**: `reports/plans/{family}/{platform}/site_plan.yaml` → `sections.kb.pages`

**Commands**:
1. `/new-kb-index {family} {platform}`
2. `/new-kb-faq {family} {platform}`
3. For each entry in site plan KB section where `type: topic` and `page_class: generated`:
   - `/new-kb-howto {family} {platform} {slug}`
   - Use slug **exactly as given in site plan** — pattern is `how-to-{verb}-{noun}-{platform_suffix}`
   - Expected count: 1–7 articles depending on cluster thresholds
   - Do NOT default to a single hardcoded `how-to-get-started-*` slug

**Skip condition**: files already exist AND pass audit (step 1 is self-idempotent — it skips
automatically if `_index.md` already has `linkTitle`, `layout: list`, and `{{< children >}}`)

**Checkpoint**: `kb_done`

---

### STAGE 4.5 — Products Page FAQ Backfill
**Checkpoint**: `products_faq_done`

**Purpose**: Populate the products page FAQ section now that the KB FAQ exists (created in Stage 4).

**Skip condition**: products page `faq.enable` is already `true` with a non-empty `faq.list[]`

**Steps**:
1. Read `content/kb.aspose.org/en/{family}/{platform}/faq.md`
2. If file exists and contains Q&A content, extract 4–6 representative Q&A pairs
3. Update `content/products.aspose.org/en/{family}/{platform}/_index.md`:
   - Set `faq.enable: true`
   - Populate `faq.list[]` with extracted Q&A pairs (question + short 1–2 sentence answer)
4. If KB FAQ does not exist (unlikely after Stage 4), leave `faq: enable: false` unchanged

**Save checkpoint**: `python scripts/pipeline/commands/ops/project_phase_store.py set {family} {platform} products_faq_done true`

---

### STAGE 5 — Reference Pages (Batch)
**Commands**:
1. `/new-reference-index {family} {platform}`
2. `/batch-reference {family} {platform}`

Step 1 is self-idempotent — skips if `_index.md` already has `layout: list` and
`{{< children >}}`. Step 2 is idempotent — skips existing class pages automatically.

**Post-generation note**: As of Fix 8 (2026-04-07), `batch_reference.py` calls
`attach_evidence()` internally after writing each class page. This means no separate
evidence attachment step is needed after Stage 5 — grading (`grade:`, `graded_at:`)
and evidence (`apis:`, `claims:`) are written during generation.

**Checkpoint**: `reference_done`

---

### STAGE 5.5 — Family Index Verification

**Purpose**: Confirm that the family-level `_index.md` files were created by
S-70/S-69/S-71 (step 5) during Stages 3–5. Without these files the family is
invisible in `{{< docs-families >}}` listings and sidebars.

**Check**: For each of `docs.aspose.org`, `kb.aspose.org`, `reference.aspose.org`:
1. Verify `content/{site}/en/{family}/_index.md` exists
2. Verify it contains `layout:` in the frontmatter

If any file is missing or malformed:
`LAUNCH BLOCKED: family index missing for {site}/{family} — re-run the corresponding /new-*-index skill`

**This is a read-only verification step** — it does not create files. If it fails,
re-run the relevant platform-index skill (`/new-docs-index`, `/new-kb-index`, or
`/new-reference-index`) which will create the family index in its step 5.

**Checkpoint**: `family_indexes_verified`

---

### STAGE 6 — Truth Audit
**Command**: `/truth-audit {family} {platform}`
**Checkpoint**: `truth_audit_done`

**On FAIL findings**: Print the full list. **Do NOT auto-fix.** Require human review or
healing agent to resolve before marking this checkpoint complete. Do not proceed to Stage 7 until FAIL count is 0.

---

### STAGE 7 — Quality Check + Auto-Fix
**Command**: `/batch-eval-fix {family} {platform}`
**Checkpoint**: `quality_done`

Auto-fixes deterministic issues only (no LLM pass). Reviews eval grades.

---

### STAGE 8 — Readiness Scorecard
**Command**:
```bash
.venv/Scripts/python scripts/pipeline/commands/launch/readiness_scorecard.py --family {family} --platform {platform} --set-checkpoint
```
**Checkpoint**: `readiness_done`

The script collects grades automatically. Review the output below.

Print per-page grades with counts:
```
=== LAUNCH READINESS: {family}/{platform} ===
Products page:   {grade}
Blog posts:      {A/B/C/D/F per post} ({N} posts)
Docs pages:      {grade summary} ({N} pages)
KB articles:     {grade summary} ({N} pages)
Reference pages: {grade summary} ({N} pages)

A: N  B: N  C: N  D: N  F: N

```

**Print**: `READY TO SHIP` or `NOT READY` with a bullet list of blocking items.

```
READY TO SHIP if:
  - 0 D/F pages
  - products + getting-started + first blog post at B+
```

> **Grade calibration — reference pages**: Reference page grades reflect both API surface accuracy
> and description completeness (`description_completeness` evaluator runs alongside the audit tier
> for reference pages). For FOSS repos without XML docstrings, grade **C** is expected and
> acceptable — it means the API structure is correct but description fields are empty
> (`description_completeness` FAIL for tables with ≥3 rows). Grade B or above requires non-empty
> description text from ERC enrichment. Grade **A** is NOT expected for skeleton reference pages
> from undocumented FOSS repos.

---

### STAGE 8.5 — Governed Review Gates (H-01 through H-05, executed by S-90)

> **Updated 2026-04-17** — H-gates are now executed by S-90 (`/publish-readiness-review`)
> per §7c and §7a (full detail: [docs/governance/launch-gates.md](../docs/governance/launch-gates.md)). The agent performs all 5 gate equivalents. Real human escalation only
> per §7c conditions (see AGENTS.md §7c).

**Step 1 — Invoke S-90 as the governed H-gate executor:**
```
/publish-readiness-review {family} {platform} --triage-unknowns
```

S-90 covers all 5 gates internally:
- **H-01** (prose review): Inspects a sample of non-reference pages against `claims.json` + `api_surface.json`
- **H-02** (reference accuracy): Invokes S-38 (truth-audit) on a stratified reference sample
- **H-03** (format table spot-check): Runs `content_eval --evaluators format_truth` on pages with format tables
- **H-04** (link validation): Invokes S-65 (link-validate) for all cross-subdomain links
- **H-05** (license accuracy): Reads LICENSE from clone cache; checks against products page claim

**Step 2 — Review S-90 output:**

S-90 writes `reports/publish-review/{family}-{platform}-{YYYYMMDD}/final-verdict.md`.
This replaces the per-gate sign-off files. The verdict format covers:
- Per-section READY/CONDITIONAL/BLOCKED
- Actions taken (S-21/S-26/batch-reference/S-65/S-38 invocations)
- Items escalated to real human (only those matching §7c real-escalation conditions)

**Step 3 — Record results in scorecard:**
```bash
.venv/Scripts/python scripts/pipeline/commands/launch/readiness_scorecard.py --family {family} --platform {platform} --set-checkpoint
```

The scorecard accepts the S-90 final-verdict.md as H-gate sign-off. "READY TO SHIP" requires
the S-90 verdict to be PUBLISH or CONDITIONAL (with all CONDITIONAL items having been
actioned by S-90's fix-skill invocations). If S-90 verdict is BLOCKED, the launch is blocked.

> **Note**: Use `--skip-human-review` during development only. Production launches require all H-gates.

---

## Resume Behavior

On re-run, read checkpoint state:
```bash
.venv/Scripts/python scripts/pipeline/commands/ops/project_phase_store.py get {family} {platform}
```
Skip completed stages. Print: `Resuming {family}/{platform} from stage N (checkpoint: {name})`

## Checkpoint Storage

Checkpoints are stored via S-10 (`project-phase-store`) in `reports/phase_state.json`.

Keys used: `{family}_{platform}_knowledge_ready`, `{family}_{platform}_site_plan_done`,
`{family}_{platform}_products_done`, `{family}_{platform}_family_sync_done`,
`{family}_{platform}_blog_done`,
`{family}_{platform}_docs_done`, `{family}_{platform}_kb_done`,
`{family}_{platform}_products_faq_done`,
`{family}_{platform}_reference_done`, `{family}_{platform}_truth_audit_done`,
`{family}_{platform}_quality_done`

## Error Handling

- If any stage fails unexpectedly, save the last successful checkpoint and halt with instructions
- Do not skip failed stages — investigate and fix before resuming
- Stage 6 (truth audit) FAIL count > 0 is a hard stop; do not proceed to Stage 7 or 8
