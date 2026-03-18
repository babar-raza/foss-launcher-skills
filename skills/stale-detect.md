---
name: stale-detect
id: S-13
description: >
  Map upstream repository changes to content pages that may need updating.
  Identifies stale, at-risk, and current content across all sites.
args: "{family} {platform}"
---

# S-13: Stale Detect — Map Changes to Affected Content

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}`

## Purpose
Map upstream repository changes (detected by S-12) to content pages that may need updating.

> **Configuration**: Content site paths scanned by this skill are defaults for the aspose.org repo. See `config.yaml` for your project's path configuration.

## Pre-conditions
1. Knowledge diff should have been run (S-12) or `model.yaml` should have change info
2. Content pages must exist for the product

## Steps

1. **Load knowledge**: Read `merged/index.json` and `merged/claims.json`
2. **Identify changed claims**: Compare current claims against content citations
3. **Scan content pages**: Find all content files for `{family}/{platform}` across all sites:
   - `content/docs.aspose.org/en/{family}/{platform}/`
   - `content/blog.aspose.org/{family}/{platform}/`
   - `content/kb.aspose.org/en/{family}/{platform}/`
   - `content/reference.aspose.org/en/{family}/{platform}/`
4. **For each content page**:
   - Read evidence citations (`<!-- evidence: claim_id=... -->`)
   - Check if cited claims have changed or been removed
   - Check if page references classes/methods that no longer exist
   - Check if page mentions formats whose support status changed
5. **Classify staleness**:
   - STALE: Page cites changed/removed claims
   - AT_RISK: Page references changed API surface
   - CURRENT: No changes detected
6. **Write report**

## Output
```
# Staleness Report: {family}/{platform}
Pages checked: N
STALE: N pages need updating
AT_RISK: N pages may need review
CURRENT: N pages are up to date

## STALE pages
- docs/getting-started/installation.md — cited claim CLM-abc123 changed
- kb/howto/load-model.md — references Scene.load() which was renamed

## AT_RISK pages
- docs/developer-guide/formats.md — format matrix may have changed
```

## Post-conditions
- Report identifies all potentially affected content pages
- STALE pages should be prioritized for update
