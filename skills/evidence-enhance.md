---
name: evidence-enhance
id: S-78
description: >
  Improve section-level evidence coverage on content pages that already pass validation
  (ground-check PASS, grade A or B). Evidence frontmatter only — body content unchanged.
args: "{content-file-path}"
---

# S-78: Evidence Enhance — Improve Section Evidence Coverage on Passing Pages

**Arguments**: $ARGUMENTS
Expected format: `{content-file-path}`

## Purpose

Improve evidence coverage on a content page that **already passes validation**
(S-23 ground-check PASS, grade A or B). This skill increases the breadth and
specificity of the `evidence:` frontmatter block — attaching more claims and API
references that the page discusses but hasn't yet cited.

Use S-72 (evidence-repair) instead if the page is blocked by validators or has
audit failures. S-78 and S-72 have mutually exclusive preconditions.

**Critical scope boundary**: This skill ONLY modifies the `evidence:` and optionally
`provenance:` blocks in the YAML frontmatter. It NEVER modifies page title, description,
body content, headings, code blocks, or any prose text.

## Pre-conditions

1. File exists under the content directory
2. File is an English source file (not a locale translation variant)
3. Knowledge model exists at `knowledge/{family}/{platform}/merged/` with
   `model.yaml` (`stale_since: null`), `claims.json`, and `api_surface.json`
4. **Pre-flight ground-check passes** — run S-23 (ground-check) first:
   - If FAIL: **HALT** — redirect to S-72 (evidence-repair)
5. Evidence coverage is incomplete (not all detectable API references are cited)

> **Optional context gate** — if `scripts/skill_context.py` exists, run before step 1:
> ```bash
> python scripts/skill_context.py begin --skill S-78 --scope "{content-file-path}"
> ```

## Steps

### Step 1: Capture baseline

Record current evidence coverage: how many claims and API references are cited,
and the current ground-check status and grade.

### Step 2: Auto-refresh knowledge (if stale)

If `stale_since` is set in `model.yaml` and `scripts/merge.py` exists:
```bash
python scripts/merge.py {family} {platform}
```

### Step 3: Run auto-attach (if script available)

If `scripts/attach_evidence.py` exists:
```bash
python scripts/attach_evidence.py --files {content-file-path} --force
```

If the script is absent: proceed to manual population (Step 4).

### Step 4: Manual evidence population (when script absent or coverage still low)

Load knowledge artifacts:
- `knowledge/{family}/{platform}/merged/claims.json`
- `knowledge/{family}/{platform}/merged/api_surface.json`

Scan the page content for:
- API class names, method names, property names (in code blocks and prose)
- Factual claims about the product that match entries in `claims.json`

For each new match:
- **Only cite claims/APIs that exist in the knowledge model** — never invent
- Match API refs to `api_surface.json` entries exactly (ClassName.method)
- Match claim refs to `claim_id` values in `claims.json`

Add new matches to `evidence.claims` and `evidence.apis` (preserving existing entries).

### Step 5: Post-attach ground-check

Run S-23 (ground-check) on the updated file.
- If FAIL: **revert the file** to its pre-Step-3 state and report ESCAPED
- If PASS: continue

### Step 6: Validate frontmatter structure

Check that the frontmatter YAML is valid (parse it; confirm no duplicate keys).
If invalid: revert and report ESCAPED.

### Step 7: Do NOT update provenance.last_mechanism

Evidence-only attachment does not constitute a content change and must not update
`provenance.last_mechanism`. The existing value is preserved.

### Step 8: Re-check grade

If grade decreased: **revert** and report ESCAPED. Evidence enhancement must not
lower quality.

### Step 9: Report

```
EVIDENCE ENHANCE — {content-file-path}

Before: {A} APIs, {C} claims cited
After:  {A'} APIs, {C'} claims cited

Result: ENHANCED | NO_CHANGE | ESCAPED
Grade:  {before} → {after} (must not decrease)
```

> **Optional context close** — if `scripts/skill_context.py` exists, run after the last step:
> ```bash
> python scripts/skill_context.py end --skill S-78 --status completed
> ```

## Post-conditions

- Ground-check (S-23) still passes
- Grade is unchanged or improved
- `provenance.last_mechanism` is unchanged (evidence-only operation)
- Page body content is byte-for-byte identical to pre-skill state

## Error handling

| Condition | Action |
|---|---|
| Pre-flight ground-check FAIL | HALT; redirect to S-72 (evidence-repair) |
| Knowledge stale | HALT; redirect to S-14 (knowledge-update) |
| Post-attach ground-check FAIL | Revert file; report ESCAPED |
| Frontmatter validation fails | Revert file; report ESCAPED |
| Grade decreases | Revert file; report ESCAPED |
| Coverage already complete (no new matches) | Report NO_CHANGE; no file writes |

## Never do

- Modify page title, body, headings, code blocks, or prose
- Invent claim IDs not present in `claims.json`
- Invent API refs not present in `api_surface.json`
- Run on locale translation files
- Proceed when knowledge is stale
- Skip the post-attach ground-check
- Accept a grade decrease as an acceptable outcome
