---
name: site-plan
description: >
  Produce a complete, evidence-bound manifest of all pages a product needs across all 5 subdomains
args: "{family} {platform} [--mode launch|update|section] [--section products|docs|blog|kb|reference] [--dry-run]"
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# S-47: Site Plan — Production-Grade Pre-Generation Site Manifest

**Arguments**: $ARGUMENTS
**Expected format**: `{family} {platform} [--mode launch|update|section] [--section products|docs|blog|kb|reference] [--dry-run]`

## Purpose

Produce `reports/plans/{family}/{platform}/site_plan.yaml` — a deterministic, evidence-bound manifest of all pages a product needs across all 5 subdomains. Consumed by `launch-product`, `new-blog-post`, `new-docs-page`, `new-kb-howto`, `new-products-page`, and `gap-eval`.

## Pre-conditions

1. Run `/knowledge-bootstrap {family} {platform}` first — halt on `STOP:partial`; halt and review on `REFRESHED`
2. `knowledge/{family}/{platform}/merged/` must have: `claims.json`, `api_surface.json`, `formats.json`, `limitations.md`, `model.yaml`
3. If `model.yaml.stale_since != null` → HARD STOP. Run `S-12 → S-14` first.

## Steps

### Step 1: Parse arguments
Extract `{family}`, `{platform}`, `--mode` (default: `launch`), `--section`, `--dry-run`.

### Step 2: Staleness gate
If `model.yaml.stale_since != null`, print `SITE-PLAN STOP: Knowledge is stale since {stale_since}. Run /knowledge-update {family} {platform} first.` and halt.

### Step 3: Load knowledge
Load `claims.json`, `api_surface.json`, `index.json`, `limitations.md`, `formats.json`, `model.yaml`.

### Step 4: Detect launch_tier
- `full` — all 5 sections have existing content
- `partial` — products exists but one or more sections missing
- `placeholder` — no docs/kb/blog/reference content

### Step 5: Detect capability clusters
```bash
.venv/Scripts/python scripts/pipeline/site_planner.py {family} {platform} --detect-clusters
```
Each cluster: `name`, `slug`, `claim_count`, `api_method_count`, `snippet_count`, `in_limitations`, `verb`, `slug_convention`.

### Step 6: Apply evidence thresholds per section

**Products** (always mandatory): family `_index.md` (layout: `family`) + `{platform}/_index.md` (layout: `plugin`).

**Blog** (justified if `claim_count >= 200 AND snippet_count >= 10`): `introducing-{family}-foss-{platform}` + `{family}-key-features-{platform}`. Optional 3rd post if `claim_count >= 500 AND top_cluster.claim_count >= 20 AND top_cluster.snippet_count >= 3`.

**Docs** (always mandatory):
- `getting-started/installation.md` — always
- `getting-started/license.md` — ONLY if license file found in clone cache (`LICENSE`, `LICENSE.txt`, `LICENSE.md`, `COPYING`, `COPYING.txt`); record `evidence_source`
- `developer-guide/features.md` — always (FIXED mandatory; not cluster-derived)
- `developer-guide/{topic}.md` — one per cluster with `claim_count >= 5 AND snippet_count >= 1 AND not in_limitations`

**KB** (mandatory except placeholder tier):
- `faq.md` — always
- `how-to-{verb}-{noun}-{platform}.md` — one per top cluster (max 5) with `claim_count >= 3 AND api_method_count >= 1 AND not in_limitations`
- `troubleshooting.md` — if `howto_count >= 6 AND platform in {typescript, python, cpp}`
- `use-cases.md` — if `claim_count >= 500 AND snippet_count >= 20`

**Reference** (always mandatory): `_index.md` (layout: `reference-home`) + all classes/enums from `api_surface.json` via batch-reference.

### Step 7: Write or print plan
- `--dry-run`: print YAML to stdout only
- Otherwise: write `reports/plans/{family}/{platform}/site_plan.yaml`
- `--mode update`: produce delta (`pages_to_add`, `pages_to_update`, `pages_to_remove`)

### Step 8: Print summary
```
SITE-PLAN: {family}/{platform} [{mode}]
  launch_tier: {tier}
  products: {N} pages
  blog: {N} pages ({justified|not justified})
  docs: {N} pages
  kb: {N} pages
  reference: {N} classes + 1 home
  excluded_topics: {N} (reason: below threshold or in limitations.md)
  output: reports/plans/{family}/{platform}/site_plan.yaml
```

## Post-conditions

- `reports/plans/{family}/{platform}/site_plan.yaml` written (or printed if `--dry-run`)
- All planned pages evidence-justified; no pages for topics in `limitations.md`
- `license.md` planned only if license file found in clone cache; `evidence_source` recorded
- `features.md` always planned (not cluster-derived)
- Products section always includes family `_index.md` AND platform `_index.md` (layout: `plugin`)

## Error Handling

- No `claims.json` → STOP: "Run /knowledge-bootstrap {family} {platform} first"
- Clone cache missing → WARN and proceed without `license.md`
- `api_surface.json` has 0 classes → WARN: "Reference section may be empty"
- All clusters below threshold → INFO: "No developer-guide topics meet threshold. Only features.md will be planned."
