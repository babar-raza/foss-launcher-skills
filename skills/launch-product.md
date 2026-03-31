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

### STAGE 1 — Products Page
**Command**: `/new-products-page {family} {platform}`
**Checkpoint**: `products_done`

**Skip condition**: `content/products.aspose.org/en/{family}/_index.md` already exists AND
passes `python scripts/pipeline/audit.py --files content/products.aspose.org/en/{family}/_index.md`
(0 FAIL)

**Save checkpoint** when done.

---

### STAGE 1.2 — Products Translation

**Purpose**: Ensure the products page exists in all served locales before the family sync
runs (family sync reads locale pages to compile the platform grid).

**Command**:
```bash
python -m translator page content/products.aspose.org/en/{family}/{platform}/_index.md --locales all
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
**Commands** (run sequentially):
1. `/new-blog-post {family} {platform} introducing-{family}-foss-{platform}`
2. `/new-blog-post {family} {platform} {family}-key-features-{platform}`

**Skip condition per slug**: directory `content/blog.aspose.org/{family}/{platform}/{slug}/`
already exists AND its `index.md` passes audit (0 FAIL)

**Checkpoint**: `blog_done`

---

### STAGE 3 — Documentation Pages
**Derive needed pages** from `knowledge/{family}/{platform}/merged/claims.json`:
- `getting-started/installation` — always generate if missing
- `getting-started/quickstart` — always generate if missing
- `developer-guide/{topic}` — one page per distinct capability cluster in claims

**Command per page**: `/new-docs-page {family} {platform} {section} {slug}`

**Skip condition**: file already exists AND passes audit

**Checkpoint**: `docs_done`

---

### STAGE 4 — KB Articles
**Commands**:
1. `/new-kb-faq {family} {platform}`
2. `/new-kb-howto {family} {platform} how-to-get-started-{family}-{platform}`

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
Products translations: {N}/{total_locales} locales present

READY TO SHIP if: 0 D/F pages AND products + getting-started + first blog post at B+ AND products translations >= 80% of declared locales
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

Keys used: `{family}_{platform}_knowledge_ready`, `{family}_{platform}_products_done`,
`{family}_{platform}_blog_done`, `{family}_{platform}_docs_done`, `{family}_{platform}_kb_done`,
`{family}_{platform}_reference_done`, `{family}_{platform}_truth_audit_done`,
`{family}_{platform}_quality_done`

## Error Handling

- If any stage fails unexpectedly, save the last successful checkpoint and halt with instructions
- Do not skip failed stages — investigate and fix before resuming
- Stage 6 (truth audit) FAIL count > 0 is a hard stop; do not proceed to Stage 7 or 8
