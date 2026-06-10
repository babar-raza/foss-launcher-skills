---
name: category-fix
description: >
  S-42: Run a specific category fixer on targeted files. Surgical fix when
  you know exactly which finding category (ST, RV, EG, RL, AA, PC, FC, PT, CP, CG) needs remediation.
args: "{category} {file-or-directory}"
---
# S-42: Category Fix — Run Specific Fixer on Files

**Arguments**: $ARGUMENTS
Expected format: `{category} {file-or-directory}` — e.g. `ST content/docs.aspose.org/en/3d/python/` or `RV content/kb.aspose.org/en/slides/java/faq.md`

## Purpose

Run a specific category fixer on targeted files. Useful for surgical fixes when you know exactly which finding category needs remediation.

## Pre-conditions

1. Target files exist.
2. Category is a valid eval category code: ST, RV, EG, RL, AA, PC, FC, PT, CP, CG.

## Category-to-Evaluator Mapping

| Code | Evaluator | Auto-fixable? |
|------|-----------|---------------|
| ST | structure | Yes (code fence lang, placeholders) |
| RV | page_role | Yes (frontmatter type, author) |
| EG | evidence_depth | Yes (evidence attachment) |
| RL | risk_language | LLM only |
| AA | api_accuracy | LLM only |
| PC | platform_purity | LLM only |
| FC | forbidden_claims | LLM only |
| PT | prose_truth | LLM only |
| CP | code_plausibility | LLM only |
| CG | coverage | Skip (enhancement, not remediation) |

## Steps

1. **Parse arguments**: Extract category code and file path(s) from `$ARGUMENTS`.

2. **Discover files**: If path is a directory, discover all `.md` files within it.

3. **Run eval** on just those files with the relevant evaluator:

   ```bash
   python -m scripts.pipeline.content_eval evaluate --files {files...} --evaluators {evaluator} --format json
   ```

4. **Run targeted fix**:

   ```bash
   python scripts/pipeline/commands/content/remediate.py fix {report-path} --categories {category}
   ```

5. **For LLM-needed findings** in the category (RL, AA, PC, FC, PT, CP):
   - Read the file and its findings from the remediation report's `llm_queue`.
   - Load knowledge: `knowledge/{family}/{platform}/merged/claims.json`, `api_surface.json`, `snippets/`.
   - Apply targeted fixes per finding type:
     - **RL** (risk language): Rewrite sentence with factual phrasing grounded in claims.
     - **AA** (API accuracy): Replace incorrect API tokens with correct ones from `api_surface.json`.
     - **PC** (platform contamination): Replace wrong-platform code with correct snippet from `snippets/`.
     - **FC** (forbidden claims): Remove the sentence containing the forbidden claim.
     - **PT** (prose truth): Correct factual errors using `claims.json`.
     - **CP** (code plausibility): Replace with verified snippet from `snippets/` or rewrite using `api_surface.json`.
   - Run ground-check after each file: `python scripts/pipeline/commands/content/audit.py --files {path}`
   - If audit returns FAIL, revert the file and report as human-needed.

6. **Re-evaluate** the fixed files:

   ```bash
   python -m scripts.pipeline.content_eval evaluate --files {files...} --evaluators {evaluator} --format json
   ```

7. **Report**:

   ```
   CATEGORY FIX — {category} on {file_count} files
   Before: {finding_count} findings
   Fixed: {fixed_count}
   Remaining: {remaining_count}
   ```

## Post-conditions

- Only the specified category's findings are addressed.
- Other content is untouched.
- Evidence refreshed if EG category was fixed.
- Ground-check passes for all LLM-modified files.
