<!-- CONTRACT: agent-executed
     purpose: remediate D/F grade pages by improving content to meet quality bar
     preconditions: grade_remediation_check.py report exists with D/F findings
     postcondition: target pages re-graded to C or above; no quality regressions introduced
     idempotent: yes — re-run on already-passing pages produces no-ops
     verified: 2026-06-12
-->
---
name: grade-remediate
id: S-102
description: >
  Remediate D/F grade content pages by improving page quality to meet the minimum
  grade bar. Scans for low-grade pages, analyzes root cause, applies targeted fixes,
  and re-grades.
args: "{family} {platform} [--grade-filter D,F] [--dry-run]"
---

# S-102: Grade Remediate — Fix D/F Grade Pages

**Arguments**: `{family} {platform}`
Expected format: `{family} {platform} [--grade-filter D,F] [--dry-run]`

## Purpose

After a knowledge refresh or content update cycle, some pages may be graded D or F
due to stale content, missing evidence, or thin body prose. This skill scans for such
pages and applies targeted improvements to bring them to grade C or above.

## Pre-conditions

1. `knowledge/{family}/{platform}/merged/` exists with current artifacts
2. `reports/refresh_review/{family}/{platform}/grade_remediation_report.json` exists
   (produced by `grade_remediation_check.py` in S-84 Step 9.6)
3. Grade D/F pages have been identified

## Steps

> **Skill context gate** — run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-101 --scope "*"
> ```

1. **Scan for D/F grade pages**:
   ```bash
   .venv/Scripts/python scripts/pipeline/commands/ops/grade_remediation_check.py {family} {platform} --grade-filter D,F --list
   ```
   Reads `reports/refresh_review/{family}/{platform}/grade_remediation_report.json`.
   Produces a list of pages to remediate.

2. **Classify root cause** for each D/F page:
   - `THIN_BODY` — insufficient prose; body word count below threshold
   - `STALE_EVIDENCE` — `evidence.model_sha` not current
   - `ORPHANED_CLAIMS` — `evidence.claims` references unknown claim IDs
   - `PHANTOM_APIS` — `evidence.apis` references unknown API members
   - `HASH_ONLY_REGRESSION` — grade dropped due to a mere body hash change with
     no actual content quality degradation (see Hash-Only Rejection Rule below)

3. **Apply targeted fix** based on root cause:
   - `THIN_BODY` → route to `/page-enhance {family} {platform} {slug}` (S-21)
   - `STALE_EVIDENCE` → update `evidence.model_sha` and re-run `attach_evidence`
   - `ORPHANED_CLAIMS` → run `/evidence-repair {slug}` (S-72)
   - `PHANTOM_APIS` → run `/evidence-repair {slug}` (S-72)
   - `HASH_ONLY_REGRESSION` → see rejection rule below (do NOT blindly re-grade)

4. **Re-grade after fix**:
   ```bash
   .venv/Scripts/python -m content_eval evaluate {family} {platform} --write-grade --files {page_path}
   ```
   Target: grade C or above. If page remains D/F after fix, escalate to S-73 (manual-edit).

5. **Verify no regressions** on neighboring pages:
   ```bash
   .venv/Scripts/python scripts/pipeline/commands/content/audit.py --files {page_path}
   ```

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-101 --status completed
> ```

## Hash-Only Rejection Rule

A page MUST NOT be automatically re-graded when the only reason for a D/F grade is
a **mere body hash change** — i.e., the `graded_content_hash` in frontmatter no longer
matches the current body content, but the actual prose quality has not degraded.

**Why this rule exists**: The content hash changes whenever body text is touched, even
for minor whitespace or formatting fixes. A grade downgrade triggered by a hash mismatch
alone (without substantive quality degradation) is a false positive.

**Detection**: If the page was previously graded B or above, and the current grade is D/F
solely because `graded_content_hash` changed (no new quality problems in the prose), the
root cause is `HASH_ONLY_REGRESSION`.

**Correct action**: Restore the correct grade by re-running the grader without treating
the hash mismatch as a quality failure. Do NOT add content just to inflate the grade.

## Error Handling

- If `grade_remediation_check.py` fails (exit 2): check that the `reports/` directory exists
- If page remains D/F after 2 enhancement attempts: escalate to human review via S-73
- If audit.py fails after fix: do not commit; route to S-72 (evidence-repair) first
