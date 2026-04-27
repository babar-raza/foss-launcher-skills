---
name: evidence-repair
id: S-72
description: >
  Repair broken or empty evidence frontmatter blocks on content pages that fail
  validation. Operates on evidence frontmatter only — never modifies page body content.
args: "{content-file-path} [additional-paths ...] [--dry-run] [--scope claims|apis|both]"
---

# S-72: Evidence Repair — Repair Evidence Frontmatter for Validator-Blocked Pages

**Arguments**: $ARGUMENTS
Expected format: `{content-file-path} [additional-paths ...]`

Optional flags:
- `--dry-run` — report what would change without writing any files
- `--scope claims|apis|both` (default: `both`)

## Purpose

Repair the `evidence:` frontmatter block on a content page that is blocked by a
pre-commit validator or audit check because `evidence.claims` or `evidence.apis`
is empty or malformed.

**Critical scope boundary**: This skill ONLY modifies the `evidence:` and `provenance:`
blocks in the YAML frontmatter. It NEVER modifies page title, description, body content,
headings, code blocks, or any prose text.

**Relationship to S-78**: S-72 handles validator-blocked pages (audit FAIL). S-78
handles passing pages with incomplete section evidence. Their pre-conditions are
mutually exclusive.

## Pre-conditions

1. Target file(s) exist under the content directory
2. Knowledge model must exist at `knowledge/{family}/{platform}/merged/` with
   `model.yaml`, `claims.json`, and `api_surface.json`
3. Knowledge must not be stale — if `stale_since` is set in `model.yaml`, run
   S-14 (knowledge-update) first
4. File must be an English source file — do not apply to locale translation variants

> **Optional context gate** — if `scripts/skill_context.py` exists, run before step 1:
> ```bash
> python scripts/skill_context.py begin --skill S-72 --scope "{target}"
> ```

## Steps

### Preflight check

For each file:
1. Confirm file exists under an allowed content path (run path-guard S-01)
2. Confirm file is English source (reject locale variants like `page.fr.md`)
3. Derive `{family}` and `{platform}` from the file path
4. Confirm `knowledge/{family}/{platform}/merged/model.yaml` is present and
   `stale_since` is null — **HALT** if stale (redirect to S-14)
5. Confirm `claims.json` and `api_surface.json` exist

### Stage 1: Auto-attach (script-driven)

If `scripts/attach_evidence.py` exists:
```bash
python scripts/attach_evidence.py --files {path} --force
```
Skip if `--dry-run`; report what would happen instead.

If the script is absent: skip to Stage 2 (reasoning-based).

After Stage 1, run S-23 (ground-check):
- If passes → report **REPAIRED (auto)** and stop for this file
- If still fails → proceed to Stage 2

### Stage 2: Reasoning-based population (knowledge-grounded)

1. **Load knowledge artifacts**:
   - Read `knowledge/{family}/{platform}/merged/claims.json`
   - Read `knowledge/{family}/{platform}/merged/api_surface.json`

2. **Read current page content** in full

3. **Populate `evidence.claims`** (if claims are empty or gap is claims-related):
   - Scan the page for factual claims it makes about the product
   - For each claim, find the matching `claim_id` in `claims.json`
   - Only add claim IDs that exist in `claims.json` — **never invent IDs**
   - Match by comparing `claim.text` or `claim.description` to page prose
   - Include 2–8 most relevant claim IDs
   - If no claims can be confidently matched: skip (proceed to safe-escape)
   - **Never add a claim ID you cannot trace to a specific passage in the page**

4. **Populate `evidence.apis`** (if apis are empty or gap is apis-related):
   - Scan the page for API class names, method names, or property names (in code blocks and prose)
   - For each API mention, find the matching entry in `api_surface.json`
   - Only add API refs that exist in `api_surface.json` — **never invent refs**
   - Match class names, qualified names (`ClassName.method`), or enum values exactly
   - **Never add an API ref you cannot trace to a specific passage in the page**

5. **Write updated evidence block**:
   - Update `evidence.model_sha` from `merged/model.yaml` `repo_sha` field
   - Set `provenance.last_mechanism: evidence-attach`
   - Do NOT touch: page title, body, headings, code blocks, any prose

6. Run S-23 (ground-check):
   - If passes → report **REPAIRED (reasoning)** and stop
   - If still fails → proceed to Safe-Escape

### Safe-escape — when confidence is insufficient

Activate when Stage 2 cannot confidently populate claims or apis (e.g., introductory
prose with no traceable API surface):

1. Set `provenance.content_origin: manual-remediation` in frontmatter
2. Do NOT modify `evidence.claims` or `evidence.apis` (leave them empty — do not guess)
3. Set `provenance.last_mechanism: evidence-attach`
4. Append an escalation entry to `reports/evidence-repair/needs-human-{YYYYMMDD}.md`
5. Report **ESCAPED**

### Report (one entry per file)

```
EVIDENCE REPAIR — {file-path}
  Product: {family}/{platform}
  Knowledge SHA: {model_sha}

  Stage 1 (auto-attach): {RESOLVED | PARTIAL | SKIPPED | FAILED}
  Stage 2 (reasoning):   {RESOLVED | PARTIAL | SKIPPED | N/A}
  Safe-escape:           {APPLIED | NOT NEEDED}

  Result: REPAIRED (auto) | REPAIRED (reasoning) | ESCAPED | REFUSED

  Changes:
    evidence.claims: {[] → [CLM-xxx, ...] | unchanged}
    evidence.apis:   {[] → [ClassName.method, ...] | unchanged}
    provenance.content_origin: {unchanged | manual-remediation}
    provenance.last_mechanism: evidence-attach
```

> **Optional context close** — if `scripts/skill_context.py` exists, run after the last step:
> ```bash
> python scripts/skill_context.py end --skill S-72 --status completed
> ```

## Post-conditions

- REPAIRED (auto|reasoning): validators pass; evidence is populated with verified values only
- ESCAPED: marked for human follow-up; `provenance.content_origin: manual-remediation`
- REFUSED: no changes made; refusal reason printed
- Page body content is identical to input (no prose changes)
- `evidence.model_sha` matches current `merged/model.yaml.repo_sha`
- Escalation entries written for all ESCAPED files

## Refusal conditions

| Condition | Action |
|---|---|
| Knowledge model missing | REFUSE — redirect to S-14 (knowledge-update) |
| Knowledge model stale (`stale_since` set) | REFUSE — redirect to S-12 + S-14 |
| File not under an allowed content path | REFUSE |
| Locale translation variant file | REFUSE — run on English source only |

## Never do

- Modify page title, body, headings, code blocks, or prose
- Invent or guess claim IDs — all must exist in `claims.json`
- Invent or guess API refs — all must exist in `api_surface.json`
- Apply to locale translation files
- Skip post-edit ground-check
- Call itself recursively or enter an infinite retry loop
