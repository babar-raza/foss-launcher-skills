---
name: truth-audit-content
id: S-85
description: >
  Line-level content truth audit against clone cache and knowledge model
args: "{family} {platform} [--scope all|products|docs|blog|kb|reference] [--no-llm] [--max-units N]"
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# S-85: Truth Audit Content — Line-Level Content Truth Audit

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform} [--scope all|products|docs|blog|kb|reference] [--no-llm] [--max-units N] [--unit-types H,P,C,T,L]`

## Purpose

Decompose all English content pages for a family/platform into individually addressable reviewable units (headings, paragraphs, code blocks, table rows, list items), verify each unit against the clone cache and knowledge model, and produce a structured gap ledger with stable finding IDs and evidence chains. **Read-only — never modifies content.**

## Pre-conditions

1. Clone cache must exist at `runs/.clone_cache/aspose_{family}_{platform}/`
2. `knowledge/{family}/{platform}/merged/api_surface.json` must exist
3. `knowledge/{family}/{platform}/merged/model.yaml` `stale_since` must be null
4. Knowledge bootstrap must have been run (DAR: S-54)

## Steps

### Step 1: Run the audit

```bash
python scripts/pipeline/truth_audit_content.py {family} {platform} --scope {scope}
```

### Step 2: Review output

- **Gap ledger (JSON)**: `reports/truth-audit/{family}-{platform}-{date}.json`
- **Human report (Markdown)**: `reports/truth-audit/{family}-{platform}-{date}.md`
- **State file**: `reports/truth-audit/state/{family}-{platform}.json`

### Step 3: Interpret verdicts

| Verdict | Meaning | Action |
|---------|---------|--------|
| VERIFIED | Confirmed by clone cache + knowledge | None |
| UNVERIFIABLE | Evidence insufficient | Review if critical |
| UNSUPPORTED | No evidence found | Investigate |
| CONTRADICTED | Evidence contradicts unit | Must fix |
| FABRICATED | References nonexistent API | Must fix |

## Post-conditions

1. Reports written to `reports/truth-audit/`
2. State file updated for delta tracking
3. **No content files modified**

## Exit Codes

- `0`: No defects
- `1`: Internal error
- `2`: CONTRADICTED or FABRICATED units found
