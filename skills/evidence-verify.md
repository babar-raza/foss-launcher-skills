---
name: evidence-verify
id: S-42
description: >
  Verify published content pages against the Product Evidence File using
  deterministic checks for citations, API references, format claims, and
  forbidden claim violations.
args: "{content-file-path} | --batch {family} {platform}"
---

# S-42: Evidence Verify — Deterministic Content Verification

**Arguments**: $ARGUMENTS
Expected format: `{content-file-path}` or `--batch {family} {platform}`

## Purpose
Deterministically verify that a published content page is grounded in the PEF. Checks citation validity, API reference accuracy, format claim correctness, and forbidden claim violations. Produces a structured verification report with PASS/WARN/FAIL result.

## Pre-conditions
1. `evidence/{family}/{platform}/pef.json` must exist (run S-40 first)
2. Content file must exist at the specified path

## Automated Script

Run the verifier:
```
python scripts/verify.py {content-file-path}              # Single page
python scripts/verify.py --batch {family} {platform}       # All pages for a product
```

## Verification Checks (all deterministic)
1. **Citation validity**: Parse `<!-- evidence: claim_id=X -->` comments → check claim_id exists in PEF
2. **API references**: Extract `ClassName.method()` from code blocks and inline code → check against PEF api_surface
3. **Format claims**: Extract format mentions (DOCX, PDF, etc.) → check against PEF formats
4. **Forbidden claims**: Check content text against PEF forbidden_claims list
5. **Code blocks**: Verify class/method names in code blocks match PEF

## Result Determination
- **PASS**: All checkable items grounded (grounded_pct ≥ 70%, no forbidden violations)
- **WARN**: Some orphaned citations or unverified API references
- **FAIL**: Forbidden claim violations OR grounded_pct < 70%

## Output
- `evidence/{family}/{platform}/verification/{slug}-{timestamp}.json`

## Post-conditions
- Verification report exists for each checked page
- Result is deterministic and reproducible for same content + PEF
