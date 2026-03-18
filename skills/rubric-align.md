---
name: rubric-align
id: S-17
description: >
  Evaluate a content page against a quality rubric and produce a gap analysis
  showing what needs improvement per dimension.
args: "{content-file-path}"
---

# S-17: Rubric Align — Quality Gap Analysis

**Arguments**: $ARGUMENTS
Expected format: `{content-file-path}`

## Purpose
Evaluate a content page against a quality rubric and produce a detailed gap analysis. Unlike S-25 (eval-page) which assigns a grade, rubric-align produces actionable improvement recommendations for S-21 (page-enhance) to execute.

## Pre-conditions
1. Content file must exist
2. Knowledge model must exist: `knowledge/{family}/{platform}/merged/index.json`

## Rubric Dimensions

| Dimension | Grade A (excellent) | Grade B (good) | Grade C (adequate) | Grade D (poor) | Grade F (failing) |
|-----------|--------------------|----|----|----|---|
| Completeness | Covers >90% of relevant claims | 75–90% | 60–74% | 40–59% | <40% |
| Evidence density | >90% factual paragraphs cited | 75–90% | 60–74% | 40–59% | <40% |
| Code quality | All blocks verified, language IDs | Minor gaps | Some unverified | Multiple issues | No verification |
| Structure | Perfect template compliance | Minor deviations | Noticeable gaps | Missing sections | Broken structure |
| API accuracy | 100% verified API | 1–2 minor issues | Some unverified | Multiple errors | Fabricated API |
| Freshness | Knowledge current, all citations valid | Minor staleness | Some orphaned cites | Significant staleness | Stale knowledge |
| Golden conformance | Score >= 0.75 | 0.55–0.74 | 0.35–0.54 | 0.20–0.34 | < 0.20 |

## Steps

1. **Read the content file** at $ARGUMENTS

2. **Identify product**: Extract `{family}` and `{platform}` from path

3. **Load knowledge**: `index.json`, `claims.json`, `api_surface.json`, `formats.json`

4. **Score each dimension** (A through F):
   - **Completeness**: Count relevant claims from claims.json; count how many appear in content
   - **Evidence density**: Count factual paragraphs; count those with `<!-- evidence: -->` comments
   - **Code quality**: Check language identifiers, API verification, snippet provenance
   - **Structure**: Check frontmatter, headings, dividers, template section order
   - **API accuracy**: Cross-reference all class/method names against api_surface.json
   - **Freshness**: Check stale flag, orphaned citations, lastmod vs last_merged
   - **Golden conformance**: Run `python scripts/golden_conformance.py {content-file-path} {page_role}` and read the conformance score. If script/index unavailable, skip this dimension.

5. **Produce gap analysis**: For each dimension below B:
   - List specific items that need fixing
   - Provide the knowledge source that supports the fix
   - Estimate effort (minor / moderate / significant)

6. **Compute overall grade**: Lowest dimension grade determines overall

7. **Write rubric report** to `reports/rubric/{family}-{platform}-{slug}-{timestamp}.md`

## Output

```
RUBRIC ALIGNMENT — {content-file-path}
Knowledge: {family}/{platform}

Dimension Grades:
  Completeness:       {grade} — {brief finding}
  Evidence density:   {grade} — {brief finding}
  Code quality:       {grade} — {brief finding}
  Structure:          {grade} — {brief finding}
  API accuracy:       {grade} — {brief finding}
  Freshness:          {grade} — {brief finding}
  Golden conformance: {grade} — {brief finding}

Overall: {lowest grade}

Gap Analysis:
  {dimension}: {grade}
    - {specific gap} (effort: {minor|moderate|significant})
    - {specific gap} ...

Report: reports/rubric/{report-filename}
```

## Post-conditions
- If overall grade is C or below → recommend running S-21 (page-enhance)
- If overall grade is D or F → recommend running S-25/S-26 (healing chain) instead
- Rubric report is consumed by S-21 to guide enhancement

## Error handling
- If knowledge not found → mark Completeness, Evidence, API, Freshness as "unable to assess"
- If content file not found → abort
