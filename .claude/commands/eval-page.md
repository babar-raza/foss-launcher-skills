# S-25: Eval Page — Content Quality Grade

**Arguments**: $ARGUMENTS
Expected format: `{content-file-path}`

## Purpose
Evaluate a content page and assign a letter grade (A–F) based on a weighted rubric. Used to identify pages that need healing (grade D or below) and to measure quality improvements over time.

## Pre-conditions
1. Content file must exist
2. Knowledge model must exist: `knowledge/{family}/{platform}/merged/index.json`

## Rubric Dimensions

| Dimension | Weight | What it measures |
|-----------|--------|-----------------|
| Structure | 15% | Frontmatter validity, correct headings, dividers, template compliance |
| Evidence | 25% | Citation density, claim traceability, no forbidden claims |
| Completeness | 20% | Coverage of relevant claims from knowledge model |
| Code quality | 15% | Language identifiers, verified API usage, snippet provenance |
| Freshness | 10% | Knowledge staleness, orphaned citations, outdated API references |
| Golden conformance | 15% | Structural alignment with golden template (section coverage, order, depth, block types, code density) |

> **Rubric version**: 2 — includes golden conformance dimension. Version 1 reports used 5 dimensions with different weights.

## Steps

1. **Read the content file** at the path given in $ARGUMENTS

2. **Identify product**: Extract `{family}` and `{platform}` from the file path

3. **Load knowledge**: `index.json`, `claims.json`, `api_surface.json`, `formats.json`

4. **Score Structure (15%)**:
   - Frontmatter: valid YAML, has required fields (title, description, type/layout)
   - Headings: proper hierarchy (no skipped levels), follows template for page type
   - Dividers: section separators where expected (KB articles use `---`)
   - Template compliance: matches expected section order for page type
   - Score: 0–100

5. **Score Evidence (25%)**:
   - Inspect the YAML `evidence:` frontmatter block for claim/API coverage
   - Citation density = cited paragraphs / total factual paragraphs
   - Check all `claim_id` references exist in claims.json
   - Check no forbidden claims are asserted
   - Penalize: orphaned citations (claim_id not in claims.json), missing citations on factual content
   - Score: 0–100

6. **Score Completeness (20%)**:
   - Identify claims in claims.json relevant to this page's topic
   - Count how many are covered (referenced or paraphrased) in the content
   - Coverage = covered claims / relevant claims
   - Penalize: major topics in knowledge model with no page coverage
   - Score: 0–100

7. **Score Code Quality (15%)**:
   - All code blocks have language identifiers
   - Class/method names exist in api_surface.json
   - Code examples come from snippets or use only verified API
   - No placeholder code (`// TODO`, `...`, `pass` without context)
   - Score: 0–100

8. **Score Freshness (10%)**:
   - Knowledge model `stale` flag
   - Citations referencing claims that have changed since last page update
   - API references to methods that have been renamed/removed
   - `lastmod` date compared to knowledge `last_merged` date
   - Score: 0–100

9. **Score Golden Conformance (15%)**:
   - Determine the page_role from the file path and site type (docs developer-guide → `workflow_page`, kb howto → `howto_article`, etc.)
   - Run: `python scripts/golden_conformance.py {content-file-path} {page_role}`
   - Read the output from `reports/conformance/{slug}-conformance.json`
   - Use the `conformance_score` (0.0–1.0) scaled to 0–100
   - If the script is not available or golden index missing → score 50 (neutral) and note in findings
   - Score: 0–100

10. **Compute grade**:
   - Weighted total = (structure × 0.15) + (evidence × 0.25) + (completeness × 0.20) + (code × 0.15) + (freshness × 0.10) + (golden_conformance × 0.15)
   - A: 90–100 | B: 80–89 | C: 70–79 | D: 60–69 | F: below 60

11. **Write report** to `reports/eval/{family}-{platform}-{slug}-{timestamp}.md`
    - Include `rubric_version: 2` in the report header

## Output

```
PAGE EVALUATION — {content-file-path}
Knowledge: {family}/{platform} (sha: {repo_sha})

Rubric version: 2
Dimension Scores:
  Structure:          {score}/100 (weight: 15%)
  Evidence:           {score}/100 (weight: 25%)
  Completeness:       {score}/100 (weight: 20%)
  Code Quality:       {score}/100 (weight: 15%)
  Freshness:          {score}/100 (weight: 10%)
  Golden Conformance: {score}/100 (weight: 15%)

Weighted Total: {total}/100
GRADE: {A|B|C|D|F}

Key Findings:
  {bulleted list of specific issues}

Report: reports/eval/{report-filename}
```

## Post-conditions
- If grade is D or F → trigger S-26 (heal-page)
- If grade is F → this is a hard stop condition (AGENTS.md Section 7)
- If grade is A or B → no action needed
- If grade is C → recommend S-17 (rubric-align) for enhancement

## Error handling
- If knowledge model missing → grade Freshness as 0, note in findings
- If content file empty → grade F immediately
