---
name: batch-eval-fix
description: >
  Quick eval and auto-fix batch pipeline for content quality
args: "{family} {platform}"
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# S-41: Batch Eval Fix — Quick Eval + Auto-Fix Only

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}` or `{eval-report-path}` or `--eval-report {eval-report-path}` — e.g. `3d python` or `reports/content_eval/eval-20260324.json`

When `--eval-report` is provided, skip the evaluation step and consume the existing report directly. This is useful when chaining with S-89 (heal-batch) or when re-running fixes after a previous evaluation.

## Purpose

Lightweight remediation pipeline: evaluate content (or consume an existing report), then apply only deterministic auto-fixes. No LLM pass. Safe for unattended batch runs.

## Pre-conditions

1. **Knowledge bootstrap** (when using `{family} {platform}`): Run `/knowledge-bootstrap {family} {platform}` and check status:
   - `STOP:partial` → halt (see printed message)
   - Any other status (`READY`, `BOOTSTRAPPED`, `REFRESHED`, `WARN:conflicts`) → continue
2. `scripts/pipeline/content_eval` and `scripts/pipeline/remediate.py` are available.

## Steps

> **Skill context gate** — run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/skill_context.py begin --skill S-41 --scope "*"
> ```


1. **Parse arguments.** If two words, treat as `{family} {platform}`. If a `.json` path or `--eval-report {path}`, use it directly as the eval report.

2. **Run evaluation** (skip if consuming existing report via path or `--eval-report`):

   ```bash
   .venv/Scripts/python -m scripts.pipeline.content_eval evaluate {family} {platform} --format json --remediation
   ```

   Note the report path from stderr output (e.g. `reports/content_eval/eval-{timestamp}.json`).

3. **Dry-run auto-fix** to preview changes:

   ```bash
   .venv/Scripts/python scripts/pipeline/remediate.py fix {eval-report-path} --dry-run
   ```

   Review the dry-run output. Confirm findings and planned fixes look correct.

4. **Apply auto-fixes**:

   ```bash
   .venv/Scripts/python scripts/pipeline/remediate.py fix {eval-report-path}
   ```

5. **Refresh evidence** on modified files. Extract the list of modified files from the remediation report, then run:

   ```bash
   .venv/Scripts/python scripts/pipeline/attach_evidence.py --files {file1} {file2} ...
   ```

6. **Report results** to the user:

   ```
   BATCH EVAL FIX — {target}
   Findings triaged: {total}
   Auto-fixed: {count} ({breakdown by fixer})
   Deferred to LLM: {count}
   Deferred to human: {count}
   Reports: {json_path}, {md_path}
   ```

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/skill_context.py end --skill S-41 --status completed
> ```

## Post-conditions

- Only deterministic, safe fixes applied (frontmatter fields, code fence languages, placeholders, evidence blocks).
- No LLM calls made — all fixes are regex-based text transformations.
- Evidence blocks refreshed for modified files.
- Remediation report saved to `reports/remediation/`.
- No files outside allowed content paths were modified (S-01 path-guard).
