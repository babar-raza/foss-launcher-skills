<!-- CONTRACT: scripts/pipeline/content_eval/cli.py evaluate
     purpose: batch multi-dimensional content evaluation across 9-16 evaluators
     preconditions: knowledge model available; content files exist under content/
     postcondition: evaluation report with grades and prioritized remediation plan
     idempotent: yes — deterministic evaluators produce same results for same input
     verified: 2026-04-11
-->
# S-51: Content Eval — Multi-Dimensional Content Evaluation

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

> **Skill context gate** — run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-51 --scope "*"
> ```


1. **Parse arguments**: Determine target scope from $ARGUMENTS
2. **Run evaluation**: Execute the content_eval pipeline

```bash
cd scripts/pipeline && .venv/Scripts/python -m content_eval evaluate $ARGUMENTS --remediation
```

3. **Review findings**: Present the report to the user, organized by severity
4. **For JSON output**: Add `--format json` flag
5. **For cross-page analysis**: Add `--cross-page` flag
6. **For specific evaluators only**: Add `--evaluators api_accuracy,platform_purity,page_role`
7. **To run all 16 evaluators** (slower): Add `--evaluators api_accuracy,api_backtick,claim_coverage,platform_purity,forbidden_claims,page_role,structure,prose_truth,format_truth,install_recipe,limitations_check,risk_language,evidence_depth,code_plausibility,coverage,type_accuracy`

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-51 --status completed
> ```

## Available evaluators

By default only the 9 **DEFAULT** evaluators run (fast, deterministic, production-ready). The full set of 16 (**ALL**) includes 7 additional slower or context-specific evaluators. Use `--evaluators <comma-list>` to select any subset.

### DEFAULT evaluators (run when no `--evaluators` flag is given)
- `api_accuracy` — Wraps audit.py token verification (AA) **[DEFAULT]**
- `platform_purity` — Wrong-language code/prose detection (PC) **[DEFAULT]**
- `forbidden_claims` — Matches prose against known false claims (FC) **[DEFAULT]**
- `page_role` — Section-role rubric compliance (RV) **[DEFAULT]**
- `structure` — Heading hierarchy, code fences, placeholders (ST) **[DEFAULT]**
- `risk_language` — Superlatives, speculative phrases (RL) **[DEFAULT]**
- `evidence_depth` — Claim-to-evidence backing ratio (EG) **[DEFAULT]**
- `prose_truth` — Format claims vs knowledge (PT) **[DEFAULT]**
- `code_plausibility` — Code example quality checks (CP) **[DEFAULT]**

### Additional evaluators (available with `--evaluators`, not in DEFAULT set)
- `api_backtick` — Check API class names in prose are properly backtick-quoted (AB)
- `claim_coverage` — Detect phantom evidence: claims in frontmatter not discussed in body (CC)
- `format_truth` — Validate format extension/direction claims against formats.json (FT)
- `install_recipe` — Check that API-usage pages include or link to installation guidance (IR)
- `limitations_check` — Verify capability pages document or link to known limitations (LC)
- `coverage` — Missing important API capabilities (CG)
- `type_accuracy` — Verify method return types and property types (C++ pages) (TA)

## Output
- Report written to `reports/content_eval/`
- Markdown (default) or JSON format
- Remediation plan with prioritized fix batches
