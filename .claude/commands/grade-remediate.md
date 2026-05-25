<!-- CONTRACT: agent-executed
Skill: S-96
Name: grade-remediate
Version: 1.0
Status: active
Trigger: /grade-remediate {family} {platform} [--grade-filter D,F] [--max N]
Outputs: grade_remediation_report.json, per-page repair evidence
Governed by: S-73 (manual-edit) for body changes; S-23 (content-check) for validation
-->

# S-96: Grade Remediate — Repair D/F Graded Pages

Scan `{family}/{platform}` for D/F graded pages and attempt controlled body repair for
CONTENT_FIXABLE findings. Produces a per-page decision record:
`GRADING_REPAIRED`, `GRADING_BLOCKED`, or `TASKCARD_CREATED`.

## Arguments

- `{family}` — product family (e.g. `cells`, `font`)
- `{platform}` — platform (e.g. `java`, `python`)
- `--grade-filter` — comma-separated grades to target (default: `D,F`)
- `--max` — maximum pages to process in this run (default: 10)
- `--stale-grades` — also include pages with stale graded_content_hash

## Step 1: Scan for grade issues

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python \
    scripts/pipeline/commands/ops/grade_remediation_check.py \
    {family} {platform} \
    --grade-filter {grade_filter_arg} \
    --stale-grades \
    --list
```

Writes: `reports/refresh_review/{family}/{platform}/grade_remediation_report.json`

If no issues found: emit summary and exit 0. No further steps required.

## Step 2: Fresh evaluation per page

For each page in the grade report (up to `--max`):

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python -m scripts.pipeline.content_eval evaluate \
    --files {page_path} --format json --remediation
```

Classify each finding:

| Finding class | Action |
|---------------|--------|
| CONTENT_FIXABLE | Proceed to Step 3 (body repair via S-73) |
| METADATA_ONLY | Proceed to Step 4 (attach_evidence.py) |
| PIPELINE_CLASS | Proceed to Step 5 (taskcard) |
| EVALUATOR_FALSE_POSITIVE | Skip; log as FALSE_POSITIVE |
| STALE_GRADE | Re-run evaluator; may become CONTENT_FIXABLE |

## Step 3: Body repair for CONTENT_FIXABLE findings

**For each CONTENT_FIXABLE page**:

3.1. Invoke S-73 (manual-edit):
```
/manual-edit {page_path}
```
S-73 applies path-guard and pre-edit validation.

3.2. After S-73 completes, run S-23 (content-check):
```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python \
    scripts/pipeline/commands/content/audit.py --files {page_path}
```

3.3. Re-run evaluator to confirm improvement:
```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python -m scripts.pipeline.content_eval evaluate \
    --files {page_path} --format json
```

3.4. If body changed AND grade improved, persist grade:
```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python -m scripts.pipeline.content_eval evaluate \
    --files {page_path} --write-grade-if-policy-met
```

3.5. Record decision: `GRADING_REPAIRED`

**If S-73 is blocked by pre-tool-use hook**:
- Record hook output verbatim as governed-gate evidence
- Record decision: `GRADING_BLOCKED`
- Continue to next page

## Step 4: Metadata-only fixes (METADATA_ONLY)

For pages where all failures are metadata/evidence block issues:

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python \
    scripts/pipeline/commands/content/attach_evidence.py \
    --file {page_path} \
    --knowledge-dir knowledge/{family}/{platform}/merged
```

Record decision: `GRADING_REPAIRED` (if evidence attached) or `GRADING_BLOCKED`

## Step 5: Taskcard creation for PIPELINE-class findings

For pages where grade failure is caused by pipeline issues (missing knowledge,
claim extraction gap, evaluator false-positive):

Add taskcard to `backlog/BACKLOG.md`:
```markdown
| GRADE-{family}-{platform}-{slug} | knowledge | MEDIUM | Grade {grade}: {page_path} — {failure_reason} | OPEN |
```

Record decision: `TASKCARD_CREATED`

## Step 6: Update page_decisions.json

For pages processed in this run, extend `reports/refresh_review/{family}/{platform}/page_decisions.json`
with extended decision vocabulary:

```json
{
  "{page_path}": {
    "decision": "GRADING_REPAIRED|GRADING_BLOCKED|TASKCARD_CREATED",
    "grade_before": "D",
    "grade_after": "C",
    "body_hash_changed": true,
    "remediation_timestamp": "ISO-8601"
  }
}
```

## Step 7: Summary report

Emit summary:
```
Grade remediation complete for {family}/{platform}:
  Scanned:             {total}
  GRADING_REPAIRED:    {count}
  GRADING_BLOCKED:     {count}
  TASKCARD_CREATED:    {count}
  FALSE_POSITIVE:      {count}
```

Write: `reports/refresh-pipeline-investigation/05-grading-remediation-results.md`

## Acceptance gate

At least one of:
- Net finding count decreases (WARN or FAIL count goes down)
- Grade letter improves (e.g. D -> C)
- False-positive evaluator issue proven with evidence and taskcarded
- Source-gap or external gate documented with exact blocker

A mere body hash change with net-neutral or increased finding count
is NOT sufficient for GRADING_REPAIRED status.

## Integration with S-84

This skill is invoked at Step 9.6 of S-84 (refresh-product):

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python \
    scripts/pipeline/commands/ops/grade_remediation_check.py \
    {family} {platform} --grade-filter D,F --list
```

If issues found: invoke `/grade-remediate {family} {platform} --grade-filter D,F --max 10`

Grade remediation failures do NOT block the refresh commit. They generate taskcards for
follow-up remediation.
