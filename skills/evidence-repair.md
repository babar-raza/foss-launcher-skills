---
name: evidence-repair
id: S-77
description: >
  Repair the evidence: frontmatter block on content pages blocked by the
  pre-commit validator. Two-stage: auto-attach then LLM reasoning.
  ONLY modifies evidence: and provenance: blocks — never touches page body.
args: "{relative-file-path} [additional-paths...] [--dry-run] [--scope claims|apis|both]"
---

# S-77: Evidence Repair — Repair Evidence Frontmatter for Validator-Blocked Pages

**Arguments**: $ARGUMENTS
Expected format: `{relative-file-path} [additional-paths...]`

Optional flags: `--dry-run` (no file writes), `--scope claims|apis|both` (default: `both`)

## Purpose

Repair the `evidence:` frontmatter block on a content page that is blocked by the
pre-commit validator (`validate_frontmatter.py` P-03 or `audit.py` evidence FAIL).

**Critical scope boundary**: This skill ONLY modifies the `evidence:` and `provenance:`
blocks in the YAML frontmatter. It NEVER modifies page title, description, body content,
headings, code blocks, or any prose text.

## Pre-conditions

For each file:
- File must exist under `$CONTENT_REPO_PATH/content/`
- File must be an English source file — refuse locale variants (index.ar.md, etc.)
- `knowledge/{family}/{platform}/merged/model.yaml` must exist with `stale_since: null`
- `knowledge/{family}/{platform}/merged/claims.json` and `api_surface.json` must exist

## Section-Specific Evidence Requirements

| Section | claims required? | apis required? |
|---------|-----------------|----------------|
| `blog.aspose.org` | YES | YES |
| `docs.aspose.org` | YES | YES |
| `kb.aspose.org` | YES | YES |
| `products.aspose.org` | NO | NO |
| `reference.aspose.org` | YES | YES |

## Steps

### Stage 1 — Auto-Attach (script-driven)

1. **Run attach_evidence.py with --force**:
   ```bash
   python scripts/pipeline/attach_evidence.py --files {path} --force
   ```

2. **Verify Stage 1 result**:
   ```bash
   python scripts/pipeline/validate_frontmatter.py {path}
   python scripts/pipeline/audit.py --files {path}
   ```
   - If both exit 0 → report **REPAIRED (auto)** and stop.
   - If either still fails → proceed to Stage 2.

### Stage 2 — Reasoning-Based Population (LLM-executed, knowledge-grounded)

3. **Load knowledge artifacts**:
   - Read `knowledge/{family}/{platform}/merged/claims.json`
   - Read `knowledge/{family}/{platform}/merged/api_surface.json`
   - Read `knowledge/{family}/{platform}/merged/api_surface.md`

4. **Read current page content** — full text including all sections and code blocks.

5. **Populate evidence.claims**: Scan page for factual claims. Match against `claims.json` by `description`/`text`. Include 2–8 most relevant claim IDs. **Only add IDs that exist in `claims.json` — never invent IDs.**

6. **Populate evidence.apis**: Scan page for API class names, methods, enum values in code blocks and prose. Match against `api_surface.json`. **Only add refs that exist in `api_surface.json` — never invent refs.**

7. **Write evidence block**:
   - MAY modify: `evidence.claims`, `evidence.apis`, `evidence.model_sha`, `evidence.model_version`
   - Set `provenance.last_mechanism: evidence-attach`
   - MUST NOT touch: page title, description, body content, headings, code blocks, prose

8. **Verify Stage 2 result**:
   ```bash
   python scripts/pipeline/validate_frontmatter.py {path}
   python scripts/pipeline/audit.py --files {path}
   ```
   - If both exit 0 → report **REPAIRED (reasoning)** and stop.
   - If either still fails → proceed to Safe-Escape.

### Safe-Escape

When Stage 2 cannot confidently populate claims or apis:

9. Set `provenance.content_origin: manual-remediation` in frontmatter.
10. Verify `validate_frontmatter.py` exits 0 (P-03 bypassed for manual-remediation).
11. Append escalation entry to `reports/evidence-repair/needs-human-{YYYYMMDD}.md`.
12. Report **ESCAPED** for this file.

## Post-conditions

- REPAIRED: both validators pass; evidence populated with verified values only
- ESCAPED: validate_frontmatter.py passes; marked for human follow-up
- Page body content identical to input (no prose changes)

## Refusal Conditions

| Condition | Action |
|-----------|--------|
| Knowledge model stale | REFUSE: run S-12 + S-14 first |
| File not under content/ | REFUSE: path-guard DENY |
| Locale variant file | REFUSE: English source only |
| Double frontmatter | REFUSE: fix structural issue first |

## Never Do

- Never modify page title, description, body text, headings, or code blocks
- Never invent claim IDs or API refs — must exist in knowledge artifacts
- Never apply to locale translation files
- Never skip post-edit validation
