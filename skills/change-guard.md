---
name: change-guard
id: S-33
description: >
  Pre-write gate that validates proposed content changes against verified
  knowledge. Rejects writes that contradict known facts.
args: "{family} {platform} \"{proposed-text}\""
depends_on: [path-guard, ground-check]
---

# S-33: Change Guard — Pre-Write Knowledge Gate

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform} "{proposed-text}"`

## Purpose
Pre-write gate that validates proposed content changes against verified knowledge before they are written. Rejects writes that contradict known facts.

## Pre-conditions
1. `knowledge/{family}/{platform}/merged/index.json` must exist
2. Knowledge must not be stale

## Steps

1. **Load knowledge**: Read `index.json`, specifically `forbidden_claims` and `not_implemented` lists
2. **Check proposed text against forbidden claims**:
   - Exact match → DENY
   - Semantic similarity (>80% token overlap with any forbidden claim) → DENY
   - Check for paraphrases of forbidden claims → DENY
3. **Check proposed text against known facts**:
   - If text makes a claim, verify it has backing in `claims.json`
   - If text references a class/method, verify it exists in `api_surface.json`
   - If text references a format, verify it in `formats.json`
4. **Decision**:
   - PASS: Text is consistent with knowledge
   - WARN: Text lacks direct evidence but doesn't contradict
   - DENY: Text contradicts known facts

## Output
```
PASS: Proposed text is consistent with verified knowledge
WARN: No direct evidence found, but no contradiction detected
DENY: Proposed text contradicts known fact — {forbidden_claim}
```

## Post-conditions
- Decision is logged
- DENY decisions must be resolved before content is written
