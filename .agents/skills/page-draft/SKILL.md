---
name: page-draft
id: S-19
description: >
  Draft initial page content following the structure plan from S-18. Delegates
  to the appropriate site-type template (new-docs-page, new-blog-post, etc.).
args: "{family} {platform} {site-type} {slug}"
---

# S-19: Page Draft — Initial Content Generation

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform} {site-type} {slug}`

> **Configuration**: Output paths are defaults for the aspose.org repo. See `config.yaml` for your project's path configuration.

## Purpose
Draft the initial page content following the structure plan from S-18 (page-plan). This skill delegates to the appropriate site-type-specific template for the actual content generation.

## Pre-conditions
1. S-18 structure plan should exist: `reports/plans/{family}-{platform}-{slug}-structure.yaml`
2. Knowledge model must exist and not be stale
3. Target file must not already exist (checked by S-10)

## Golden Corpus Pre-conditions

1. **Load corpus profile**: Read `knowledge/{family}/{platform}/_corpus/{site-type}_profile.json`
   - If not found → WARN and suggest running `/corpus-scan {family} {platform} {site-type}`; proceed with default template

2. **Load golden index**: Read `golden/_index.json`
   - If not found → WARN and suggest running `python scripts/golden_index.py`; proceed with default template

3. **Determine variant**: Read `selected_variant` from the corpus profile (e.g., "standard", "minimal", "steps")
   - If `richness_tier: C` → use "minimal" variant
   - If `richness_tier: A` or `B` → use "standard" variant
   - Pass the selected variant to the delegate skill (new-docs-page, new-kb-howto, etc.)

4. **Select golden page**: From `golden/_index.json`, find the page matching the target page_role and variant
   - Page role is determined by site-type: docs→`workflow_page`, blog→`feature_blog`, kb→`howto_article`, reference→`api_reference`

5. **Read the golden file**: Read the actual golden `.md` file at the `source_path` from the index entry
   - Pass golden structural contracts and style rubric context to the delegate skill

## Steps

1. **Read structure plan** from `reports/plans/{family}-{platform}-{slug}-structure.yaml`
   - If not found → WARN and proceed using default template (less targeted but functional)

2. **Load knowledge artifacts**: `index.json`, `claims.json`, `api_surface.json`, `formats.json`, `snippets/`

3. **Delegate to site-type template**: Based on `{site-type}`, invoke the corresponding content generation skill:
   - `docs` → Follow the **new-docs-page** skill template
     - Pass: `{family} {platform} {section} {slug}` (section from structure plan or default to `getting-started`)
   - `blog` → Follow the **new-blog-post** skill template
     - Pass: `{family} {platform} {slug}`
   - `kb` → Follow the **new-kb-howto** skill template (or **new-kb-faq** if slug is "faq")
     - Pass: `{family} {platform} {slug}`
   - `reference` → Follow the **new-reference-page** skill template
     - Pass: `{family} {platform} {slug}`

4. **Apply structure plan overrides**: If the structure plan specifies:
   - Specific claims per section → ensure those claims are covered
   - Specific snippets → use those code examples
   - Specific FAQ items → include those questions
   - Internal links → add to "See Also" or "Next Steps" sections

5. **Write draft** to the target content path (determined by site-type)

6. **Update plan status** to `drafted` in `reports/plans/{family}-{platform}-{slug}.yaml`

## Output

```
PAGE DRAFT — {family}/{platform}/{slug}
Site type: {site-type}
Template:  {template skill used}
Target:    {output file path}
Claims referenced: {count}
Code blocks: {count}
Status: DRAFTED

Next steps in chain:
  1. /faq-generate {content-file-path}  (S-22, if applicable)
  2. /ground-check {content-file-path}  (S-23)
  3. /evidence-cite {content-file-path}  (S-24)
  4. /path-guard {content-file-path}     (S-01)
```

## Error handling
- If structure plan missing → proceed with default template (warn user)
- If knowledge is stale → abort
- If target file exists → abort with "Use /page-update (S-20) instead"
- If site-type not recognized → list valid options and abort

## Relationship to new-* skills
The `new-blog-post`, `new-docs-page`, `new-kb-howto`, `new-kb-faq`, and `new-reference-page` skills are the site-type-specific templates that this skill delegates to. They can also be invoked directly as shortcuts when S-10/S-18/S-19 chain is not needed.
