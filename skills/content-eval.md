---
name: content-eval
description: >
  Multi-dimensional content evaluation against repo truth. Checks API accuracy,
  platform purity, forbidden claims, page role compliance, structural correctness,
  risk language, evidence depth, prose truth, code plausibility, coverage gaps,
  and cross-page consistency.
args: "{family} {platform} | all | --files path1.md path2.md"
---
# Content Eval — Multi-Dimensional Content Evaluation

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}` or `all` or `--files path1.md path2.md`

## Purpose
Run a comprehensive, multi-dimensional evaluation of content pages against repo truth.
Goes beyond API token verification (audit.py/S-23) to check:
- API accuracy (wraps audit.py)
- Platform purity (wrong-language contamination)
- Forbidden claims (matches against limitations)
- Page role compliance (reference/kb/docs/blog/products rubrics)
- Structural correctness (headings, code fences, frontmatter, placeholders)
- Risk language (superlatives, unsupported claims)
- Evidence depth (claim-to-evidence backing ratio)
- Prose truth (format claims vs knowledge)
- Code plausibility (empty blocks, placeholders, truncated examples)
- Coverage gaps (missing important API capabilities)
- Cross-page consistency (optional)

## Steps

1. **Parse arguments**: Determine target scope from $ARGUMENTS
2. **Run evaluation**: Execute the content_eval pipeline

```bash
python -m scripts.pipeline.content_eval evaluate $ARGUMENTS --remediation
```

3. **Review findings**: Present the report to the user, organized by severity
4. **For JSON output**: Add `--format json` flag
5. **For cross-page analysis**: Add `--cross-page` flag
6. **For specific evaluators only**: Add `--evaluators api_accuracy,platform_purity,page_role`

## Available evaluators
- `api_accuracy` — Wraps audit.py token verification (AA)
- `platform_purity` — Wrong-language code/prose detection (PC)
- `forbidden_claims` — Matches prose against known false claims (FC)
- `page_role` — Section-role rubric compliance (RV)
- `structure` — Heading hierarchy, code fences, placeholders (ST)
- `risk_language` — Superlatives, speculative phrases (RL)
- `evidence_depth` — Claim-to-evidence backing ratio (EG)
- `prose_truth` — Format claims vs knowledge (PT)
- `code_plausibility` — Code example quality (CP)
- `coverage` — Missing API capabilities (CG)

## Output
- Report written to `reports/content_eval/`
- Markdown (default) or JSON format
- Remediation plan with prioritized fix batches
