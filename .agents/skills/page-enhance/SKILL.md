---
name: page-enhance
id: S-21
description: >
  Enhance a content page to meet quality bar based on the gap analysis from
  S-17 rubric-align. Applies targeted improvements per dimension.
args: "{content-file-path}"
---

# S-21: Page Enhance — Quality Improvement

**Arguments**: $ARGUMENTS
Expected format: `{content-file-path}`

## Purpose
Enhance a content page to meet the quality bar based on the gap analysis produced by S-17 (rubric-align). Applies targeted improvements dimension by dimension.

## Pre-conditions
1. S-17 rubric report must exist for this page in `reports/rubric/`
2. Content file must exist
3. Knowledge model must exist and not be stale
4. If Freshness dimension scored D or F → run S-14 (knowledge-update) first, then re-run S-17
5. If Golden conformance dimension scored below B → load `golden/_index.json` and the matching golden `.md` file for conformance-guided healing (step 4g)

## Steps

1. **Read the rubric report** from S-17 (most recent for this file in `reports/rubric/`)

2. **Read the content file**

3. **Load knowledge**: `index.json`, `claims.json`, `api_surface.json`, `formats.json`, `snippets/`

4. **Enhance each dimension below B**:

   a. **Completeness below B**:
      - Identify uncovered claims from claims.json that are relevant to this page
      - Add new subsections or paragraphs covering high-confidence claims (confidence >= 0.7)
      - Use verified snippets for supporting code examples
      - Do NOT add claims with confidence < 0.5 or provenance = "llm_fallback"

   b. **Evidence density below B**:
      - Identify factual sections not represented in the YAML `evidence:` frontmatter block
      - Match each to the closest claim in claims.json
      - Prepare for S-24 (evidence-cite) to attach proper citations
      - Rewrite vague paragraphs to be more specific and citable

   c. **Code quality below B**:
      - Add language identifiers to bare code blocks (e.g., ` ```python `)
      - Replace unverified code with snippets from `snippets/` where available
      - Fix incorrect class/method names using api_surface.json
      - Remove placeholder code (`// TODO`, `...`)

   d. **Structure below B**:
      - Fix frontmatter: add missing required fields, correct date formats
      - Fix heading hierarchy: no skipped levels
      - Add missing template sections for the page type
      - Add section dividers where expected

   e. **API accuracy below B**:
      - Replace incorrect class/method names with verified ones from api_surface.json
      - Remove references to classes/methods not in the API surface
      - Update import statements if api_surface.json specifies canonical imports

   f. **Freshness below B**:
      - Remove orphaned citations (claim_ids no longer in claims.json)
      - Update references to renamed API methods
      - If knowledge is stale, abort and instruct to run S-14 first

   g. **Golden conformance below B** (if rubric includes this dimension):
      - Load `golden/_index.json` and find the matching golden page for this page's role and variant
      - Read the golden file at `source_path`
      - If section_coverage low → add missing golden sections
      - If section_order low → reorder sections to match golden sequence
      - If depth_proportionality low → expand thin sections or trim bloated ones toward golden proportions
      - If block_type_coverage low → add missing block types (code, list, table) per golden structural contract
      - If code_density_alignment low → adjust code-to-prose ratio toward golden target

5. **Update frontmatter**: Set `lastmod` to today's date

6. **Write enhanced content** back to the file

## Output

```
PAGE ENHANCE — {content-file-path}
Rubric report: {report-path}

Improvements applied:
  Completeness:       {n} claims added
  Evidence:           {n} paragraphs prepared for citation
  Code quality:       {n} blocks fixed
  Structure:          {n} fixes applied
  API accuracy:       {n} references corrected
  Freshness:          {n} orphaned cites removed
  Golden conformance: {n} sections aligned to golden template

Previous grade: {grade from S-17}
Estimated new grade: {grade}
```

## Post-conditions
- After enhancement, run:
  1. S-23 (ground-check) — verify enhanced content passes truth gate
  2. S-01 (path-guard) — validate write path
  3. Then write

## Error handling
- If rubric report not found → run S-17 first
- If knowledge is stale → abort, instruct to run S-14
- If no improvements can be made (all gaps require human judgment) → escalate
