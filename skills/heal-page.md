---
name: heal-page
id: S-26
description: >
  Heal a low-quality content page (grade D or below from S-25) by applying
  targeted two-pass fixes: contradictions, unverified API references, missing
  evidence, structural issues, and golden conformance gaps.
args: "{content-file-path}"
---

# S-26: Heal Page — Fix Low-Quality Content

**Arguments**: $ARGUMENTS
Expected format: `{content-file-path}` — path to the content file to heal

## Purpose

Heal a page that received grade D or F from S-25 (eval-page). Applies targeted
fixes in two passes, then re-evaluates. Escalates to S-73 (manual-edit) if grade
does not improve after 2 attempts.

## Pre-conditions

1. S-25 (eval-page) eval report must exist for this page in `reports/eval/`
   (or the agent must be able to run eval-page to produce one)
2. Content file must exist
3. Knowledge model must exist: `knowledge/{family}/{platform}/merged/`
   with `claims.json`, `api_surface.json`, and optionally `formats.json`
4. Knowledge must not be stale — if stale, run S-14 (knowledge-update) first

> **Optional context gate** — if `scripts/skill_context.py` exists, run before step 1:
> ```bash
> python scripts/skill_context.py begin --skill S-26 --scope "{content-file-path}"
> ```

## Steps

### Step 1: Parse arguments

Extract `{content-file-path}` from $ARGUMENTS. Derive `{family}` and `{platform}`
from the path (the segments identifying the product in the knowledge directory).

### Step 2: Auto-refresh knowledge

Before loading any knowledge artifacts, ensure they are current.

If `scripts/merge.py` exists and `knowledge/{family}/{platform}/scout/model.yaml`
has a `stale_since` field set:
```bash
python scripts/merge.py {family} {platform}
```
- If it prints "refreshed": knowledge was rebuilt from the scout cache.
- If it prints "current": no action needed.
- If the script is absent or the clone cache is missing: warn but continue with
  existing knowledge artifacts.

### Step 3: Load evaluation report

Retrieve S-25 output for this page. If not available, run S-25 (eval-page) first.

If the eval report exists and the grade is C or above, report that healing is not
needed and exit.

### Step 4: Load knowledge artifacts

Read from `knowledge/{family}/{platform}/merged/`:
- `claims.json` — factual claims with confidence scores
- `api_surface.json` — verified class/method/property names
- `formats.json` — supported file formats (if present)
- `limitations.md` — known unimplemented features (if present)
- `index.json` — product index (if present)

Read from `knowledge/{family}/{platform}/`:
- `snippets/` — verified code examples (if directory exists)

### Step 5: Read current page content

Read the full content of the file at `{content-file-path}`.

### Step 6: Healing pass 1 — apply targeted fixes for each FAIL finding

Apply fixes in priority order:

| Finding type | Fix strategy |
|---|---|
| Contradicted claim | Remove or rewrite using correct information from `claims.json` |
| Unverified API reference | Replace with correct name from `api_surface.json`; if no match, remove and note gap |
| Contradicted format claim | Correct direction (import/export/both) or remove if unsupported in `formats.json` |
| Broken / missing structure | Rebuild section following page-type template; fix heading hierarchy |
| Missing frontmatter | Add required Hugo fields (`title`, `description`, `date`, `draft`, `type`) |
| Placeholder text | Replace with knowledge-grounded content or remove |
| Missing evidence citations | Match paragraphs to `claims.json` entries; mark for S-24 (evidence-cite) |

Golden conformance fixes (if conformance score < 0.55):
- Load `golden/_index.json` and find the matching golden page for this page's role/variant
- If `section_coverage` low → add missing golden sections with appropriate content
- If `section_order` low → reorder sections to match golden sequence
- If `block_type_coverage` low → add missing block types (code, list, table) per golden contract
- If `code_density_alignment` low → adjust code-to-prose ratio toward golden target

### Step 7: Update evidence frontmatter after pass 1

Refresh `evidence.model_sha`, `evidence.claims`, and `evidence.apis` to reflect
the post-pass-1 content.

### Step 8: Update provenance after pass 1

In the file's frontmatter `provenance:` block:
- Set `last_mechanism: heal-page`
- Do **not** change `auto_updatable` or `content_origin`

### Step 9: Ground-check after pass 1

Run S-23 (ground-check) on the healed file to detect any NEW FAIL findings
introduced by the pass-1 fixes that were not in the original eval report.

If new FAILs are found that were not in the pass-1 report: **halt and escalate**
to S-73 (manual-edit) — do not proceed with aggressive rewrites until the new
failures are understood. This protects against fixes that mask existing problems
while introducing new ones.

If ground-check is clean (no new FAILs): continue.

### Step 10: Re-evaluate after pass 1

Run S-25 (eval-page) on the healed file.

If grade is C or above: report success and exit (see Step 14).

### Step 11: Healing pass 2 (if still D or F)

Apply more aggressive fixes:
- Rewrite entire failing sections from scratch using claims and snippets
- Remove sections that cannot be fixed (better to be incomplete than wrong)
- Simplify code examples to only verified API calls from `api_surface.json`
- Add missing high-confidence claims (confidence >= 0.8) as new sections

### Step 12: Update provenance after pass 2

Repeat Step 8 (set `last_mechanism: heal-page`).

### Step 13: Re-evaluate after pass 2

Run S-25 (eval-page) on the healed file.

### Step 14: Log changes

Write a heal log to `reports/heal/{family}-{platform}-{slug}-{timestamp}.md`
with the fixes applied, grades before/after each pass, and the final outcome.

### Step 15: Final decision

- If grade C or above after either pass: **HEALED** — report success
- If still D or F after 2 passes: **ESCALATE** — do not attempt further automatic fixes.
  Invoke **S-73 (manual-edit)** for each escalated item. S-73 is the only sanctioned
  path for operator-directed targeted edits.

### Step 16: Report

```
HEAL PAGE — {content-file-path}
Initial grade: {letter}

Pass 1:
  Fixes applied: {count}
  - [{finding-type}]: {fix description}
  Ground-check: PASS | NEW FAILS FOUND (→ ESCALATED)
  Grade after pass 1: {letter}

Pass 2 (if needed):
  Fixes applied: {count}
  Grade after pass 2: {letter}

RESULT: {HEALED | ESCALATED}
Final grade: {letter}
Report: reports/heal/{report-filename}
```

> **Optional context close** — if `scripts/skill_context.py` exists, run after the last step:
> ```bash
> python scripts/skill_context.py end --skill S-26 --status {completed|escalated}
> ```

## Post-conditions

- If HEALED: page grade is C or above; ground-check passes; provenance updated
- If ESCALATED: page is flagged for human review via S-73; no further automatic changes
- All fixes are grounded in knowledge (no fabrication)
- Evidence frontmatter is current
- Heal log written to `reports/heal/`

## Error handling

| Error | Cause | Fix |
|---|---|---|
| Knowledge unavailable | Knowledge not bootstrapped | Run `/repo-scout {family} {platform}` then `/truth-merge` |
| `stale_since` set in model.yaml | Knowledge outdated | Run S-14 (knowledge-update) first |
| Grade not improved after pass 1 | Fix didn't address root cause | Pass 2 will attempt; if still failing → ESCALATE to S-73 |
| Still D/F after 2 passes | Page has structural issues beyond auto-repair | Escalate to S-73 (manual-edit) |
| Ground-check finds new FAILs | Pass-1 fix introduced new problems | ESCALATE immediately — do not proceed to pass 2 |
| No eval report and no eval script | Cannot assess quality | Run S-25 (eval-page) manually first |
| Content file is empty | Nothing to heal | Escalate to S-73 or delete and regenerate |
