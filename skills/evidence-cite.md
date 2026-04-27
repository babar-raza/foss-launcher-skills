---
name: evidence-cite
id: S-24
description: >
  Insert evidence citation comments into content pages, linking each factual
  statement to its backing claim in the knowledge model.
args: "{content-file-path}"
depends_on: [path-guard, ground-check]
---

# S-24: Evidence Cite — Attach Knowledge Citations

**Arguments**: $ARGUMENTS
Expected format: `{content-file-path}`

## Purpose
Insert `<!-- evidence: claim_id=X -->` citation comments into content pages, linking each factual statement to its backing claim in the knowledge model.

## Pre-conditions
1. Content file must exist
2. Knowledge must exist for the product (detect from content path)
3. Run S-32 content-audit first to identify claim mappings

## Steps

1. **Identify product**: Extract family/platform from content file path
2. **Load knowledge**: Read `merged/claims.json`
3. **Read content file**
4. **For each factual paragraph**:
   - Find the best matching claim from claims.json
   - If match confidence >= 0.7, insert citation comment after the paragraph:
     ```
     <!-- evidence: claim_id=CLM-3d-abc123, confidence=0.95, provenance=dual -->
     ```
   - If code block references a class/method:
     ```
     <!-- evidence: api=Scene.open, source=api_surface.json -->
     ```
5. **Write modified content file** (preserve all existing content, only add citation comments)
6. **Do NOT remove existing citations** — only add or update

## Citation format
```html
<!-- evidence: claim_id={id}, confidence={conf}, provenance={prov} -->
<!-- evidence: api={class.method}, source=api_surface.json -->
<!-- evidence: format={ext}, support={import|export|both}, source=formats.json -->
```

## Post-conditions
- Content file has citation comments for all verifiable claims
- No content was removed or modified (only comments added)
- Citations reference valid claim_ids from claims.json
