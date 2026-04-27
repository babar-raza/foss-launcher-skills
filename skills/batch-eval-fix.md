---
name: batch-eval-fix
id: S-41
description: >
  Lightweight remediation pipeline: evaluate content (or consume an existing eval report),
  then apply only deterministic auto-fixes. No LLM pass. Safe for unattended batch runs.
args: "{family} {platform} | --eval-report {eval-report-path}"
---

# S-41: Batch Eval Fix — Quick Eval + Auto-Fix Only

**Arguments**: $ARGUMENTS
Expected format:
- `{family} {platform}` — evaluate then fix all content for this product
- `--eval-report {path}` — skip evaluation; consume an existing eval report directly

When `--eval-report` is provided, the evaluation step is skipped. This is useful when
chaining with other skills or when re-running fixes after a previous evaluation.

## Purpose

Lightweight remediation pipeline: evaluate content (or consume an existing eval report),
then apply only deterministic auto-fixes. **No LLM pass.** Safe for unattended batch runs.

Fixes applied are deterministic text transformations only:
- Fix invalid/missing frontmatter fields (add `date`, `draft`, `type`, `lastmod`)
- Correct code fence language identifiers (e.g., ` ```python ` not ` ```py `)
- Remove placeholder text (`TODO`, `PLACEHOLDER`, `[INSERT ...]`)
- Refresh evidence block (`model_sha`, claim/api citations)
- Fix invalid YAML structure in frontmatter

No LLM-generated prose replacements are made.

## Pre-conditions

1. For `{family} {platform}` mode: knowledge model must exist at
   `knowledge/{family}/{platform}/merged/` with `model.yaml`, `claims.json`, `api_surface.json`
2. Content pages must exist for the product (discovered from `config.yaml sites`)
3. If consuming an existing eval report: the report file must exist

> **Optional context gate** — if `scripts/skill_context.py` exists, run before step 1:
> ```bash
> python scripts/skill_context.py begin --skill S-41 --scope "{target}"
> ```

## Steps

### Step 1: Parse arguments

If two words: treat as `{family} {platform}`.
If `--eval-report {path}`: load the eval report directly (skip Step 2).

### Step 2: Run evaluation (unless consuming existing report)

Run S-25 (eval-page) across all content files for the product. Save the eval report.

If `scripts/content_eval.py` or equivalent exists:
```bash
python scripts/content_eval.py {family} {platform} --format json --remediation \
  > reports/content_eval/eval-{timestamp}.json
```

Note the report path from output.

### Step 3: Dry-run auto-fix (preview)

Before writing any changes, preview what would be fixed:

```
Auto-fix preview — {target}
  {file-path}:
    [FRONTMATTER] add missing 'date' field
    [CODE-FENCE]  line 47: ```py → ```python
    [PLACEHOLDER] line 89: remove "TODO: add example"
    [EVIDENCE]    refresh model_sha
```

Confirm the fixes look correct before proceeding.

### Step 4: Apply auto-fixes

For each finding in the eval report that has a deterministic fix:
- Apply the fix directly to the file
- Record the change in the remediation log

If `scripts/remediate.py` exists:
```bash
python scripts/remediate.py fix {eval-report-path}
```

Otherwise: apply fixes manually as agent-executed text transformations.

**Only touch files that have findings.** Do not reformat or clean up files with no findings.

### Step 5: Refresh evidence

For each modified file, update the `evidence:` frontmatter block using S-78
(evidence-enhance) or S-24 (evidence-cite):

```bash
# If script available:
python scripts/attach_evidence.py --files {modified-file-list}
```

Or invoke S-24 (evidence-cite) per modified file.

### Step 6: Report results

```
BATCH EVAL FIX — {target}
Files evaluated:  {total}
Files modified:   {count}

Findings triaged: {total}
Auto-fixed:       {count}
  Frontmatter fixes:  {count}
  Code fence fixes:   {count}
  Placeholder removals: {count}
  Evidence refreshes: {count}
Deferred to LLM:  {count} (use S-26 heal-page for these)
Deferred to human: {count}

Reports: {eval-report-path}, {remediation-report-path}
```

> **Optional context close** — if `scripts/skill_context.py` exists, run after the last step:
> ```bash
> python scripts/skill_context.py end --skill S-41 --status completed
> ```

## Post-conditions

- Only deterministic, safe fixes applied
- No LLM-generated content introduced
- Evidence blocks refreshed for modified files
- Remediation report saved to `reports/remediation/`
- No files outside allowed content paths were modified (path-guard S-01)

## Chaining

After batch-eval-fix, pages that still have FAIL findings (not auto-fixable) should be
addressed with S-26 (heal-page) for LLM-assisted repair or S-73 (manual-edit) for
operator-directed fixes.
