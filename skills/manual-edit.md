---
name: manual-edit
id: S-78
description: >
  Apply an operator-specified targeted content edit to a single content file
  under full governance. Unlike heal-page, the operator specifies exactly what
  to change; the skill validates, applies, and verifies the change.
args: "{relative-file-path} --scope {scope} --intent {intent} [--section {heading}] [--evidence {id}]"
---

# S-78: Manual Edit — Operator-Directed Targeted Content Edit

**Arguments**: $ARGUMENTS
Expected format:
```
{relative-file-path} --scope {scope} --intent "{intent}" [--section "{heading}"] [--evidence "{id}"]
```

| Parameter | Required | Values |
|-----------|----------|--------|
| `{relative-file-path}` | Yes | Path from `$CONTENT_REPO_PATH/content/` |
| `--scope` | Yes | `frontmatter-only` \| `body-wording` \| `code-snippet` \| `section-replacement` \| `full-remediation` |
| `--intent` | Yes | Natural language specification: what to change and why |
| `--section` | Conditional | H2 or H3 heading text; required for `code-snippet` and `section-replacement` scopes |
| `--evidence` | Conditional | CLM-xxx claim ID or API token; required for `full-remediation` scope |

## Purpose

Apply an operator-specified targeted change to a single content file under full governance.
Unlike S-26 (heal-page) and S-21 (page-enhance) — which are agent-decided repairs — S-78
applies exactly what the operator specifies.

Use for: typo/wording corrections, frontmatter field updates, code block replacements with
known snippets, section rewrites directed by human editorial judgment.

Do **not** use for: multi-file changes, agent-decided repairs, knowledge-driven updates (use S-20), or onboarding human-authored pages (use register-human-content, S-71).

## Scope Boundaries

| Scope | May touch | Must not touch |
|-------|-----------|----------------|
| `frontmatter-only` | `title`, `description`, `date`, `weight`, `tags`, `categories`, `icon`, `linktitle`, `subtitle`, `keywords` | `evidence.*`, `grade*`, `provenance.*` |
| `body-wording` | Prose sentences and paragraphs | Code blocks, frontmatter, section headings |
| `code-snippet` | Single code block inside `--section` | Prose, frontmatter, other code blocks |
| `section-replacement` | All content within `--section` to next heading | Other sections, frontmatter |
| `full-remediation` | Any content element named in `--intent` | `evidence.*`, `grade*`, `provenance.*` |

**Minimal-edit principle:** Touch only what is named in `--intent`. Do not fix adjacent issues.

## Pre-conditions

1. File exists at the target path under `$CONTENT_REPO_PATH/content/`
2. `knowledge/{family}/{platform}/model.yaml` exists with `stale_since: null`
3. File is an English source file (refuse locale variants)

## Steps

1. **Parse and validate arguments** from $ARGUMENTS.

2. **Freshness check**:
   ```bash
   python scripts/pipeline/check_staleness.py {family} {platform}
   ```
   If stale → STOP: "Knowledge is stale. Run S-12 (knowledge-diff) then S-14 (knowledge-update) first."

3. **Read file** — full content including frontmatter and body.

4. **Apply edit** per scope:
   - `frontmatter-only`: Update only the named YAML fields
   - `body-wording`: Modify only prose sentences within specified passage
   - `code-snippet`: Find section by heading, replace only the first code block in that section
   - `section-replacement`: Replace content from heading to next same-level heading
   - `full-remediation`: Apply change named in `--intent` to any content element

5. **Reattach evidence**:
   ```bash
   python scripts/pipeline/attach_evidence.py --files {path} --force
   ```

6. **Audit**:
   ```bash
   python scripts/pipeline/audit.py --files {path}
   ```
   Must exit with 0 FAIL.

7. **Content eval** (for body scope changes):
   ```bash
   python -m scripts.pipeline.content_eval evaluate --files {path}
   ```
   If grade decreased → revert and report; do not commit a regression.

8. **Report result**:
   ```
   MANUAL EDIT — {path}
   Scope: {scope}
   Intent: {intent}
   Result: APPLIED | REVERTED | REFUSED
   Grade: {before} → {after}
   Validation: audit.py PASS | FAIL
   ```

## Post-conditions

- File modified exactly as specified in `--intent`
- `evidence:` block up to date
- `audit.py` exits with 0 FAIL
- Grade not decreased

## Error handling

| Error | Action |
|-------|--------|
| Knowledge stale | REFUSE; instruct to run S-12 + S-14 first |
| Grade decreased after edit | Revert; report as REVERTED |
| File not under content/ | REFUSE; path-guard DENY |
| Scope requires body modification but evidences are empty | Run evidence-repair (S-77) first |
