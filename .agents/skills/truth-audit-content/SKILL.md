---
name: truth-audit-content
id: S-90
description: >
  Line-level content truth audit. Decomposes content pages into individually
  addressable units (headings, paragraphs, code blocks, tables, list items),
  verifies each unit against knowledge model, and produces a structured gap
  ledger. Read-only.
args: "{family} {platform} [--scope all|products|docs|blog|kb|reference] [--no-llm] [--max-units N]"
---

# S-90: Truth Audit Content — Line-Level Content Truth Audit

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform} [--scope all|products|docs|blog|kb|reference] [--no-llm] [--max-units N] [--unit-types H,P,C,T,L]`

## Purpose

Decompose all English content pages for a family/platform into individually addressable
reviewable units (headings, paragraphs, code blocks, table rows, list items), verify each
unit against the clone cache and knowledge model, and produce a structured gap ledger with
stable finding IDs and evidence chains. **Read-only — never modifies content.**

This fills the gap between S-47 (truth-audit — member-level API token verification) and S-25
(eval-page — page-level publishability verdict) by providing line-level truth verification
with defect origin classification.

## Pre-conditions

1. `knowledge/{family}/{platform}/merged/api_surface.json` must exist
2. `knowledge/{family}/{platform}/merged/model.yaml` `stale_since` must be null
3. Content pages exist under `$CONTENT_REPO_PATH/content/` for the target product
4. Clone cache at `runs/.clone_cache/aspose_{family}_{platform}/` (optional; disables Tier 2 grep if absent)

## Scope Options

| Flag | Includes |
|---|---|
| `--scope all` | All five content sites |
| `--scope products` | products.aspose.org only |
| `--scope docs` | docs.aspose.org only |
| `--scope blog` | blog.aspose.org only |
| `--scope kb` | kb.aspose.org only |
| `--scope reference` | reference.aspose.org only |

## Unit Types

| Code | Unit type |
|---|---|
| H | Headings |
| P | Paragraphs |
| C | Code blocks |
| T | Table rows |
| L | List items |

## Steps

1. **Parse arguments**: Extract `family`, `platform`, `scope`, and flags.

2. **Load knowledge artifacts**:
   - `api_surface.json` — canonical API surface
   - `claims.json` — verifiable claims
   - `limitations.md` — known limitations (for false-positive filtering)

3. **Decompose pages into units**: For each page in scope, extract all units with their line numbers and section context.

4. **Verify each unit** at three tiers:
   - **Tier 1**: Check class/method names against `api_surface.json`. Flag any name not present.
   - **Tier 2**: Grep clone cache for corroboration of unique phrases (if clone cache present).
   - **Tier 3** (LLM, unless `--no-llm`): Verify complex prose claims against knowledge model.

5. **Classify each finding**:

   | Classification | Meaning |
   |---|---|
   | `PASS` | Unit verified against knowledge |
   | `WARN:unverified` | Could not verify; no contradiction found |
   | `FAIL:false_api` | API name not in `api_surface.json` |
   | `FAIL:contradicts_knowledge` | Claim contradicts `claims.json` or `limitations.md` |
   | `FAIL:stale` | Claim was true in a previous version but is no longer valid |

6. **Assign stable finding IDs**: Each FAIL/WARN gets a stable ID derived from file path + line number.

7. **Write gap ledger** to `reports/truth-audit/{family}/{platform}/truth-audit-{date}.json`:
   ```json
   {
     "family": "{family}",
     "platform": "{platform}",
     "scope": "{scope}",
     "audited_at": "{ISO datetime}",
     "units_checked": N,
     "findings": [
       {
         "id": "TA-{hash}",
         "file": "{path}",
         "line": N,
         "unit_type": "P",
         "classification": "FAIL:false_api",
         "unit_text": "{offending text}",
         "evidence": "{what contradicts it}"
       }
     ]
   }
   ```

8. **Print summary**:
   ```
   TRUTH AUDIT CONTENT — {family}/{platform}
   Scope: {scope}
   Pages audited: N
   Units checked: N
     PASS:               N
     WARN:unverified:    N
     FAIL:false_api:     N
     FAIL:contradicts:   N
     FAIL:stale:         N

   Gap ledger: reports/truth-audit/{family}/{platform}/truth-audit-{date}.json
   ```

## Post-conditions

- Gap ledger written with stable finding IDs
- No content modified (read-only)
- FAILs should be routed to S-26 (heal-page) or S-78 (manual-edit) for remediation
