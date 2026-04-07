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

**Save checkpoint**: `python scripts/pipeline/project_phase_store.py set {family} {platform} knowledge_ready true`

---

### STAGE 0.5 — Site Plan
**Command**: `/site-plan {family} {platform}`
**Output**: `reports/plans/{family}/{platform}/site_plan.yaml`
**Checkpoint**: `site_plan_done`

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

**Save checkpoint**: `python scripts/pipeline/project_phase_store.py set {family} {platform} site_plan_done true`

---

### STAGE 1 — Products Page
**Command**: `/new-products-page {family} {platform}`
**Checkpoint**: `products_done`

**Skip condition**: `content/products.aspose.org/en/{family}/{platform}/_index.md` already exists AND
passes `python scripts/pipeline/audit.py --files content/products.aspose.org/en/{family}/{platform}/_index.md`
(0 FAIL)

**Save checkpoint** when done.

---

### STAGE 1.2 — Products Translation

**Purpose**: Ensure the products page exists in all served locales before the family sync
runs (family sync reads locale pages to compile the platform grid).

**Command**:
```bash
.venv/Scripts/python -m translator batch --family {family} --platform {platform} --site products.aspose.org
```

**Skip condition**: At least 80% of declared locales already have
`content/products.aspose.org/{locale}/{family}/{platform}/_index.md`. Check a representative
sample (ar, de, fr, zh) -- if all four are present, skip.

**Checkpoint**: `products_translation_done`

**On failure**: Log failed locales, continue -- translation failures are non-blocking for
the launch but must appear in the Stage 8 readiness scorecard.

**Save checkpoint**: `python scripts/pipeline/project_phase_store.py set {family} {platform} products_translation_done true`

---

### STAGE 1.5 — Family Page Sync

**Condition**: Run ONLY when >= 2 platform subdirectories exist under
`content/products.aspose.org/en/{family}/` after Stage 1 completes.

If only 1 platform subdirectory exists (first launch), skip — family page was just created fresh.

**Command**: `/family-sync {family}`

**Checkpoint**: `family_sync_done`

**Skip condition**: only 1 platform subdirectory exists under the family

**Save checkpoint**: `python scripts/pipeline/project_phase_store.py set {family} {platform} family_sync_done true`

---

### STAGE 2 — Blog Posts
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

### STAGE 6 — Truth Audit
**Command**: `/truth-audit {family} {platform}`
**Checkpoint**: `truth_audit_done`

**On FAIL findings**: Print the full list. **Do NOT auto-fix.** Require human review or
healing agent to resolve before marking this checkpoint complete. Do not proceed to Stage 6.5
or Stage 7 until FAIL count is 0.

---

### STAGE 6.5 — Full Translation (all subdomains)

**Purpose**: Translate all English content to all 36 locales after truth audit passes.
Products were already translated in Stage 1.2 — verify coverage only for products.

**Commands** (run each subdomain sequentially):
```bash
.venv/Scripts/python -m translator batch --family {family} --platform {platform} --site docs.aspose.org
.venv/Scripts/python -m translator batch --family {family} --platform {platform} --site kb.aspose.org
.venv/Scripts/python -m translator batch --family {family} --platform {platform} --site reference.aspose.org
.venv/Scripts/python -m translator batch --family {family} --platform {platform} --site blog.aspose.org
```

**Checkpoint**: `translation_done`

**On failure per locale**: Log and continue — translation failures are non-blocking for the
launch but must appear in the Stage 8 readiness scorecard with per-subdomain locale counts.

**On products**: verify coverage >= 80% from Stage 1.2; re-run only if coverage dropped below threshold.

**Save checkpoint**: `python scripts/pipeline/project_phase_store.py set {family} {platform} translation_done true`

---

### STAGE 7 — Quality Check + Auto-Fix
**Command**: `/batch-eval-fix {family} {platform}`
**Checkpoint**: `quality_done`

Auto-fixes deterministic issues only (no LLM pass). Reviews eval grades.

---

### STAGE 8 — Readiness Scorecard
Read `reports/content_eval/eval-latest.json` (or run fresh eval) for this product.

Print per-page grades with counts:
```
=== LAUNCH READINESS: {family}/{platform} ===
Products page:   {grade}
Blog posts:      {A/B/C/D/F per post} ({N} posts)
Docs pages:      {grade summary} ({N} pages)
KB articles:     {grade summary} ({N} pages)
Reference pages: {grade summary} ({N} pages)

A: N  B: N  C: N  D: N  F: N

Translation coverage:
  Products:   {N}/36 locales
  Docs:       {N}/36 locales
  KB:         {N}/36 locales
  Reference:  {N}/36 locales
  Blog:       {N}/36 locales
```

**Print**: `READY TO SHIP` or `NOT READY` with a bullet list of blocking items.

```
READY TO SHIP if:
  - 0 D/F pages
  - products + getting-started + first blog post at B+
  - ALL subdomain translations >= 70% of 36 locales (>= 26 locales each)
```

> **Grade calibration — reference pages**: Reference page grades reflect API surface accuracy
> (format_truth / format_completeness evaluators), not description depth. For FOSS repos that
> ship without XML docstrings, grade A on reference pages means "no format errors detected" —
> empty property/method description fields are expected and do not lower the grade. This is
> correct behaviour. Do NOT treat A-graded reference pages as evidence of prose quality;
> treat them as evidence of structural and API-accuracy compliance only.

---

## Resume Behavior

On re-run, read checkpoint state:
```bash
.venv/Scripts/python scripts/pipeline/project_phase_store.py get {family} {platform}
```
Skip completed stages. Print: `Resuming {family}/{platform} from stage N (checkpoint: {name})`

## Checkpoint Storage

Checkpoints are stored via S-10 (`project-phase-store`) in `reports/phase_state.json`.

Keys used: `{family}_{platform}_knowledge_ready`, `{family}_{platform}_site_plan_done`,
`{family}_{platform}_products_done`, `{family}_{platform}_products_translation_done`,
`{family}_{platform}_family_sync_done`, `{family}_{platform}_blog_done`,
`{family}_{platform}_docs_done`, `{family}_{platform}_kb_done`,
`{family}_{platform}_reference_done`, `{family}_{platform}_truth_audit_done`,
`{family}_{platform}_translation_done`, `{family}_{platform}_quality_done`

## Error Handling

- If any stage fails unexpectedly, save the last successful checkpoint and halt with instructions
- Do not skip failed stages — investigate and fix before resuming
- Stage 6 (truth audit) FAIL count > 0 is a hard stop; do not proceed to Stage 6.5, 7, or 8
