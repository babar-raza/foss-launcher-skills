---
name: change-guard
id: S-33
description: >
  Pre-write gate that validates proposed content changes against verified
  knowledge. Rejects writes that contradict known facts.
args: "{family} {platform} \"{proposed-text}\""
---

# S-33: Change Guard — Pre-Write Knowledge Gate

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform} "{proposed-text}"`

## Purpose
Pre-write gate that validates proposed content changes against verified knowledge before they are written. Rejects writes that contradict known facts.

## Pre-conditions
1. `knowledge/{family}/{platform}/merged/index.json` must exist
2. Knowledge must not be stale
3. If `knowledge/{family}/{platform}/scout/absent_evidence.json` exists, load it for negative evidence validation

## Steps

1. **Load knowledge**: Read `index.json`, specifically `forbidden_claims` and `not_implemented` lists. Also read `api_surface.json` for class/method validation.
2. **Load negative evidence** (if available): Read `absent_evidence.json` from scout output for definitive class existence data.
3. **Check proposed text against forbidden claims**:
   - Exact match → DENY
   - Semantic similarity (>80% token overlap with any forbidden claim) → DENY
   - Check for paraphrases of forbidden claims → DENY
4. **Check proposed text against known facts**:
   - If text makes a claim, verify it has backing in `claims.json`
   - If text references a class/method, verify it exists in `api_surface.json`
   - If text references a format, verify it in `formats.json`
5. **Negative evidence checks** (when `absent_evidence.json` exists):
   - If text references a class name (PascalCase word) that is NOT in `absent_evidence.json` → `found_classes` AND NOT in `api_surface.json` → DENY with "Class {name} not found in repository"
   - If text contains a constructor call `new ClassName(args)`, verify the constructor signature exists in `api_surface.json` (methods where name matches the class name or `<init>`) → DENY if no matching constructor
   - If text references a package/namespace not in `absent_evidence.json` → `scanned_packages` → DENY with "Package {name} not found in repository"
6. **Decision**:
   - PASS: Text is consistent with knowledge
   - WARN: Text lacks direct evidence but doesn't contradict
   - DENY: Text contradicts known facts or references non-existent classes/constructors/packages

## Output
```
PASS: Proposed text is consistent with verified knowledge
WARN: No direct evidence found, but no contradiction detected
DENY: Proposed text contradicts known fact — {forbidden_claim}
```

## Post-conditions
- Decision is logged
- DENY decisions must be resolved before content is written
