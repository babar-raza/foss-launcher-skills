---
name: content-audit
id: S-32
description: >
  Audit content pages against verified knowledge. Maps each factual claim
  in content to knowledge artifacts using semantic similarity.
args: "{content-file-path} | {family} {platform}"
---

# S-32: Content Audit — Semantic Knowledge Verification

**Arguments**: $ARGUMENTS
Expected format: `{content-file-path}` or `{family} {platform}`

## Purpose
Audit content pages against verified knowledge. Maps each factual claim in content to knowledge artifacts using semantic similarity.

## Pre-conditions
1. Knowledge must exist: `knowledge/{family}/{platform}/merged/index.json`
2. Index must not be stale (`stale: false`)
3. Index must not have unresolved conflicts (`has_conflicts: false` or conflicts are acknowledged)

## Steps

1. **Identify product**: Extract family/platform from content path or arguments
2. **Load knowledge**: Read `merged/index.json`, `merged/claims.json`, `merged/api_surface.json`
3. **Load content**: Read the content file(s)
4. **Split content into factual paragraphs**: Skip frontmatter, headings, and code blocks
5. **For each paragraph, classify**:
   - Search claims.json for matching claims (text similarity)
   - **SUPPORTED**: Match found, confidence >= 0.75, provenance = dual
   - **PROBABLE**: Match found, confidence >= 0.6, single-source provenance
   - **WEAK**: Match found, confidence < 0.6 or llm_fallback source
   - **UNSUPPORTED**: No matching claim found
   - **CONTRADICTED**: Paragraph matches a `forbidden_claim`
6. **For code blocks**: Verify class/method names exist in `api_surface.json`
7. **Check coverage**: Identify knowledge facts not mentioned in content → MISSING COVERAGE
8. **Write audit report** to `reports/audit/{family}-{platform}-{timestamp}.md`

## Audit report format
```
# Content Audit: {file}
Date: {timestamp}
Knowledge: {family}/{platform} (sha: {repo_sha})

## Summary
- Paragraphs checked: N
- SUPPORTED: N (N%)
- PROBABLE: N (N%)
- WEAK: N (N%)
- UNSUPPORTED: N (N%)
- CONTRADICTED: N (N%)

## Findings
### CONTRADICTED (must fix)
- Line X: "FBX export is supported" → contradicts forbidden_claim "FBX export is supported"

### UNSUPPORTED (needs evidence)
- Line Y: "The library supports 50 formats" → no matching claim found

### MISSING COVERAGE
- Claim CLM-3d-abc123 "Scene class provides open() method" not mentioned in content
```

## Post-conditions
- Audit report written to `reports/audit/`
- No CONTRADICTED findings should remain in committed content
