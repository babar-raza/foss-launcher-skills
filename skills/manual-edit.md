---
name: manual-edit
id: S-73
description: >
  Apply an operator-specified targeted change to a single content file under full governance.
  Validates, applies, and verifies the change within the skill chain.
args: "{relative-file-path} --scope {scope} --intent \"{intent}\" [--section \"{heading}\"] [--evidence \"{id}\"]"
---

<!-- CONTRACT: agent-executed
     purpose: apply operator-specified targeted content edit under full governance
     preconditions: active session; target file exists under content/; knowledge model current
     postcondition: page edited with evidence attached, audit passed, and provenance updated
     idempotent: no — operator intent varies; grade outcomes depend on edit content
-->

# S-73: Manual Edit — Operator-Directed Targeted Content Edit

**Arguments**: $ARGUMENTS
Expected format:
```
{relative-file-path} --scope {scope} --intent "{intent}" [--section "{heading}"] [--evidence "{id}"]
```

| Parameter | Required | Values |
|-----------|----------|--------|
| `{relative-file-path}` | Yes | Path from repo root to the content file |
| `--scope` | Yes | `frontmatter-only` \| `body-wording` \| `code-snippet` \| `section-replacement` \| `full-remediation` |
| `--intent` | Yes | Natural language specification: what to change and why |
| `--section` | Conditional | H2 or H3 heading text; **required** for `code-snippet` and `section-replacement` scopes |
| `--evidence` | Conditional | Claim ID or API token; **required** for `full-remediation` scope |

**Examples:**
```
# Fix a frontmatter description
/manual-edit content/docs/3d/python/developer-guide/rendering.md \
  --scope frontmatter-only \
  --intent "Set description to 'Render 3D scenes in Python with the FOSS library.'"

# Fix a specific sentence in the body
/manual-edit content/blog/3d/python/introducing-3d-for-python/index.md \
  --scope body-wording \
  --intent "Replace 'The library supports over 50 formats' with 'The library supports FBX, glTF, OBJ, STL, and additional formats'"

# Replace code block in a named section
/manual-edit content/kb/3d/python/how-to-load-3d-models-in-python.md \
  --scope code-snippet \
  --section "Load OBJ Files" \
  --intent "Replace the code block with the snippet from knowledge/3d/python/snippets/load_obj.py"

# Rewrite an entire section
/manual-edit content/docs/cells/python/developer-guide/working-with-charts.md \
  --scope section-replacement \
  --section "Prerequisites" \
  --intent "Replace the Prerequisites section with: install via pip install {package-name}"

# Full targeted remediation (requires evidence)
/manual-edit content/reference/3d/java/Scene.md \
  --scope full-remediation \
  --intent "Remove the incorrect statement claiming Scene extends Node; it extends A3DObject" \
  --evidence "CLM-3d-a1f23b"
```

---

## Purpose

Apply an operator-specified targeted change to a single content file under full governance.
Unlike S-26 (heal-page), S-21 (page-enhance), and S-20 (page-update) — which are agent-decided
repairs — S-73 applies exactly what the operator specifies. The operator determines what to change;
the skill validates, applies, and verifies that change within the skill chain.

Use S-73 for:
- Typo or wording corrections where the operator knows the exact change
- Frontmatter field updates (title, description, date, weight, etc.)
- Code block replacements where the correct snippet is already known
- Section rewrites directed by human editorial judgment
- Escalated items from S-26 (heal-page) or automated repair skills
- Human-authored content requiring targeted correction

Do **not** use S-73 for:
- Multi-file changes (invoke S-73 once per file)
- Changes where the agent should decide what to fix (use S-26 or S-21 instead)
- Knowledge-driven updates after an upstream change (use S-20 instead)
- Onboarding a page written directly by a human (use S-66 instead)

---

## Scope Boundaries

| Scope | May touch | Must not touch |
|-------|-----------|----------------|
| `frontmatter-only` | Non-system YAML fields: `title`, `description`, `date`, `weight`, `tags`, `categories`, `icon`, `linktitle`, `subtitle`, `keywords`, `author`, `draft`, `summary` | `evidence.*`, `grade`, `graded_at`, `graded_model_sha`, `graded_evaluators`, `provenance.*` |
| `body-wording` | Prose sentences and paragraphs only | Code blocks, frontmatter, section headings (`##`, `###`) |
| `code-snippet` | Single code block inside `--section` | Prose, frontmatter, other code blocks, the heading line itself |
| `section-replacement` | All content from `--section` heading to the next heading of equal or higher level | Other sections, frontmatter |
| `full-remediation` | Any content element named in `--intent` | `evidence.*`, `grade*`, `provenance.*` (always system-managed) |

**Minimal-edit principle:** Touch only what is named in `--intent`. Do not fix adjacent issues noticed
during the edit. Do not reformat unrelated content. Do not opportunistically improve sections not specified.

---

## Pre-conditions

1. The file exists at `{relative-file-path}` under the content directory
2. Path-guard check passes for the target file (invoke S-01)
3. The file path resolves to one of the configured site sections (from `config.yaml sites` keys)
4. `{family}` and `{platform}` are derivable from the file path
5. `knowledge/{family}/{platform}/model.yaml` exists (required for freshness check)

---

## Steps

> **Optional context gate** — if `scripts/skill_context.py` exists, run before step 1:
> ```bash
> python scripts/skill_context.py begin --skill S-73 --scope "*"
> ```

### Step 1: Parse and validate arguments

Extract all arguments from $ARGUMENTS:
- `target_file` — the relative file path
- `edit_scope` — one of the five scope values
- `edit_intent` — the full intent string
- `target_section` — (if provided)
- `evidence_justification` — (if provided)

Validate:
- `edit_scope` must be one of the five exact values. If not, **REFUSE**: "Unknown scope '{value}' — valid scopes: frontmatter-only, body-wording, code-snippet, section-replacement, full-remediation"
- `section-replacement` and `code-snippet` require `--section`. If absent, **REFUSE**: "Scope '{scope}' requires --section to identify the target heading"
- `full-remediation` requires `--evidence`. If absent, **REFUSE**: "Scope full-remediation requires --evidence to justify the change"

Emit capability state:
```
CAPABILITY ASSESSMENT — manual-edit S-73
State: FULL
Skills: S-73 (manual-edit), S-01 (path-guard), S-23 (ground-check), S-24 (evidence-cite)
Action: Apply operator-specified targeted edit under S-73 governance
```

### Step 2: Path guard check

Invoke S-01 (path-guard) on `{target_file}`.

If `scripts/path_guard.py` exists:
```bash
python scripts/path_guard.py {target_file}
```

- Exit 0: proceed
- Exit 2 (DENY): **halt immediately** — "Path guard denied write to '{target_file}'. Reason: {guard_reason}. Do not bypass."

Otherwise: verify the file is under a content directory listed in `config.yaml sites` section.

### Step 3: File existence and section detection

1. Confirm the file exists. If not: **REFUSE** — "File not found: {target_file}"

2. Detect section from path — read site keys from `config.yaml sites` section:
   - Map the file path prefix to the matching site key (e.g. `content/docs/`, `content/blog/`, etc.)
   - If the path does not match any configured site key: **REFUSE** — "Cannot determine section from path '{target_file}'. S-73 operates only on files under configured content directories (see config.yaml sites)"

3. Extract `{family}` and `{platform}` from the path (typically the subdirectory segments after the site prefix).

### Step 4: Load section rules

Read the site sections from `config.yaml`. Apply any section-specific rules documented in the repo's
`AGENTS.md` for the matched section. Common general rules:
- Evidence block required for documentation, blog, knowledge base, and reference pages
- Products/landing pages: evidence block typically not required
- `draft` field required for blog posts
- Index shortcodes vary by section

If `edit_scope = code-snippet` or `edit_scope = section-replacement` for a section that discourages
code examples (e.g. products/landing pages): warn the operator and halt if not confirmed.

### Step 5: Knowledge freshness check

```bash
python scripts/merge.py {family} {platform}
```

If the script is unavailable, read `knowledge/{family}/{platform}/merged/model.yaml` and check
`stale_since`. If stale: **halt** — "Knowledge for {family}/{platform} is stale. Run S-12
(knowledge-diff) → S-14 (knowledge-update) before editing content."

### Step 6: Auto-updatable check

Read the file's frontmatter. If `provenance.auto_updatable: false`:

```
Warning: This page has auto_updatable: false (human-authored content).
Applying S-73 will mark it as skill-edited in provenance.
Proceed? [Y/N]
```

Halt if operator responds N.

### Step 7: Capture pre-edit grade

Run S-25 (eval-page) on the file to capture the baseline grade, or use S-23 (ground-check) as proxy:

```bash
python scripts/content_eval.py --files {target_file} --format json
```

Store result as `pre_grade`. If unavailable, run ground-check and record as "unknown (audit proxy)".

### Step 8: Validate intent against knowledge

For scopes `body-wording`, `code-snippet`, `section-replacement`, `full-remediation`:

1. Load `knowledge/{family}/{platform}/merged/api_surface.json`
2. Scan `--intent` for backtick-quoted identifiers (pattern: `` `Identifier` ``)
3. For each identifier found: verify it exists in `api_surface.json`
   - If not found: **REFUSE** — "Proposed text references unknown API token '`{token}`' — not in api_surface.json for {family}/{platform}. Correct the intent or update the knowledge model first (S-14)."

4. Invoke S-33 (change-guard) if available:
   ```bash
   python scripts/change_guard.py {family} {platform} "{edit_intent_first_200_chars}"
   ```
   - DENY: **REFUSE** with the guard's reason

### Step 9: Apply the edit

Read the current file. Apply the change described in `--intent` per scope rules:

**`frontmatter-only`**:
Locate the frontmatter YAML block. Find the field(s) named in `--intent`. Apply the new value.
Preserve all other frontmatter fields byte-for-byte. Do not reorder keys.
Refuse if `--intent` names a system-managed field (`evidence`, `grade`, `graded_at`,
`graded_model_sha`, `provenance`).

**`body-wording`**:
Locate the target sentence or paragraph as described in `--intent`. If it appears more than once
in the file: **REFUSE** — "Target text is not unique in the file. Provide longer surrounding context
or use scope section-replacement with --section to narrow the target."
Apply the replacement text. Do not touch code blocks, headings, or frontmatter.

**`code-snippet`**:
Locate the heading matching `--section`. Within that section, find the first code block
(triple-backtick fence). If none found: **REFUSE** — "No code block found in section '{target_section}'."
Replace the code fence body with the operator-specified snippet. Preserve the opening fence language identifier.

**`section-replacement`**:
Locate the heading matching `--section` (exact H2 `## {section}` or H3 `### {section}` match).
If not found: **REFUSE** — "Heading '{target_section}' not found in file."
Replace all content from that heading line (exclusive — keep the heading) to the start of the next
heading of equal or higher level (exclusive) with the operator-specified content.
If operator explicitly specifies a new heading text, replace the heading line too.

**`full-remediation`**:
Apply all changes described in `--intent` to the elements named. Touch nothing not explicitly named.
The operator bears responsibility for completeness; the skill validates but does not second-guess scope.

Write the modified content back to the file.

### Step 10: Post-edit path guard re-check

Re-invoke S-01 (path-guard) or `python scripts/path_guard.py {target_file}`.
If DENY: this indicates an unexpected path mutation. **Revert the write, halt.**

### Step 11: Ground-check (audit)

Invoke S-23 (ground-check) on the updated file:

```bash
python scripts/ground_check.py --files {target_file}
```

If unavailable, validate frontmatter structure and confirm no structural regressions were introduced.

If FAIL:
- **Revert the edit** (restore pre-edit file content)
- **Halt** — "Post-edit ground-check FAIL — edit has been reverted. Fix the proposed content and retry.\nFindings:\n{findings}"

### Step 12: Frontmatter validation

Validate the YAML frontmatter structure: parse it with a YAML parser and confirm no duplicate keys,
no malformed values. If errors: **revert, halt** with the validation errors listed.

### Step 13: Refresh evidence block

For sections that require an evidence block, update `evidence.model_sha`, `evidence.claims`,
and `evidence.apis` to reflect the post-edit content.

If `scripts/attach_evidence.py` exists:
```bash
python scripts/attach_evidence.py --files {target_file}
```

Otherwise: invoke S-24 (evidence-cite) or S-78 (evidence-enhance) to refresh citations.

Do not perform this step for sections without evidence blocks (e.g. products/landing pages).

### Step 14: Update provenance

In the file's frontmatter `provenance:` block:
- Set `last_mechanism: manual-edit-skill`
- Set `reviewed: false` (operator-directed but not peer-reviewed)
- Do **not** change `auto_updatable`
- Do **not** downgrade `content_origin` from `human-authored`

### Step 15: Re-evaluate and check for grade regression

Run S-25 (eval-page) or S-23 (ground-check) again and store as `post_grade`.

**No-downgrade check**: If `post_grade` is lower than `pre_grade` by more than one letter:
```
Warning: Grade regression detected: {pre_grade} → {post_grade}
The edit reduced content quality. Review the diff and confirm you want to keep this change.
Proceed? [Y/N]
```
If operator responds N: **revert the edit** (restore pre-edit content, do not update evidence or provenance).

Update the grade frontmatter field if grade-tracking is active.

### Step 16: Write audit trail

```bash
mkdir -p reports/manual-edits
```

Write the audit record to `reports/manual-edits/{YYYY-MM-DD}-{file-slug}-{timestamp}.json`:

```json
{
  "skill": "S-73",
  "target_file": "{relative path}",
  "family": "{family}",
  "platform": "{platform}",
  "section": "{detected section key}",
  "edit_scope": "{scope}",
  "edit_intent": "{full intent string}",
  "target_section_heading": "{heading or null}",
  "evidence_justification": "{CLM-xxx or null}",
  "pre_grade": "{A|B|C|D|F|unknown}",
  "post_grade": "{A|B|C|D|F|unknown}",
  "audit_result": "PASS|FAIL",
  "audit_findings": [],
  "edit_applied": true,
  "reverted": false,
  "provenance_mechanism": "manual-edit-skill",
  "executed_at": "ISO-8601 timestamp"
}
```

### Step 17: Report

```
MANUAL EDIT — {target_file}
Section:  {detected section key}
Scope:    {edit_scope}
Intent:   {edit_intent}

Pre-edit grade:  {pre_grade}
Post-edit grade: {post_grade}

Audit:     {PASS|FAIL}
Evidence:  updated (model_sha: {sha})  [or: N/A for sections without evidence]
Provenance: last_mechanism → manual-edit-skill

Edit applied:  {YES|NO (reverted)}
Audit trail:  reports/manual-edits/{filename}.json

RESULT: {APPLIED|REVERTED|REFUSED}
Reason (if not APPLIED): {reason}
```

---

> **Optional context close** — if `scripts/skill_context.py` exists, run after the last step:
> ```bash
> python scripts/skill_context.py end --skill S-73 --status completed
> ```

## Post-conditions

- If APPLIED:
  - File content reflects exactly the operator-specified change and nothing else
  - Ground-check (S-23) passes on the modified file
  - Evidence frontmatter is current (model_sha, claims, apis)
  - `provenance.last_mechanism = manual-edit-skill`
  - Audit trail written to `reports/manual-edits/`
- If REVERTED: file is byte-for-byte identical to pre-edit state; audit trail written with `reverted: true`
- If REFUSED: file is untouched; no audit trail written; refusal reason printed to console

---

## Refusal and halt conditions

| Condition | Response |
|-----------|----------|
| Unknown `edit_scope` value | REFUSE |
| `section-replacement` or `code-snippet` without `--section` | REFUSE |
| `full-remediation` without `--evidence` | REFUSE |
| Path guard DENY | HALT (no recovery) |
| File not found | REFUSE |
| Path does not map to known section | REFUSE |
| Knowledge stale | HALT — run knowledge-update first |
| API token in `--intent` not in `api_surface.json` | REFUSE |
| Change-guard DENY | REFUSE |
| `--section` heading not found in file | REFUSE |
| Target text not unique (`body-wording`) | REFUSE |
| No code block in target section (`code-snippet`) | REFUSE |
| `--intent` names a system-managed frontmatter field | REFUSE |
| Post-edit ground-check FAIL | REVERT and HALT |
| Frontmatter YAML validation errors | REVERT and HALT |
| Grade regression > 1 letter, operator declines | REVERT |

### What S-73 will never do

- Generate alternative text via LLM (use S-26 or S-21 if the agent should decide what to fix)
- Edit more than one file per invocation
- Modify `evidence.*`, `grade*`, or `provenance.*` via operator intent (these are system-managed)
- Operate on files outside the configured content directories
- Proceed when knowledge is confirmed stale
- Skip ground-check or frontmatter validation for any reason
- Be invoked programmatically by another skill (always operator-invoked)

---

## Integration with remediation flows

S-73 is the sanctioned path for human-escalated items from all automated repair skills:

| Upstream source | Escalation mechanism | S-73 role |
|----------------|---------------------|-----------|
| S-26 (heal-page) | Grade does not improve after 2 passes → escalation | Operator reviews the page, specifies the fix, invokes S-73 |
| Batch repair skills | Human-queue items | Operator processes each queue item via S-73 |
| Content audit findings | Manual review items | Operator formulates the specific change, invokes S-73 |

S-73 produces an audit trail at `reports/manual-edits/` that references the originating escalation
item, creating an end-to-end traceable remediation record.

---

## Error handling

| Error | Action |
|-------|--------|
| Knowledge model missing | Abort — do not edit without knowledge grounding |
| Ground-check script not found | Treat as BROKEN skill condition; revert any pending write; report |
| evidence-cite/enhance failure | Revert edit; report as post-edit pipeline error |
| `content_eval` unavailable | Proceed with ground-check as grade proxy; log caveat |
| File write permission error | Halt; report filesystem error |
