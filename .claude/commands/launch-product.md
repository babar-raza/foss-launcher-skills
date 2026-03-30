# Launch Product — 5-Subdomain Full Documentation Launch

**Arguments**: $ARGUMENTS
**Expected format**: `{family} {platform}` — e.g. `3d java` or `slides python`

## Purpose

Orchestrate a full 5-subdomain documentation launch for a FOSS product: products, blog, docs,
kb, and reference pages. Uses `project-phase-store` (S-10) for checkpoint-based resume.

## Pre-conditions

- All Phase 0 skills must be fixed (P0-1 through P0-5) — HTML comment evidence violation fixed
- `no-downgrade-guard` skill must exist
- `new-products-page` skill must exist

## Stages

### STAGE 0 — Knowledge Bootstrap
**Command**: `/knowledge-bootstrap {family} {platform}`
**Checkpoint**: `knowledge_ready`

**On completion**:
- `KNOWLEDGE: STOP:partial` → halt and explain; do not proceed
- `KNOWLEDGE: REFRESHED` → halt: "Knowledge refreshed from upstream changes. Run `/knowledge-diff`
  to review what changed, then re-run `/launch-product {family} {platform}`."
- Any other status → continue to Stage 1

**Save checkpoint**: `python scripts/pipeline/project_phase_store.py set {family} {platform} knowledge_ready true`

---

### STAGE 0.5 — Site Plan

Run `/site-plan {family} {platform}` to generate a complete, evidence-bound manifest of all pages before any generation begins.

Check the output:
- If `SITE-PLAN STOP:` → halt and fix the reported issue
- If `launch_tier: placeholder` → first launch; continue
- Note the `output: reports/plans/{family}/{platform}/site_plan.yaml` path for use in subsequent stages

**Checkpoint**: `site_plan_done`

**Resume guard**: If resuming and `reports/plans/{family}/{platform}/site_plan.yaml` already exists, verify its `repo_sha` matches `knowledge/{family}/{platform}/merged/model.yaml` `repo_sha`. If match: skip. If mismatch: re-run `/site-plan {family} {platform}`.

**Save checkpoint**: `python scripts/pipeline/project_phase_store.py set {family} {platform} site_plan_done true`

---

### STAGE 1 — Products Page

Read products pages from `reports/plans/{family}/{platform}/site_plan.yaml`, section `sections.products.pages[]`.

Generate both:
1. Family `_index.md` (layout: family): `/new-products-page {family}`
2. Platform `_index.md` (layout: plugin): `/new-products-page {family} {platform} --layout plugin`

**Checkpoint**: `products_done`

**Skip condition**: file already exists AND passes audit (0 FAIL)

**Save checkpoint** when done.

---

### STAGE 2 — Blog Posts

Read blog post slugs from `reports/plans/{family}/{platform}/site_plan.yaml`, section `sections.blog.pages[]`. Generate each page whose `mandatory: true`. Also generate optional posts if `mandatory: false` and evidence supports it.

For each page entry in `sections.blog.pages[]`:
- Use `/new-blog-post {family} {platform} {slug}` for each entry

**Skip condition per slug**: directory `content/blog.aspose.org/{family}/{platform}/{slug}/`
already exists AND its `index.md` passes audit (0 FAIL)

**Checkpoint**: `blog_done`

---

### STAGE 3 — Documentation Pages

Read docs pages from `reports/plans/{family}/{platform}/site_plan.yaml`, section `sections.docs.pages[]`.

For each page entry:
- Generate using `/new-docs-page {family} {platform} {section}/{slug}`

**Skip condition**: file already exists AND passes audit

**Checkpoint**: `docs_done`

---

### STAGE 4 — KB Articles

Read KB pages from `reports/plans/{family}/{platform}/site_plan.yaml`, section `sections.kb.pages[]`.

1. Generate FAQ: `/new-kb-faq {family} {platform}`
2. For each how-to page in the plan: `/new-kb-howto {family} {platform} {slug}`

**Skip condition**: files already exist AND pass audit

**Checkpoint**: `kb_done`

---

### STAGE 5 — Reference Pages (Batch)
**Command**: `/batch-reference {family} {platform}`

Idempotent — skips existing pages automatically. No skip-condition check needed.

**Checkpoint**: `reference_done`

---

### STAGE 6 — Truth Audit
**Command**: `/truth-audit {family} {platform}`
**Checkpoint**: `truth_audit_done`

**On FAIL findings**: Print the full list. **Do NOT auto-fix.** Require human review or
healing agent to resolve before marking this checkpoint complete. Do not proceed to Stage 7
until FAIL count is 0.

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
Blog posts:      {A/B/C/D/F per post}
Docs pages:      {grade summary}
KB articles:     {grade summary}
Reference pages: {grade summary} ({N} pages)

A: N  B: N  C: N  D: N  F: N

READY TO SHIP if: 0 D/F pages AND products + getting-started + first blog post at B+
```

**Print**: `READY TO SHIP` or `NOT READY` with a bullet list of blocking items.

---

## Resume Behavior

On re-run, read checkpoint state:
```bash
python scripts/pipeline/project_phase_store.py get {family} {platform}
```
Skip completed stages. Print: `Resuming {family}/{platform} from stage N (checkpoint: {name})`

## Checkpoint Storage

Checkpoints are stored via S-10 (`project-phase-store`) in `reports/phase_state.json`.

Record key: `{family}/{platform}` (created automatically by the CLI from positional args).

Value keys stored under each record: `knowledge_ready`, `products_done`,
`blog_done`, `docs_done`, `kb_done`,
`reference_done`, `truth_audit_done`, `quality_done`

Example: `python scripts/pipeline/project_phase_store.py set email net knowledge_ready true`
stores `knowledge_ready=true` under record key `email/net`.

## Error Handling

- If any stage fails unexpectedly, save the last successful checkpoint and halt with instructions
- Do not skip failed stages — investigate and fix before resuming
- Stage 6 (truth audit) FAIL count > 0 is a hard stop; do not proceed to Stage 7 or 8
