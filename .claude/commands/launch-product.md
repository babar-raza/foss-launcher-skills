<!-- CONTRACT: agent-executed
     purpose: orchestrate 5-subdomain full documentation launch (products, blog, docs, kb, reference)
     preconditions: knowledge bootstrapped; clone cache populated
     postcondition: all 5 subdomains populated, graded, readiness scorecard produced,
                    blog index published, websites.aspose.org products sync run
     idempotent: yes — checkpoint-based resume skips completed stages
     verified: 2026-08-29 (TC-MT040-23: TypeScript platform notes, blog-index step,
               S-69/S-70 backlink caveat, websites-sync stage, 16-gate reference)
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
**Command**: `/knowledge-bootstrap {family} {platform}` (agent-executed per `skills/knowledge-bootstrap.md`
— that skill's own `.claude/commands/` mirror is deliberately absent, exempted via
`scripts/pipeline/lib/_skill_constants.py`'s `INTERNAL_SKILLS`; do not create one).
**Checkpoint**: `knowledge_ready`

**On completion**:
- `KNOWLEDGE: STOP:partial` → halt and explain; do not proceed
- `KNOWLEDGE: REFRESHED` → halt: "Knowledge refreshed from upstream changes. Run `/knowledge-diff`
  to review what changed, then re-run `/launch-product {family} {platform}`."
- Any other status → continue to Stage 0.5

**TypeScript completeness gate** (TC-MT040-22, `platform in {typescript, javascript, nodejs}` only):
```bash
.venv/Scripts/python scripts/pipeline/commands/diagnostics/typescript_api_completeness.py {family} {platform}
```
Exit 1 ⇒ treat as `KNOWLEDGE: STOP:partial` — the scout has missing/inconsistent barrel-exported
declarations (`barrel_exports_missing_from_api_surface` or `exported_but_marked_unreachable` in
the printed report). Also verify `knowledge/{family}/{platform}/scout/scout_report.json`'s
`ts_entry_point` field is non-empty (the package's barrel/entry point resolved). An empty value is
**not** a failure by itself — it means this product's reachability signal is `Unknown` (fail-safe;
see `platform_capabilities.yaml`'s `typescript.reachability_adapter` note) — but record it in the
launch evidence so a reviewer knows every class on this product will render, including any that
would otherwise be filtered as unreachable elsewhere.

**Save checkpoint**: `python scripts/pipeline/commands/ops/project_phase_store.py set {family} {platform} knowledge_ready true`

**Compile/import smoke (TC-PSD-HRD-02, net/python only):** tree-sitter's parser is lenient and
never fails on source that doesn't actually compile (a real upstream repo has been found holding
320 real compile errors invisible to extraction). `scripts/pipeline/commands/launch/
compile_smoke.py {platform} {clone_path} --json` runs a real `dotnet build` (net) or isolated-mode
`import` (python) against the product's own clone and PASS/FAIL/WARNs honestly; every other
platform returns `NOT_RUN` (not yet built). This is **not currently invoked automatically by any
stage above** — `upstream_readiness_check.py`'s own `U-07` placeholder still reports `NOT_RUN`
regardless of this module's real result (wiring the dispatch is a future card, same disclosed-scope
pattern as `U-01`'s own Stage -1 module). Run it by hand for a net/python launch before trusting a
scout's API surface.

**Source-install fallback mode (TC-PSD-HRD-10, permanent fix of F-PSD-07):** the unpublished-
package install block (`foss-source-install.html`, called from `package-install`/
`package-install-inline`/`maven-coord`/`maven-gav`) reads a per-product `source_install_mode`
field in `data/products.json`, decided by `scripts/pipeline/lib/source_install.py::
determine_source_install_mode(platform, repo)`: `"standard"` (absent/default; today's
unconditional per-platform instructions, used by every product except the one named below) or,
**python-only**, `"pythonpath"` (no packaging manifest exists at all, so an editable install
cannot work; the package renders clone + run-from-folder-or-PYTHONPATH instructions instead —
psd/python's own case). A `net` product's mode is also computed (reused by
`upstream_readiness_check.py`'s U-04 preflight check) but every net product today resolves
`"standard"`; the field only ever changes the RENDERED python branch. Run `enrich_products_
source_install_mode.py --dry-run` after cloning a new unpublished product to see its real mode
before assuming the default is correct.

---

### Platform notes — TypeScript/npm

- **Install command**: always the `{{< package-install "{family}" "{platform}" >}}` shortcode,
  never a literal `npm install ...` line — it reads `data/package_registry.json` (the entry MUST
  exist before any page referencing it is generated; see Phase D of the launch, or
  `scripts/pipeline/lib/product_registry.py::get_package_name()` for the resolution order:
  registry candidate name when published → `naming_convention_candidate()` guess → `None`).
  For an unpublished package the shortcode renders a "not yet published — build from source"
  notice; never write `npm install {package}` as prose.
- **Frontmatter**: `plugin_platform: TypeScript`, and `linkTitle: TypeScript` on all four
  platform-level `_index.md` files (products/docs/kb/reference) — gate **L-16** enforces this.
- **Reference page kinds**: `abstract_class_declaration` (TC-MT040-10), interfaces, and
  type-alias declarations all render; interface/type-alias entries do not force `class_kind`
  page-count penalties in the coverage evaluator (`CONCRETE_ONLY_PLATFORMS`, TC-MT040-22).
  FR-14 accessor properties render as ordinary properties.
- **Unreachable classes get no page, by design** — a class never re-exported through the
  package's resolved barrel/entry point (`REACHABILITY_ENFORCED_PLATFORMS`, TC-MT040-17) is
  silently skipped from the grouped reference index, matching the PY-SHIM discard precedent.
  Do not hand-add a page for a class you notice missing without first checking whether it's
  genuinely unreachable (`compute_barrel_completeness()`'s `exported_but_marked_unreachable`
  field distinguishes "genuinely internal" from "a scout inconsistency").
- **Reference grouping**: `_derive_group_key()` reads a knowledge-layer `module_key`/
  `module_label` (written by `promote.py`, TC-MT040-43/D-4) when present, falling back to
  directory-path derivation for older knowledge. For a flat `src/` layout (no subdirectories —
  common for smaller TS packages) this uses a family-agnostic stem-keyword table
  (forms/annotations/compliance/conversion/images/text/structure/security/navigation/tables/
  attachments/redaction, `core` as the fallback) rather than collapsing everything into one
  "Core API" group.
- **Snippets are examples-first**: the tiered budget (Tier 0 README ≤10 → Tier 1
  `examples/`/`samples/` ≤60 → Tier 2 tests, remainder to 100; TC-MT040-44/16) is enabled for
  `typescript`/`javascript` specifically — leaf-only `it()`/`describe()` blocks, non-test files
  under a `test`/`tests` dir contribute nothing, `docs/**/*.md` fences are never harvested.
- **Import form**: `import { X } from "{package}"` per `merged/install.md`'s `canonical_import`
  field, not a bare require/CommonJS form.

---

### Platform notes — .NET/NuGet

- **Install command**: always the `{{< package-install "{family}" "{platform}" >}}` shortcode,
  never a literal `dotnet add package ...` line — same resolution-order rule as the TypeScript/
  npm section above (registry candidate name when published → `naming_convention_candidate()`
  guess → `None`; unpublished renders a "not yet published — build from source" notice).
- **Known extraction gap — NET-OPERATOR-OVERLOAD-001** (`backlog/BACKLOG.md`;
  `platform_capabilities.yaml`'s own `net.declared_ignored_kinds` entries for
  `operator_declaration`/`conversion_operator_declaration`/`delegate_declaration`/
  `event_field_declaration`/`indexer_declaration` document this as a real, unfixed,
  portfolio-wide gap): public `operator ==`/`operator !=`/conversion operators, delegates,
  events, and indexers on a .NET product's public types are invisible to extraction and will
  not appear in generated reference pages or claims. Confirmed live on psd/net (TC-PSD-HRD-07):
  8 real public operator overloads (`Point`, `Rectangle`, `RectangleF`, `Size`, two each) exist
  in the upstream source and 0 appear in `knowledge/psd/net/merged/api_surface.json`. This is a
  content-governance disclosure, not a fix — the extraction gap itself stays out of scope for
  any launch-product run (fixing `tree_helpers.py`/`api_surface.py` is a separate, future card).
  A reviewer or content author should not be surprised that a value type's equality operators
  are absent from its reference page; it is a known, already-filed gap, not a scout regression.

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

**Condition**: Always run after Stage 1 completes, unless checkpoint `family_sync_done` is already `true`.

**Pre-flight — placeholder check**: Before running, inspect
`content/products.aspose.org/en/{family}/_index.md` for "coming soon" text.
If the string `coming soon` appears (case-insensitive), the family page has a stale
placeholder that must be replaced regardless of how many platform subdirectories exist.

**Platform count note**: Even when only 1 platform subdirectory exists (first-family launch),
run `/family-sync {family}`. The family page may contain a pre-existing "coming soon"
placeholder that predates the launch and must be overwritten.

**Command**: `/family-sync {family}`

**Checkpoint**: `family_sync_done`

**Skip condition**: Checkpoint `family_sync_done` is already `true` AND no "coming soon"
text is present in `content/products.aspose.org/en/{family}/_index.md`.

**Gate**: Gate L-10 in `launch_gate.py` enforces this as a machine check — if "coming soon"
remains in the family `_index.md` after Stage 1, the launch gate FAILS and blocks Stage 8
readiness sign-off. Running `/family-sync {family}` replaces the placeholder with
auto-generated content and clears the L-10 gate.

**Save checkpoint**: `python scripts/pipeline/commands/ops/project_phase_store.py set {family} {platform} family_sync_done true`

---

### STAGE 2 — Blog Posts
**Pre-condition**: Verify `reports/plans/{family}/{platform}/site_plan.yaml` exists.
If missing, STOP and re-run Stage 0.5.

**Step 0 — Blog index** (must run before any post — without it Hugo 404s the section route):
```
/new-blog-index {family} {platform}
```
**Checkpoint**: `blog_index_done` — set with `--artifact content/blog.aspose.org/{family}/{platform}/_index.md`
(HARDEN-A6 fingerprinting; see Resume Behavior). Skip only if this checkpoint verifies AND the
file exists.

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
   - `/new-docs-page {family} {platform} getting-started installation` — **for `platform: java`**,
     this page's install section must be the `maven-coord` shortcode, never a literal
     `<groupId>`/coordinate (new-docs-page.md's own instructions enforce this; noted here because
     this is historically the single most-affected page type — see Mission MT008,
     `plans/master-plan.md`, the `docs.aspose.org/.../getting-started/installation.md`
     self-contradiction example in Finding F-01).
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

**Backlink caveat** (PDFPY-SKILLGAP-001): S-69/S-70/S-71's own generation of these
section-home `_index.md` pages does not run a backlink pass on them — Stage 8's
`backlink_audit.py`/`backlink_backfill.py` invocation covers per-class and per-post
pages, but section-home pages created in this stage are a separate population. After
this stage's verification passes, run:
```bash
.venv/Scripts/python scripts/pipeline/commands/ops/backlink_backfill.py --write \n  --family {family} --platform {platform}
```
then re-run `backlink_audit.py` for the same family/platform before Stage 8's own
audit — this catches a missing/anchor-non-compliant backlink on a section-home page
before it reaches Stage 8's readiness gate.

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

**Backlink compliance check** (before printing readiness verdict):
```bash
.venv/Scripts/python scripts/pipeline/commands/ops/backlink_audit.py \n  --family {family} --platform {platform}
```
For any MISSING pages, re-inject before shipping:
```bash
.venv/Scripts/python scripts/pipeline/commands/ops/backlink_backfill.py \n  --family {family} --platform {platform} --write
```
If BLOCKED_TARGET: log WARN — do not block ship decision on BLOCKED_TARGET.
    **Anchor policy v2**: platform targets → `Aspose.{Family} for {Platform} Enterprise Product`; family targets → `Aspose.{Family} Enterprise Product Family` (governed by `docs/governance/positioning-policy.md`).

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
> per §7c and §7a (full detail: [docs/_archive/pre-refactor/governance/launch-gates.md](../docs/_archive/pre-refactor/governance/launch-gates.md) — moved from `docs/governance/` per AGENTS.md §7a/§10, the link was stale before this update). The agent performs all 5 gate equivalents. Real human escalation only
> per §7c conditions (see AGENTS.md §7c).
>
> The prior stage's `launch_gate.py` runs 16 <!-- pin: launch_gate.len(_ALL_GATES) -->
> automated gates, L-01 through L-16 — not 15; the module's own docstring undercounted
> L-12 through L-15 (denominator reconciliation, cross-subdomain build, grade
> non-regression, snippet syntax) until this update. Of particular note for a new
> launch: **L-10** (no "coming soon" placeholder — Stage 1.5 clears it), **L-11**
> (canonical family display name), **L-12** (generation-manifest denominator gap must
> be 0 — a real page/claim must exist for everything the site plan counted), and
> **L-16** (platform `linkTitle` must exactly match `data/platforms.json` —
> TypeScript's canonical value is `TypeScript`) are the four gates most likely to trip
> on a first-time platform launch; the other twelve are steady-state regressions the
> earlier stages already guard against.

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

### STAGE 8.6 — websites.aspose.org Products Sync

**Purpose**: `websites.aspose.org`'s own `products:` block (English + all 36 locale copies of
`content/websites.aspose.org/.../aspose/org/_index.md`) is generated independently from
`data/products.json`/`data/families.json`/ordering data + a live check that this launch's
products page actually exists, has `layout: plugin`, and is not `draft: true` — it is **not**
regenerated automatically by any earlier stage. Missed once (MT012); shipped as an extra,
separate commit on MT013's launch (`f480548ac0`) rather than being part of the launch skill
itself. This stage exists so it is never missed again.

**Pre-condition**: Stage 1 (`products_done`) and Stage 1.5 (`family_sync_done`) must be
`true` — this stage's own live check will otherwise correctly find the platform not yet
published and skip it, silently producing a no-op sync.

**Requires an override token** (`websites.aspose.org` content is outside this launch's normal
per-family write scope):
```bash
.venv/Scripts/python scripts/pipeline/commands/governance/override_manager.py create \n  --paths "content/websites.aspose.org/**" --reason "{family}/{platform} launch Stage 8.6" \n  --plan "<this launch's plan/mission reference>"
```

**Command**:
```bash
.venv/Scripts/python scripts/pipeline/commands/websites/sync_domain_products.py --write
```
Run without `--domain` (syncs all locales) unless explicitly scoped. Dry-run first
(`--dry-run` in place of `--write`) to review the diff before writing.

**Checkpoint**: `websites_sync_done`

**Skip condition**: checkpoint already `true` AND a `--dry-run` re-run shows no diff for this
family/platform's entry.

---

## Resume Behavior

On re-run, read checkpoint state:
```bash
.venv/Scripts/python scripts/pipeline/commands/ops/project_phase_store.py get {family} {platform}
```

**Before trusting a `true` checkpoint to skip its stage (HARDEN-A5, 2026-07-22):**
a boolean alone does not prove the artifact it certifies still matches disk — it
could have been corrupted, reverted, or hand-edited since the checkpoint was set.
If the checkpoint was set with `--artifact <path>` (fingerprinted), verify it first:
```bash
.venv/Scripts/python scripts/pipeline/commands/ops/project_phase_store.py verify {family} {platform} {checkpoint_key}
```
Exit 0 = fingerprint matches (or the entry is legacy/unfingerprinted — "unverifiable,"
never blocking). Exit 1 = the artifact genuinely changed since certification — do NOT
skip the stage; treat the checkpoint as stale and re-run it. When setting a checkpoint
for a stage that produces a specific, checkable artifact (e.g. `site_plan_done` →
`reports/plans/{family}/{platform}/site_plan.yaml`), pass `--artifact <path>` so future
resumes get this real verification instead of trusting the bare boolean.

Skip completed stages only after this check passes. Print:
`Resuming {family}/{platform} from stage N (checkpoint: {name})`

## Checkpoint Storage

Checkpoints are stored via S-10 (`project-phase-store`) in `reports/phase_state.json`.

Keys used: `{family}_{platform}_knowledge_ready`, `{family}_{platform}_site_plan_done`,
`{family}_{platform}_products_done`, `{family}_{platform}_family_sync_done`,
`{family}_{platform}_blog_index_done`, `{family}_{platform}_blog_done`,
`{family}_{platform}_docs_done`, `{family}_{platform}_kb_done`,
`{family}_{platform}_products_faq_done`,
`{family}_{platform}_reference_done`, `{family}_{platform}_family_indexes_verified`,
`{family}_{platform}_truth_audit_done`,
`{family}_{platform}_quality_done`, `{family}_{platform}_readiness_done`,
`{family}_{platform}_websites_sync_done`

## Error Handling

- If any stage fails unexpectedly, save the last successful checkpoint and halt with instructions
- Do not skip failed stages — investigate and fix before resuming
- Stage 6 (truth audit) FAIL count > 0 is a hard stop; do not proceed to Stage 7 or 8

---

## LLM Metrics Obligation

If this skill invokes `llm.professionalize.com` directly or through `LLMRouter`,
the run carries a **metrics obligation** (METRICS-PLAN-001, `AGENTS.md §15`):

- All professionalize calls must use `ProfessionalizeClient`, `LLMRouter`, or a
  registered adapter entry in `metrics_callsite_registry.yaml`.
- Each run must capture per-call `MetricsEvent` records and aggregate them into a
  validated `MetricsRow` via `RunMetrics`.
- Default mode is **dry-run**. Live posting requires explicit owner approval and
  `AGENT_METRICS_ENDPOINT` / `AGENT_METRICS_TOKEN` set locally.
- Non-professionalize calls (Gemini, Ollama, M2M) are excluded from
  `token_usage` and `api_calls_count`.
- Metrics failures must not crash or block the parent pipeline job.
