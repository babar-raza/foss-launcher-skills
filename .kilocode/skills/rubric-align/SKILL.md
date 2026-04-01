---
name: rubric-align
id: S-17
description: >
  Assess a content page against the quality rubric using content_eval.
args: "{relative-file-path}"
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# S-17: Rubric Align - Assess Page Against Quality Rubric

**Arguments**: $ARGUMENTS
Expected format: `{relative-file-path}` - e.g. `content/docs.aspose.org/en/3d/python/developer-guide/rendering.md`

## Purpose

Assess a content page against the quality rubric by running content_eval evaluators and
producing a rubric score card. This identifies which quality dimensions need improvement
before enhancement (S-21) is applied.

## Pre-conditions

1. The file at `{relative-file-path}` exists and is a content page under `content/`
2. Detect `{family}` and `{platform}` from the file path
3. `knowledge/{family}/{platform}/merged/` exists with `claims.json` and `api_surface.json`
4. `scripts/pipeline/content_eval` module is available

## Steps

1. **Parse arguments**: Extract file path from $ARGUMENTS.
2. **Detect product**: Parse `{family}` and `{platform}` from the file path.
3. **Read knowledge model**: Load `knowledge/{family}/{platform}/merged/model.yaml` and verify `stale_since` is null. If stale, warn but continue (results may be against outdated knowledge).
4. **Run content_eval evaluators**:
   ```bash
   cd scripts/pipeline
   python -m content_eval evaluate --files ../../{relative-file-path} --format json
   ```
5. **Build rubric score card** from evaluator results. Score each dimension 0-100:

   | Dimension | Evaluator(s) | Weight |
   |-----------|-------------|--------|
   | API Accuracy | api_accuracy (AA) | 25% |
   | Content Structure | structure (ST), page_role (RV) | 20% |
   | Evidence Backing | evidence_depth (EG) | 15% |
   | Prose Truth | prose_truth (PT), forbidden_claims (FC) | 15% |
   | Code Quality | code_plausibility (CP) | 10% |
   | Platform Purity | platform_purity (PC) | 10% |
   | Risk Language | risk_language (RL) | 5% |

6. **Compute overall rubric score**: Weighted average of all dimensions.
7. **Assign grade**:
   - A: 90-100 (publication ready)
   - B: 75-89 (minor improvements needed)
   - C: 60-74 (significant gaps - run S-21 page-enhance)
   - D: 40-59 (major issues - run S-26 heal-page)
   - F: 0-39 (critical failures - escalate to human)

8. **Output score card**:
   ```
   RUBRIC ALIGNMENT - {file-path}
   Product: {family}/{platform}

   DIMENSION SCORES
     API Accuracy:      [score]/100  (weight 25%)
     Content Structure:  [score]/100  (weight 20%)
     Evidence Backing:   [score]/100  (weight 15%)
     Prose Truth:        [score]/100  (weight 15%)
     Code Quality:       [score]/100  (weight 10%)
     Platform Purity:    [score]/100  (weight 10%)
     Risk Language:      [score]/100  (weight 5%)

   OVERALL: [weighted score]/100 - Grade [A-F]

   TOP ISSUES (sorted by impact):
     1. [dimension]: [specific finding]
     ...

   RECOMMENDED NEXT STEP: [S-21 / S-26 / publish / escalate]
   ```

## Post-conditions

- Score card is printed with per-dimension scores
- Grade is assigned (A-F)
- Next step recommendation is provided
- No file modifications made (read-only skill)

## Error handling

- If content_eval is not available, fall back to manual rubric assessment using content-check patterns
- If knowledge model is missing, score Evidence Backing and Prose Truth as 0 and note in output
