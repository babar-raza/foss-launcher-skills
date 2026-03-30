---
name: site-plan
description: >
  Produce a complete, evidence-bound manifest of all pages a product needs across all 5 subdomains
args: "{family} {platform} [--mode launch|update|section] [--section products|docs|blog|kb|reference] [--dry-run]"
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# S-47: Site Plan — Production-Grade Pre-Generation Site Manifest

**Arguments**: $ARGUMENTS
**Expected format**: `{family} {platform} [--mode launch|update|section] [--section products|docs|blog|kb|reference] [--dry-run]` — e.g. `3d python` or `slides java --mode update`

## Purpose

Produce `reports/plans/{family}/{platform}/site_plan.yaml` — a deterministic, evidence-bound manifest of all pages a product needs across all 5 subdomains. This manifest is consumed by `launch-product`, `new-blog-post`, `new-docs-page`, `new-kb-howto`, `new-products-page`, and `gap-eval`.

Pages for which the repo provides insufficient evidence must not appear in the plan. Every planned page must be justified by repo knowledge.

## Pre-conditions

1. Run `/knowledge-bootstrap {family} {platform}` first:
   - `STOP:partial` → halt (see printed message)
   - `REFRESHED` → STOP: "Knowledge was refreshed from upstream changes. Review `/knowledge-diff`, then re-run."
   - `READY`, `BOOTSTRAPPED`, or `WARN:conflicts` → continue
2. `knowledge/{family}/{platform}/merged/` must contain: `claims.json`, `api_surface.json`, `formats.json`, `limitations.md`, `model.yaml`
3. Clone cache at `runs/.clone_cache/aspose_{family}_{platform}/` must exist (for license file detection)
4. If `model.yaml.stale_since != null` → HARD STOP. Run `S-12 → S-14` first.

## Steps

### Step 1: Parse arguments

Extract `{family}`, `{platform}`, optional `--mode` (default: `launch`), optional `--section`, optional `--dry-run`.

### Step 2: Staleness gate

Read `knowledge/{family}/{platform}/merged/model.yaml`. If `stale_since` is not null, print:

```
SITE-PLAN STOP: Knowledge is stale since {stale_since}. Run /knowledge-update {family} {platform} first.
```

Halt immediately.

### Step 3: Load knowledge artifacts

- `claims.json` — capability evidence
- `api_surface.json` — public API surface
- `index.json` — class_count, snippet_count, forbidden_claims, api_confidence
- `limitations.md` — topics that MUST NOT be documented
- `formats.json` — format support
- `model.yaml` — version, repo_sha

### Step 4: Detect launch_tier

Determine tier by inspecting existing content with `knowledge_core.discover_content()` logic:

- `full` — products AND docs AND kb AND blog AND reference all have content
- `partial` — products exists but one or more other sections are missing
- `placeholder` — no docs/kb/blog/reference content exists

### Step 5: Run capability cluster detection

```bash
python scripts/pipeline/site_planner.py {family} {platform} --detect-clusters
```

Output is a JSON cluster list. Each cluster has:
- `name` — human-readable cluster name
- `slug` — URL-safe identifier
- `claim_count` — number of evidence claims
- `api_method_count` — number of API methods in surface
- `snippet_count` — number of code snippets
- `in_limitations` — boolean: topic forbidden by limitations.md
- `verb` — KB verb (e.g. `convert`, `load`, `build`)
- `slug_convention` — `noun-form` or `working-with-noun`

### Step 6: Apply evidence threshold rules

Apply per-section rules to determine which pages are justified.

**Products section** (always mandatory):
- `_index.md` (layout: `family`) — always
- `{platform}/_index.md` (layout: `plugin`) — always when platform is part of a full or partial launch

**Blog section** (conditional):
- Justified if `claim_count >= 200 AND snippet_count >= 10`
- If justified: `introducing-{family}-foss-{platform}/index.md` — always
- If justified: `{family}-key-features-{platform}/index.md` — always
- Optional 3rd post: if `claim_count >= 500 AND top_cluster.claim_count >= 20 AND top_cluster.snippet_count >= 3`

**Docs section** (always mandatory):
- `getting-started/_index.md` — always (`page_role`: `howto_article` if 1–2 children, `toc` if 3+)
- `getting-started/installation.md` — always
- `getting-started/license.md` — ONLY if a license file is found in clone cache. Check for: `LICENSE`, `LICENSE.txt`, `LICENSE.md`, `COPYING`, `COPYING.txt`. Record exact path as `evidence_source`. Do NOT gate on class_count or claim_count.
- `developer-guide/_index.md` — always (`page_role`: `howto_article` or `toc`)
- `developer-guide/features.md` — always (FIXED mandatory; not cluster-derived)
- `developer-guide/{topic}.md` — one per cluster with `claim_count >= 5 AND snippet_count >= 1 AND not in_limitations`. Slug convention is family-specific (see Step 5 output).

**KB section** (always mandatory, except placeholder tier):
- `faq.md` — always (weight: 1)
- `how-to-{verb}-{noun}-{platform}.md` — one per top cluster (max 5) with `claim_count >= 3 AND api_method_count >= 1 AND not in_limitations`. Verb from cluster detection. Platform suffix: `-python`, `-java`, `-dotnet`, `-cpp`, `-typescript`.
- `troubleshooting.md` — if `howto_count >= 6 AND platform in {typescript, python, cpp}` (weight: 2)
- `use-cases.md` — if `claim_count >= 500 AND snippet_count >= 20` (weight: 10)

**Reference section** (always mandatory):
- `_index.md` (layout: `reference-home`) — always
- All classes/enums from `api_surface.json` — via batch-reference strategy

### Step 7: Write or print plan

If `--dry-run`: print the plan to stdout in YAML format. Do not write any file.

Otherwise, write to `reports/plans/{family}/{platform}/site_plan.yaml`.

If `--mode update`: compare against the existing plan, produce a delta with three keys: `pages_to_add`, `pages_to_update`, `pages_to_remove`.

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
- All planned pages are evidence-justified (claim/snippet thresholds met)
- No pages planned for topics listed in `limitations.md`
- `license.md` planned only if license file found in clone cache; exact `evidence_source` recorded
- `features.md` always planned (not cluster-derived)
- Products section always includes both family `_index.md` AND platform `_index.md` (layout: `plugin`)
- Reference section always includes `_index.md` (layout: `reference-home`) plus `candidate_count`

## Output Schema: site_plan.yaml

```yaml
plan:
  family: {family}
  platform: {platform}
  version: "{version}"
  repo_sha: "{sha}"
  generated_at: "{iso8601}"
  mode: launch|update
  knowledge_confidence: high|medium|low
  launch_tier: placeholder|partial|full

  sections:
    products:
      mandatory: true
      pages:
        - slug: _index
          path: content/products.aspose.org/en/{family}/_index.md
          layout: family
          title: "Aspose.{Family} FOSS"
          mandatory: true
        - slug: {platform}/_index
          path: content/products.aspose.org/en/{family}/{platform}/_index.md
          layout: plugin
          plugin_platform: {Platform}
          title: "Aspose.{Family} FOSS for {Platform}"
          mandatory: true

    blog:
      mandatory: false
      justified: true|false
      justification: "{reason}"
      pages:
        - slug: introducing-{family}-foss-{platform}
          path: content/blog.aspose.org/{family}/{platform}/introducing-{family}-foss-{platform}/index.md
          mandatory: true

    docs:
      mandatory: true
      pages:
        - slug: getting-started/installation
          type: docs
          page_role: howto_article
          weight: 11
          mandatory: true
        - slug: getting-started/license
          type: docs
          page_role: howto_article
          weight: 15
          mandatory: false
          condition: "license_file_found_in_repo == true"
          evidence_source: "{clone_cache_path}/LICENSE"
        - slug: developer-guide/features
          type: docs
          page_role: howto_article
          weight: 10
          mandatory: true
          note: "Fixed mandatory page covering all capabilities"
        - slug: developer-guide/{topic}
          type: docs
          page_role: howto_article
          weight: {20,30,...}
          mandatory: true
          capability_cluster: "{cluster_name}"
          slug_convention: "noun-form|working-with-noun"
          evidence_claims: [CLM-xxx, ...]

    kb:
      mandatory: true
      pages:
        - slug: faq
          type: topic
          weight: 1
          mandatory: true
        - slug: how-to-{verb}-{noun}-{platform}
          type: topic
          weight: {10,20,...}
          required_shortcode: "steps"
          capability_cluster: "{cluster_name}"
          verb: {verb}
          mandatory: true
        - slug: troubleshooting
          type: topic
          weight: 2
          mandatory: false
          condition: "howto_count >= 6 AND platform in {typescript, python, cpp}"
        - slug: use-cases
          type: topic
          weight: 10
          mandatory: false
          condition: "claim_count >= 500 AND snippet_count >= 20"

    reference:
      mandatory: true
      pages:
        - slug: _index
          layout: reference-home
          type: reference_home
          mandatory: true
      strategy: batch-reference
      candidate_count: {N}

  excluded_topics:
    - topic: "{topic}"
      reason: "{below threshold|in limitations.md}"
```

## Error Handling

| Condition | Action |
|-----------|--------|
| `claims.json` missing | STOP: "Run /knowledge-bootstrap {family} {platform} first" |
| Clone cache missing | WARN: "License detection unavailable — clone cache not found at runs/.clone_cache/aspose_{family}_{platform}/. Proceeding without license.md." |
| `api_surface.json` has 0 classes | WARN: "Reference section may be empty — api_surface.json has no classes" |
| All clusters below threshold | INFO: "No developer-guide topics meet evidence threshold. Only features.md will be planned." |

## Integration Points

- **`/launch-product {family} {platform}`**: Add Stage 0.5 — run `/site-plan {family} {platform}`. Stages 2, 3, 4 consume `site_plan.yaml` instead of hardcoded slugs.
- **`/new-blog-post`, `/new-docs-page`, `/new-kb-howto`, `/new-products-page`**: Check if `site_plan.yaml` exists; warn if the requested slug is not in the plan.
- **`/gap-eval {family} {platform}`**: Use `site_plan.yaml` as expected page set if present; fall back to `profiles/*.yaml`.
- **`/knowledge-update {family} {platform}`**: After re-bootstrap, run `/site-plan {family} {platform} --mode update` to detect delta.
