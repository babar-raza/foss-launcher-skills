---
name: manual-edit
description: >
  Apply an operator-specified targeted content edit to a single file under full governance:
  path-guard, evidence refresh, provenance update, audit trail, revert-on-failure.
args: "{relative-file-path} --scope {scope} --intent \"{intent}\" [--section \"{heading}\"] [--evidence \"{id}\"]"
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# S-73: Manual Edit — Operator-Directed Targeted Content Edit

**Arguments**: $ARGUMENTS
Expected format:
```
{relative-file-path} --scope {scope} --intent "{intent}" [--section "{heading}"] [--evidence "{id}"]
```

| Parameter | Required | Values |
|-----------|----------|--------|
| `{relative-file-path}` | Yes | Path from repo root, e.g. `content/docs.aspose.org/en/3d/python/developer-guide/rendering.md` |
| `--scope` | Yes | `frontmatter-only` \| `body-wording` \| `code-snippet` \| `section-replacement` \| `full-remediation` |
| `--intent` | Yes | Natural language specification: what to change and why |
| `--section` | Conditional | H2 or H3 heading text; **required** for `code-snippet` and `section-replacement` scopes |
| `--evidence` | Conditional | CLM-xxx claim ID or API token; **required** for `full-remediation` scope |

**Examples:**
```
# Fix a frontmatter description
/manual-edit content/docs.aspose.org/en/3d/python/developer-guide/rendering.md \
  --scope frontmatter-only \
  --intent "Set description to 'Render 3D scenes in Python with Aspose.3D FOSS.'"

# Fix a specific sentence in the body
/manual-edit content/blog.aspose.org/3d/python/introducing-aspose-3d-foss-for-python/index.md \
  --scope body-wording \
  --intent "Replace 'The library supports over 50 formats' with 'The library supports FBX, glTF, OBJ, STL, and additional formats'"

# Replace code block in a named section
/manual-edit content/kb.aspose.org/en/3d/python/how-to-load-3d-models-in-python.md \
  --scope code-snippet \
  --section "Load OBJ Files" \
  --intent "Replace the code block with the snippet from knowledge/3d/python/snippets/load_obj.py"

# Rewrite an entire section
/manual-edit content/docs.aspose.org/en/cells/python/developer-guide/working-with-charts.md \
  --scope section-replacement \
  --section "Prerequisites" \
  --intent "Replace the Prerequisites section with: install via .venv/Scripts/pip install aspose-cells-foss"

# Full targeted remediation (requires evidence)
/manual-edit content/reference.aspose.org/en/3d/java/Scene.md \
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
- Wave 4 escalation items from S-46 (gap-apply)
- Human-escalated items from S-26 (heal-page) or S-40 (batch-remediate)

Do **not** use S-73 for:
- Multi-file changes (invoke S-73 once per file)
- Changes where the agent should decide what to fix (use S-26 or S-21 instead)
- Knowledge-driven updates after an upstream change (use S-20 instead)
- Onboarding a page written directly by a human (use S-66 instead)

---

## Scope Boundaries

| Scope | May touch | Must not touch |
|-------|-----------|----------------|
| `frontmatter-only` | Non-system YAML fields: `title`, `description`, `date`, `weight`, `tags`, `categories`, `icon`, `linktitle`, `subtitle`, `keywords`, `author`, `draft`, `summary`, `seoTitle`, `head_title`, `head_description` | `evidence.*`, `grade`, `graded_at`, `graded_model_sha`, `graded_evaluators`, `graded_logic_version`, `provenance.*` |
| `body-wording` | Prose sentences and paragraphs only | Code blocks, frontmatter, section headings (`##`, `###`) |
| `code-snippet` | Single code block inside `--section` | Prose, frontmatter, other code blocks, the heading line itself |
| `section-replacement` | All content from `--section` heading to the next heading of equal or higher level | Other sections, frontmatter |
| `full-remediation` | Any content element named in `--intent` | `evidence.*`, `grade*`, `provenance.*` (always system-managed) |

**Minimal-edit principle:** Touch only what is named in `--intent`. Do not fix adjacent issues noticed during the edit. Do not reformat unrelated content. Do not opportunistically improve sections not specified.

---

## Pre-conditions

1. The file exists at `{relative-file-path}` under `content/`
2. Path-guard check passes for the target file
3. The file path resolves to one of the five known sections: `blog`, `docs`, `kb`, `products`, `reference`
4. `{family}` and `{platform}` are derivable from the file path
5. `knowledge/{family}/{platform}/model.yaml` exists (required for freshness check)

---

## Steps

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
Skills: S-73 (manual-edit), S-01 (path-guard), S-24 (evidence-cite)
Action: Apply operator-specified targeted edit under S-73 governance
```

### Step 2: Path guard check

```bash
.venv/Scripts/python scripts/pipeline/path_guard.py {target_file}
```

- Exit 0: proceed
- Exit 2 (DENY): **halt immediately** — "Path guard denied write to '{target_file}'. Reason: {guard_reason}. Do not bypass."

### Step 3: File existence and section detection

1. Confirm the file exists. If not: **REFUSE** — "File not found: {target_file}"

2. Detect section from path prefix (fail-closed — unknown sections are refused):

   | Path prefix | Section |
   |-------------|---------|
   | `content/blog.aspose.org/` | `blog` |
   | `content/docs.aspose.org/` | `docs` |
   | `content/kb.aspose.org/` | `kb` |
   | `content/products.aspose.org/` | `products` |
   | `content/reference.aspose.org/` | `reference` |

   If the path does not match any prefix: **REFUSE** — "Cannot determine section from path '{target_file}'. S-73 operates only on files under content/{blog,docs,kb,products,reference}.aspose.org/"

3. Extract `{family}` and `{platform}` from the path (3rd and 4th segments after the site prefix, e.g. `content/docs.aspose.org/en/{family}/{platform}/...`).

### Step 4: Load section rules

Load the applicable rules from the embedded section rules table:

| Rule | blog | docs | kb | products | reference |
|------|------|------|----|----------|-----------|
| Evidence block required | Yes — `claims` and `apis` must be non-empty | Content pages: yes; index pages: optional | Content pages: yes; index pages: optional | None | Yes |
| `author` field | Must be exactly `"Aspose"` | — | — | — | — |
| `type` field | — | `"docs"` | `"topic"` for how-to/FAQ | — | — |
| Code examples policy | Recommended | Recommended | Inside `{{% steps %}}` blocks | Discouraged — warn before applying code-snippet/section-replacement | Recommended |
| Grading active | Yes | Yes | Yes | No | Yes |
| `draft` field | Required | — | — | — | — |
| Index shortcodes | — | `{{< sections >}}` | `{{< children >}}` | — | `{{< children >}}` |

If `edit_scope = code-snippet` or `edit_scope = section-replacement` and `section = products`:
warn "products pages discourage code examples — confirm you intend to add code (Y/N)?" and halt if not confirmed.

### Step 5: Knowledge freshness check

```bash
.venv/Scripts/python scripts/pipeline/refresh_knowledge.py {family} {platform}
```

- Prints "current": proceed
- Prints "refreshed": proceed (knowledge was rebuilt)
- `model.yaml` has `stale_since` set AND clone cache is missing: **halt** — "Knowledge for {family}/{platform} is stale. Run S-12 (knowledge-diff) → S-14 (knowledge-update) before editing content."

### Step 6: Auto-updatable check

Read the file's frontmatter. If `provenance.auto_updatable: false`:

```
Warning: This page has auto_updatable: false (human-authored content).
Applying S-73 will mark it as skill-edited in provenance.
Proceed? [Y/N]
```

Halt if operator responds N.

### Step 7: Capture pre-edit grade

```bash
.venv/Scripts/python -m scripts.pipeline.content_eval evaluate --files {target_file} --format json
```

Store result as `pre_grade` (letter A–F) and `pre_score` (0–100). If content_eval is unavailable, run:
```bash
.venv/Scripts/python scripts/pipeline/audit.py --files {target_file}
```
and record `pre_grade` as "unknown (audit proxy)".

### Step 8: Validate intent against knowledge

For scopes `body-wording`, `code-snippet`, `section-replacement`, `full-remediation`:

1. Load `knowledge/{family}/{platform}/merged/api_surface.json`
2. Scan `--intent` for backtick-quoted identifiers (pattern: `` `Identifier` ``)
3. For each identifier found: verify it exists in `api_surface.json`
   - If not found: **REFUSE** — "Proposed text references unknown API token '`{token}`' — not in api_surface.json for {family}/{platform}. Correct the intent or update the knowledge model first (S-14)."

4. Run change-guard check:
   ```bash
   .venv/Scripts/python scripts/pipeline/change_guard.py {family} {platform} "{edit_intent_first_200_chars}"
   ```
   - DENY: **REFUSE** with the guard's reason

### Step 9: Apply the edit

Read the current file. Apply the change described in `--intent` per scope rules:

**`frontmatter-only`**:
Locate the frontmatter YAML block. Find the field(s) named in `--intent`. Apply the new value.
Preserve all other frontmatter fields byte-for-byte. Do not reorder keys.
Refuse if `--intent` names a system-managed field (`evidence`, `grade`, `graded_at`, `graded_model_sha`, `graded_evaluators`, `graded_logic_version`, `provenance`).

**`body-wording`**:
Locate the target sentence or paragraph as described in `--intent`. If it appears more than once in the file: **REFUSE** — "Target text is not unique in the file. Provide a longer surrounding context or use scope section-replacement with --section to narrow the target."
Apply the replacement text. Do not touch code blocks, headings, or frontmatter.

**`code-snippet`**:
Locate the heading matching `--section`. Within that section, find the first code block (triple-backtick fence). If none found: **REFUSE** — "No code block found in section '{target_section}'."
Replace the code fence body with the operator-specified snippet. Preserve the opening fence language identifier.

**`section-replacement`**:
Locate the heading matching `--section` (exact H2 `## {section}` or H3 `### {section}` match).
If not found: **REFUSE** — "Heading '{target_section}' not found in file."
Replace all content from that heading line (exclusive — keep the heading) to the start of the next heading of equal or higher level (exclusive) with the operator-specified content.
If operator explicitly specifies a new heading text, replace the heading line too.

**`full-remediation`**:
Apply all changes described in `--intent` to the elements named. Touch nothing not explicitly named.
The operator bears responsibility for completeness; the skill validates but does not second-guess scope.

Write the modified content back to the file.

### Step 10: Post-edit path guard re-check

```bash
.venv/Scripts/python scripts/pipeline/path_guard.py {target_file}
```

If DENY: this indicates an unexpected path mutation. **Revert the write, halt.**

### Step 11: Audit check

```bash
.venv/Scripts/python scripts/pipeline/audit.py --files {target_file}
```

If FAIL:
- **Revert the edit** (restore pre-edit file content)
- **Halt** — "Post-edit audit FAIL — edit has been reverted. Fix the proposed content and retry.\nFindings:\n{audit_findings}"
- Write audit trail with `edit_applied: false, reverted: true`

### Step 12: Frontmatter validation

```bash
.venv/Scripts/python scripts/pipeline/validate_frontmatter.py {target_file}
```

If errors: **revert, halt** with the validation errors listed.

### Step 13: Refresh evidence block

```bash
.venv/Scripts/python scripts/pipeline/attach_evidence.py --files {target_file}
```

This updates `evidence.model_sha`, `evidence.claims`, and `evidence.apis` to reflect the
post-edit content. Do not perform this step for `products` section files (no evidence block).

### Step 14: Update provenance

In the file's frontmatter `provenance:` block:
- Set `last_mechanism: manual-edit-skill`
- Set `reviewed: false` (operator-directed but not peer-reviewed)
- Do **not** change `auto_updatable`
- Do **not** downgrade `content_origin` from `human-authored`
- If `content_origin` was `unknown`, leave it as-is (do not upgrade; manual-edit-skill is not a generation mechanism)

### Step 15: Re-evaluate and grade

```bash
.venv/Scripts/python -m scripts.pipeline.content_eval evaluate --files {target_file} --format json
```

Store as `post_grade` and `post_score`.

**No-downgrade check**: If `post_grade` is lower than `pre_grade` by more than one letter:
```
Warning: Grade regression detected: {pre_grade} → {post_grade}
The edit reduced content quality. Review the diff and confirm you want to keep this change.
Proceed? [Y/N]
```
If operator responds N: **revert the edit** (restore pre-edit content, do not update evidence or provenance).

```bash
.venv/Scripts/python scripts/pipeline/grade_writer.py --files {target_file}
```

### Step 16: Record skill invocation

```bash
.venv/Scripts/python scripts/pipeline/skill_run_manager.py record-step \
  --skill S-73 \
  --type full \
  --files {target_file} \
  --note "manual-edit scope={edit_scope} section={target_section_or_none} intent={edit_intent_first_100_chars}"
```

### Step 17: Write audit trail

Ensure the output directory exists:
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
  "section": "{blog|docs|kb|products|reference}",
  "edit_scope": "{scope}",
  "edit_intent": "{full intent string}",
  "target_section_heading": "{heading or null}",
  "evidence_justification": "{CLM-xxx or null}",
  "pre_grade": "{A|B|C|D|F|unknown}",
  "pre_score": 0,
  "post_grade": "{A|B|C|D|F|unknown}",
  "post_score": 0,
  "audit_result": "PASS|FAIL",
  "audit_findings": [],
  "edit_applied": true,
  "reverted": false,
  "provenance_mechanism": "manual-edit-skill",
  "executed_at": "ISO-8601 timestamp",
  "run_id": "{skill_run_manager run_id}"
}
```

### Step 18: Report

```
MANUAL EDIT — {target_file}
Section:  {blog|docs|kb|products|reference}
Scope:    {edit_scope}
Intent:   {edit_intent}

Pre-edit grade:  {pre_grade} ({pre_score}/100)
Post-edit grade: {post_grade} ({post_score}/100)

Audit:     {PASS|FAIL}
Evidence:  updated (model_sha: {sha})  [or: N/A for products section]
Provenance: last_mechanism → manual-edit-skill

Edit applied:  {YES|NO (reverted)}
Audit trail:  reports/manual-edits/{filename}.json

RESULT: {APPLIED|REVERTED|REFUSED}
Reason (if not APPLIED): {reason}
```

---

## Post-conditions

- If APPLIED:
  - File content reflects exactly the operator-specified change and nothing else
  - `audit.py` passes on the modified file
  - Evidence frontmatter is current (model_sha, claims, apis)
  - `provenance.last_mechanism = manual-edit-skill`
  - Grade is persisted via `grade_writer.py`
  - Audit trail written to `reports/manual-edits/`
  - Skill invocation recorded in `skill_run_manager`
- If REVERTED: file is byte-for-byte identical to pre-edit state; audit trail written with `reverted: true`
- If REFUSED: file is untouched; no audit trail written; refusal reason printed to console

---

## Refusal and halt conditions

| Condition | Response |
|-----------|----------|
| Unknown `edit_scope` value | REFUSE |
| `section-replacement` or `code-snippet` without `--section` | REFUSE |
| `full-remediation` without `--evidence` | REFUSE |
| `path_guard.py` returns DENY | HALT (no recovery) |
| File not found | REFUSE |
| Path does not map to known section | REFUSE |
| `knowledge/model.yaml` stale AND clone cache missing | HALT — run S-12 → S-14 |
| API token in `--intent` not in `api_surface.json` | REFUSE |
| `change_guard.py` returns DENY | REFUSE |
| `--section` heading not found in file | REFUSE |
| Target text not unique (`body-wording`) | REFUSE |
| No code block in target section (`code-snippet`) | REFUSE |
| `--intent` names a system-managed frontmatter field | REFUSE |
| Post-edit `audit.py` FAIL | REVERT and HALT |
| Post-edit `validate_frontmatter.py` errors | REVERT and HALT |
| Grade regression > 1 letter, operator declines | REVERT |
| `products` section + code scope, operator declines warning | REFUSE |

### What S-73 will never do

- Generate alternative text via LLM (use S-26 or S-21 if the agent should decide what to fix)
- Edit more than one file per invocation
- Modify `evidence.*`, `grade*`, or `provenance.*` via operator intent (these are system-managed)
- Operate on files outside `content/`
- Proceed when knowledge is confirmed stale
- Skip `audit.py` or `validate_frontmatter.py` for any reason
- Be invoked programmatically by another skill (always operator-invoked)

---

## Integration with remediation flows

S-73 is the sanctioned path for human-escalated items from all automated repair skills:

| Upstream source | Escalation mechanism | S-73 role |
|----------------|---------------------|-----------|
| S-46 (gap-apply) Wave 4 | `wave4-escalation.md` | Operator reads each item, formulates the specific change, invokes S-73 |
| S-26 (heal-page) | Grade does not improve after 2 passes → escalation | Operator reviews the page, specifies the fix, invokes S-73 |
| S-40 (batch-remediate) | Human-queue items | Operator processes each queue item via S-73 |

S-73 produces an audit trail at `reports/manual-edits/` that references the originating
escalation item, creating an end-to-end traceable remediation record.

---

## Error handling

| Error | Action |
|-------|--------|
| Knowledge model missing | Abort — do not edit without knowledge grounding |
| `audit.py` or `validate_frontmatter.py` not found | Treat as BROKEN skill condition; revert any pending write; produce skill-breakage report per AGENTS.md §6b |
| `attach_evidence.py` failure | Revert edit; report as post-edit pipeline error |
| `content_eval` unavailable | Proceed with audit-proxy grade; log "content_eval unavailable — grade proxy used" |
| File write permission error | Halt; report filesystem error |
| Skill invocation recording failure | Log warning but do not revert the content edit; record the recording failure in the audit trail |
