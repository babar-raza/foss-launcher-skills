---
name: stale-detect
description: >
  Map upstream changes to affected content pages
args: "{family} {platform}"
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

<!-- CONTRACT: agent-executed workflow (no single script runs the full skill)
     postcondition: staleness report written or printed identifying STALE/AT_RISK/CURRENT pages
     postcondition: checks model_sha comparison and orphaned claim detection
     note: API surface and format change detection described in Steps 4c-4d are agent-reasoned,
           not automated by stale_detect.py (which only checks model_sha and orphaned claims)
     verified: 2026-04-01
-->
# S-13: Stale Detect — Map Changes to Affected Content

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}`

## Purpose
Map upstream repository changes (detected by S-12) to content pages that may need updating.

## Pre-conditions
1. Knowledge diff should have been run (S-12) or `model.yaml` should have change info
2. Content pages must exist for the product

## Steps

> **Skill context gate** — run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/skill_context.py begin --skill S-13 --scope "*"
> ```


1. **Load knowledge**: Read `merged/index.json` and `merged/claims.json`
2. **Identify changed claims**: Compare current claims against content citations
3. **Scan content pages**: Find all content files for `{family}/{platform}` across all sites:
   - `content/docs.aspose.org/en/{family}/{platform}/`
   - `content/blog.aspose.org/{family}/{platform}/`
   - `content/kb.aspose.org/en/{family}/{platform}/`
   - `content/reference.aspose.org/en/{family}/{platform}/`
4. **For each content page**:
   - Read evidence from YAML frontmatter: `evidence.claims` array and `evidence.model_sha`
   - Check if cited claim IDs in `evidence.claims` have changed or been removed in current `claims.json`
   - Check `evidence.model_sha` against current `merged/model.yaml` `repo_sha` — mismatch means stale
   - Check if page references classes/methods that no longer exist
   - Check if page mentions formats whose support status changed
   - Note: `<!-- evidence: ... -->` HTML comment citations are forbidden (AGENTS.md §5); if found, flag page as needing `attach_evidence.py` re-run
5. **Classify staleness**:
   - STALE: Page cites changed/removed claims
   - AT_RISK: Page references changed API surface
   - CURRENT: No changes detected
6. **Write report**

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/skill_context.py end --skill S-13 --status completed
> ```

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

## Translation Integration

After stale-detect identifies modified English source pages, the translate-batch skill
should be invoked to regenerate their translated counterparts:

  Trigger: any English page under content/{site}/en/ is written or updated
  Action: run `python -m translator sync --site {site} --family {family} --platform {platform}`
  Or use the translate-batch skill for explicit batch runs

This integration ensures translations stay in sync with English source changes automatically.
