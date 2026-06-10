---
name: page-plan
id: S-18
description: >
  Plan the page structure for a new content page. Maps sections to claims,
  code blocks to snippets, and FAQ items to knowledge artifacts.
args: "{family} {platform} {site-type} {slug}"
---

# S-18: Page Plan — Structure Planning

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform} {site-type} {slug}`

## Purpose
Plan the page structure before drafting. Maps sections to evidence claims, code positions to snippets, and FAQ items to knowledge. Produces a structured plan that S-19 (page-draft) will follow.

## Pre-conditions
1. S-10 plan file should exist: `reports/plans/{family}-{platform}-{slug}.yaml`
2. Knowledge model must exist: `knowledge/{family}/{platform}/merged/index.json`
3. Knowledge must not be stale

## Golden Corpus Pre-conditions

1. **Load corpus profile**: Read `knowledge/{family}/{platform}/_corpus/{site-type}_profile.json`
   - If not found → WARN and suggest running `/corpus-scan {family} {platform} {site-type}`; proceed with default template

2. **Load golden index**: Read `golden/_index.json`
   - If not found → WARN and suggest running `python scripts/golden_index.py`; proceed with default template

3. **Determine variant**: Read `selected_variant` from the corpus profile
   - Record this in the structure plan for S-19 to use

4. **Select golden page**: From `golden/_index.json`, find the page matching the target page_role and variant
   - Page role is determined by site-type: docs→`workflow_page`, blog→`feature_blog`, kb→`howto_article`, reference→`api_reference`

5. **Incorporate golden structural contracts into the plan**: For each planned section:
   - Look up the matching section in the golden page
   - Record its structural contract (required block types, minimum counts, target word count) in the plan YAML
   - This ensures S-19 has explicit per-section block requirements

6. **Record style rubric in plan**: Include the golden page's `style_rubric` values in the structure YAML so S-19 can enforce them

## Steps

1. **Read S-10 plan** from `reports/plans/{family}-{platform}-{slug}.yaml`
   - If not found, proceed with arguments directly (S-10 is recommended but not mandatory)

2. **Load knowledge artifacts**:
   - `knowledge/{family}/{platform}/merged/index.json`
   - `knowledge/{family}/{platform}/merged/claims.json`
   - `knowledge/{family}/{platform}/merged/api_surface.json`
   - `knowledge/{family}/{platform}/merged/formats.json`
   - `knowledge/{family}/{platform}/merged/constants.json` — module-level constants
   - List available snippets in `knowledge/{family}/{platform}/merged/snippets/`

3. **Determine page template** from site-type:
   - `docs` → use new-docs-page section structure (getting-started or developer-guide)
   - `blog` → use new-blog-post section structure
   - `kb` → use new-kb-howto section structure (or new-kb-faq if slug is "faq")
   - `reference` → use new-reference-page section structure

4. **Select relevant claims**: From claims.json, filter claims that are:
   - Relevant to the page's topic (based on slug and purpose)
   - Confidence >= 0.5
   - Not from `forbidden_claims`
   - Prioritize `dual` and `dual_fuzzy` provenance over single-source

5. **Map sections to claims**: For each section in the template:
   - Assign 2–5 claims that the section should cover
   - Note the claim_id for each (used by S-24 later)

6. **Map code positions to snippets**: For each code block position:
   - Select a snippet from `snippets/` that demonstrates the relevant API
   - If no snippet available, note which API methods to demonstrate (must be in api_surface.json)

7. **Map FAQ items** (if page type includes FAQ):
   - Select questions from knowledge: usage patterns, format support, limitations
   - Link each to supporting claims

8. **Check reference content**: Read existing pages for the same family/platform:
   - Note internal link targets available for cross-referencing
   - Identify any overlap with existing content (avoid duplication)

9. **Write structure plan** to `reports/plans/{family}-{platform}-{slug}-structure.yaml`:
   ```yaml
   family: {family}
   platform: {platform}
   site_type: {site-type}
   slug: {slug}
   template: {template name}
   golden_variant: {selected variant from corpus profile}
   golden_style_rubric:
     prose_before_code: true
     use_case_required: false
     code_completeness_required: true
     avg_sentence_length: 20
     min_code_variety: 3
   sections:
     - heading: "{section title}"
       claims: [CLM-xxx, CLM-yyy]
       code_snippet: "{snippet filename or null}"
       api_demo: [ClassName.method]
       structural_contract: "{block sequence and minimum counts from golden}"
       notes: "{any special instructions}"
   faq_items:
     - question: "{question}"
       answer_claims: [CLM-xxx]
   internal_links:
     - "{relative path to existing page}"
   created_at: {ISO-8601}
   ```

10. **Update S-10 plan status** to `structure_planned`

## Output

```
PAGE PLAN — {family}/{platform}/{slug}
Template: {template name}
Sections: {count}
Claims mapped: {count}
Snippets selected: {count}
FAQ items: {count}

Structure plan: reports/plans/{family}-{platform}-{slug}-structure.yaml
Next step: Run /page-draft {family} {platform} {site-type} {slug}
```

## Error handling
- If no claims match the topic → WARN and suggest broader topic or different slug
- If no snippets available → proceed but note code blocks will need manual API demos
- If knowledge is stale → abort
