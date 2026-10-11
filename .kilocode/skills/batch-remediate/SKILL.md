---
name: batch-remediate
description: >
  Full Eval→Fix→LLM→Re-eval pipeline for batch content remediation
args: "{family} {platform}"
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

<!-- CONTRACT: scripts/pipeline/commands/content/remediate.py (handles Steps 3-5 only)
     postcondition: remediate.py applies deterministic auto-fixes and outputs LLM queue
     postcondition: Step 6 (LLM fix pass) is executed by the agent, not by the script
     postcondition: re-evaluation in Step 7 runs content_eval again and produces diff report
     note: remediate.py has no LLM pass — LLM fixes are agent actions using knowledge artifacts
     verified: 2026-04-01
-->
# S-40: Batch Remediate — Full Eval→Fix→LLM→Re-eval Pipeline

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}` — e.g. `3d python`

## Purpose

Run the complete remediation pipeline for all content pages of a product: evaluate, triage,
auto-fix deterministic issues (via `remediate.py`), apply LLM fixes for non-deterministic
issues (agent-executed, not automated by the script), then re-evaluate to confirm improvement.

> **Script scope**: `remediate.py` handles Steps 3–5 only (evaluate, triage, auto-fix).
> Step 6 (LLM fix pass) is performed **by the agent directly**, not by any script. The agent
> reads the LLM queue output from Step 4 and applies fixes file-by-file using its own
> reasoning + knowledge artifacts. If you only need deterministic auto-fixes (no LLM pass),
> use S-41 (batch-eval-fix) instead.

## Lightweight mode (no LLM)

For deterministic auto-fixes only (no LLM pass), use S-41 (batch-eval-fix) instead:
```
/batch-eval-fix {family} {platform}
```
This is safe for unattended runs and skips the LLM fix pass (Step 6).

## Pre-conditions

1. **Knowledge bootstrap**: Run `/knowledge-bootstrap {family} {platform}` and check status:
   - `STOP:partial` → halt (see printed message)
   - Any other status (`READY`, `BOOTSTRAPPED`, `REFRESHED`, `WARN:conflicts`) → continue
2. `scripts/pipeline/content_eval` and `scripts/pipeline/commands/content/remediate.py` are available.

## Steps

> **Skill context gate** — run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-40 --scope "*"
> ```


1. **Parse arguments** to get `{family}` and `{platform}`.

2. **Load knowledge model**:
   - Read `knowledge/{family}/{platform}/merged/model.yaml` — note `repo_sha`, `version`.
   - Read `knowledge/{family}/{platform}/merged/claims.json`.
   - Read `knowledge/{family}/{platform}/merged/api_surface.json`.
   - Index `knowledge/{family}/{platform}/merged/snippets/` for code examples.

3. **Run full evaluation**:

   ```bash
   .venv/Scripts/python -m scripts.pipeline.content_eval evaluate {family} {platform} --format json --remediation
   ```

   Save the report path (e.g. `reports/content_eval/eval-{timestamp}.json`).

4. **Run triage + auto-fix**:

   ```bash
   .venv/Scripts/python scripts/pipeline/commands/content/remediate.py fix {eval-report-path}
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
   .venv/Scripts/python -m scripts.pipeline.content_eval evaluate {family} {platform} --write-grade --format json
   ```

8. **Diff reports** to show improvement:

   ```bash
   .venv/Scripts/python -m scripts.pipeline.content_eval diff {old-report} {new-report}
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

9b. **Backlink compliance assertion**: After LLM fixes, verify all modified pages still
    have compliant backlinks (LLM rewrites can erase See Also / Related Resources sections):
    ```bash
    .venv/Scripts/python scripts/pipeline/commands/ops/backlink_audit.py \n      --family {family} --platform {platform} --subdomain {subdomain}
    ```
    For any MISSING pages, re-inject:
    ```bash
    .venv/Scripts/python scripts/pipeline/commands/ops/backlink_backfill.py \n      --family {family} --platform {platform} --subdomain {subdomain} --write
    ```
    If BLOCKED_TARGET: log WARN and continue.
    **Anchor policy v2**: platform targets → `Aspose.{Family} for {Platform} Enterprise Product`; family targets → `Aspose.{Family} Enterprise Product Family` (governed by `docs/governance/positioning-policy.md`).

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-40 --status completed
> ```

## Post-conditions

- Auto-fixes are applied and idempotent.
- LLM fixes pass ground-check (`audit.py`).
- Re-evaluation report is saved to `reports/content_eval/`.
- Remediation report is saved to `reports/remediation/`.
- Human queue items are listed for manual review. Each item should be addressed via
  **S-73 (manual-edit)** — the only sanctioned path for operator-directed targeted edits.
- Maximum 2 LLM passes per file enforced (AGENTS.md Section 8 compliance).
- No files outside allowed content paths were modified (S-01 path-guard).

## Error Handling

- **Knowledge state issues**: Handled by `/knowledge-bootstrap` in pre-conditions.
- **Audit FAIL after LLM fix**: Revert file, add to human queue.
- **2 LLM passes exhausted**: Escalate to human queue with finding details.
- **File not found**: Skip and report.

## Related Skills

- **S-41 batch-eval-fix**: Lightweight auto-fix only (no LLM pass). Use when you only need deterministic fixes.
- **S-42 category-fix**: Run a specific category fixer on targeted files.
- **S-89 heal-batch**: Policy-routed batch healing from an eval report. Routes findings through the heal policy table to auto/llm/regen modes in a single pass. Use `/heal-batch` when you have an existing eval report and want structured dispatching rather than the sequential eval→fix→LLM pipeline of S-40.

---

## LLM Metrics Obligation

If this skill invokes `llm.professionalize.com` directly or through `LLMRouter`,
the run carries a **metrics obligation** (METRICS-PLAN-001, `AGENTS.md §15`):

- All professionalize calls must use `ProfessionalizeClient`, `LLMRouter`, or a
  registered adapter entry in `metrics_callsite_registry.yaml`.
- Each run must capture per-call `MetricsEvent` records and aggregate them into a
  validated `MetricsRow` via `RunMetrics`.
- Default mode is **dry-run**. Live posting requires explicit owner approval and
  `AGENT_METRICS_ENDPOINT` / `AGENT_METRICS_TOKEN` set locally.
- Non-professionalize calls (Gemini, Ollama, M2M) are excluded from
  `token_usage` and `api_calls_count`.
- Metrics failures must not crash or block the parent pipeline job.
