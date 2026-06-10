# S-40: Batch Remediate — Full Eval→Fix→LLM→Re-eval Pipeline

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}` — e.g. `3d python`

## Purpose

Run the complete remediation pipeline for all content pages of a product: evaluate, triage, auto-fix deterministic issues, apply LLM fixes for non-deterministic issues, then re-evaluate to confirm improvement.

## Pre-conditions

1. **Knowledge bootstrap**: Run `/knowledge-bootstrap {family} {platform}` and check status:
   - `STOP:partial` → halt (see printed message)
   - Any other status (`READY`, `BOOTSTRAPPED`, `REFRESHED`, `WARN:conflicts`) → continue
2. `scripts/pipeline/content_eval` and `scripts/pipeline/commands/content/remediate.py` are available.

## Steps

1. **Parse arguments** to get `{family}` and `{platform}`.

2. **Load knowledge model**:
   - Read `knowledge/{family}/{platform}/merged/model.yaml` — note `repo_sha`, `version`.
   - Read `knowledge/{family}/{platform}/merged/claims.json`.
   - Read `knowledge/{family}/{platform}/merged/api_surface.json`.
   - Index `knowledge/{family}/{platform}/merged/snippets/` for code examples.

3. **Run full evaluation**:

   ```bash
   python -m scripts.pipeline.content_eval evaluate {family} {platform} --format json --remediation
   ```

   Save the report path (e.g. `reports/content_eval/eval-{timestamp}.json`).

4. **Run triage + auto-fix**:

   ```bash
   python scripts/pipeline/commands/content/remediate.py fix {eval-report-path}
   ```

   Parse the remediation report to get: fixes applied, LLM queue, human queue.

5. **Report auto-fix results**: Count of fixes applied by category and fixer.

6. **LLM fix pass** — for each file in the LLM queue (grouped by file):

   a. Read the file and gather all its LLM-needed findings.

   b. Apply targeted fixes per finding type:

      **Content quality fixes:**
      - **Risk language (RL)**: Rewrite the sentence with factual phrasing. Use claims from `claims.json` as evidence backing. Remove unsupported superlatives.
      - **Wrong platform code (PC)**: Replace code block with correct snippet from `snippets/`. If no matching snippet exists, rewrite using `api_surface.json` method signatures.
      - **Forbidden claims (FC)**: Remove the containing sentence or paragraph. If critical context is lost, replace with a knowledge-grounded alternative from `claims.json`.
      - **Prose truth (PT)**: Correct the factual error using the nearest matching claim from `claims.json`.
      - **API accuracy (AA)**: Replace incorrect API token with the correct one from `api_surface.json`. Check inheritance chains if needed.
      - **Code plausibility (CP)**: Replace broken code example with verified snippet from `snippets/` or construct from `api_surface.json`.

      **Structural / generation fixes:**
      - **Missing description (ST)**: Read the page title, first H2 heading, and relevant claims from `claims.json`. Generate a 1-sentence SEO `description:` value (max 160 chars). Must be factual — only reference APIs/features present in `api_surface.json`. Insert into frontmatter via regex.
      - **Too few FAQ questions (RV)**: Load `claims.json` for the product. Diff claim topics against existing `## ` question headings. Generate 3-5 new Q&A sections as `## Question?\n\nAnswer grounded in claim...`. Each answer must cite at least one claim from knowledge. Append after existing FAQ content.
      - **Missing reference table (RV)**: Load `api_surface.json`. Find the class matching the page's `linkTitle` field. Extract methods and properties. Generate a markdown table: `| Name | Return Type | Description |`. Every row must come from `api_surface.json` — no fabricated members. Insert after `## Overview` section.

   c. Write the fixed file.

   d. Run ground-check: `python scripts/pipeline/commands/content/audit.py --files {path}`

   e. If audit returns FAIL after the fix, revert the file and add to human queue.

   f. Maximum 2 LLM passes per file. If findings persist after 2 passes, escalate to human queue.

7. **Run re-evaluation**:

   ```bash
   python -m scripts.pipeline.content_eval evaluate {family} {platform} --format json
   ```

8. **Diff reports** to show improvement:

   ```bash
   python -m scripts.pipeline.content_eval diff {old-report} {new-report}
   ```

9. **Report final summary**:

   ```
   BATCH REMEDIATE — {family}/{platform}
   Before: {fail_count} FAIL, {warn_count} WARN across {page_count} pages
   Auto-fixed: {auto_count} findings ({fixer breakdown})
   LLM-fixed: {llm_count} findings
   After: {new_fail_count} FAIL, {new_warn_count} WARN
   Resolved: {resolved_count} findings
   Human queue: {human_count} items (listed below)
   Reports: {report_paths}
   ```

## Post-conditions

- Auto-fixes are applied and idempotent.
- LLM fixes pass ground-check (`audit.py`).
- Re-evaluation report is saved to `reports/content_eval/`.
- Remediation report is saved to `reports/remediation/`.
- Human queue items are listed for manual review.
- Maximum 2 LLM passes per file enforced (AGENTS.md Section 8 compliance).
- No files outside allowed content paths were modified (S-01 path-guard).

## Error Handling

- **Knowledge state issues**: Handled by `/knowledge-bootstrap` in pre-conditions.
- **Audit FAIL after LLM fix**: Revert file, add to human queue.
- **2 LLM passes exhausted**: Escalate to human queue with finding details.
- **File not found**: Skip and report.
