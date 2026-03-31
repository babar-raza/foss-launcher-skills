---
name: batch-eval-fix
description: >
  S-41: Lightweight remediation pipeline — evaluate content then apply only
  deterministic auto-fixes. No LLM pass. Safe for unattended batch runs.
args: "{family} {platform} or {eval-report-path}"
---
# S-41: Batch Eval Fix — Quick Eval + Auto-Fix Only

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}` or `{eval-report-path}` — e.g. `3d python` or `reports/content_eval/eval-20260324.json`

## Purpose

Lightweight remediation pipeline: evaluate content (or consume an existing report), then apply only deterministic auto-fixes. No LLM pass. Safe for unattended batch runs.

## Pre-conditions

1. **Knowledge bootstrap** (when using `{family} {platform}`): Run `/knowledge-bootstrap {family} {platform}` and check status:
   - `STOP:partial` → halt (see printed message)
   - Any other status (`READY`, `BOOTSTRAPPED`, `REFRESHED`, `WARN:conflicts`) → continue
2. `scripts/pipeline/content_eval` and `scripts/pipeline/remediate.py` are available.

## Steps

1. **Parse arguments.** If two words, treat as `{family} {platform}`. If a `.json` path, use it directly as the eval report.

2. **Run evaluation** (skip if consuming existing report):

   ```bash
   python -m scripts.pipeline.content_eval evaluate {family} {platform} --format json --remediation
   ```

   Note the report path from stderr output (e.g. `reports/content_eval/eval-{timestamp}.json`).

3. **Dry-run auto-fix** to preview changes:

   ```bash
   python scripts/pipeline/remediate.py fix {eval-report-path} --dry-run
   ```

   Review the dry-run output. Confirm findings and planned fixes look correct.

4. **Apply auto-fixes**:

   ```bash
   python scripts/pipeline/remediate.py fix {eval-report-path}
   ```

5. **Refresh evidence** on modified files. Extract the list of modified files from the remediation report, then run:

   ```bash
   python scripts/pipeline/attach_evidence.py --files {file1} {file2} ...
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

## Post-conditions

- Only deterministic, safe fixes applied (frontmatter fields, code fence languages, placeholders, evidence blocks).
- No LLM calls made — all fixes are regex-based text transformations.
- Evidence blocks refreshed for modified files.
- Remediation report saved to `reports/remediation/`.
- No files outside allowed content paths were modified (S-01 path-guard).
