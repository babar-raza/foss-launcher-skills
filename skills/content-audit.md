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
Audit content pages against verified knowledge. Maps each factual claim in content to knowledge artifacts using deterministic semantic similarity.

## Pre-conditions
1. **Knowledge bootstrap**: Run `/knowledge-bootstrap {family} {platform}` and check status:
   - `STOP:partial` → halt (see printed message)
   - Any other status (`READY`, `BOOTSTRAPPED`, `REFRESHED`, `WARN:conflicts`) → continue

## Steps

### Step 1: Run deterministic audit script

Run the Python script first to get reproducible, machine-verifiable results:

```bash
# For a specific product:
python scripts/pipeline/commands/content/audit.py {family} {platform} --json

# For specific files:
python scripts/pipeline/commands/content/audit.py --files {content-file-path} --json

# For all products:
python scripts/pipeline/commands/content/audit.py all --json
```

The script classifies every prose paragraph into tiers:
- **SUPPORTED**: API refs verified AND token overlap >= 0.5 with a knowledge claim
- **PROBABLE**: API refs verified OR token overlap >= 0.3
- **WEAK**: token overlap < 0.3 but no contradiction
- **UNSUPPORTED**: no matching evidence found
- **CONTRADICTED**: matches a forbidden claim or contradicts format direction

It also runs `verify_tokens` on code blocks for API accuracy.

### Step 2: Interpret results

After the script completes, review the JSON output:

1. **CONTRADICTED findings are blockers** — these must be fixed before content ships
2. **UNSUPPORTED findings need investigation** — determine if they need evidence or removal
3. **WEAK findings are informational** — consider strengthening evidence or qualifying language
4. **Check code_findings** for API accuracy issues in code blocks

### Step 3: Check coverage gaps

Identify knowledge facts not mentioned in content:
- Load `claims.json` and compare against content coverage
- Flag important claims (confidence >= 0.8) that have no content coverage

### Step 4: Write audit report

The script automatically writes a report to `reports/audit/{family}-{platform}-content-audit-{timestamp}.json`.

Review the aggregate summary and act on:
- Any CONTRADICTED tier findings (must fix)
- Files with high UNSUPPORTED percentages (need evidence)
- Code blocks with API accuracy failures

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
