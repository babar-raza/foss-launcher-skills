---
name: page-update
id: S-20
description: >
  Update an existing content page after knowledge has been refreshed by S-14.
  Applies targeted changes based on claim, API, and format differences.
args: "{content-file-path}"
---

# S-20: Page Update — Post-Knowledge-Refresh Content Update

**Arguments**: $ARGUMENTS
Expected format: `{content-file-path}`

## Purpose
Update an existing content page after S-14 (knowledge-update) has refreshed the knowledge model. Compares the page's existing citations against the current knowledge to identify what needs changing.

## Pre-conditions
1. Content file must exist
2. Knowledge model must exist and must NOT be stale (S-14 should have cleared staleness)
3. Recommended: S-13 stale report identifies this page as STALE or AT_RISK

## Steps

1. **Read the content file** at $ARGUMENTS

2. **Identify product**: Extract `{family}` and `{platform}` from path

3. **Load current knowledge**: `index.json`, `claims.json`, `api_surface.json`, `formats.json`

4. **Extract existing citations**: Parse all `<!-- evidence: claim_id=X -->` comments in the file
   - Build a list of referenced claim_ids
   - Build a list of referenced API names
   - Build a list of referenced format claims

5. **Identify citation changes**:
   a. **Orphaned citations**: claim_ids that no longer exist in claims.json
      - The paragraphs containing these need rewriting or removal
   b. **Modified claims**: claim_ids that exist but with changed text or confidence
      - The paragraphs may need updating to match new claim wording
   c. **New relevant claims**: claims in claims.json not yet covered by the page
      - May warrant new sections (only if high confidence and high relevance)

6. **Identify API changes**:
   a. **Removed API**: class/method names in content not in current api_surface.json
      - Code blocks using removed API must be rewritten or removed
   b. **Renamed API**: methods that were renamed (detect via similar signatures)
      - Find-and-replace in both prose and code blocks
   c. **New API**: methods added that are relevant to the page topic
      - May warrant new code examples

7. **Identify format changes**:
   a. Format claims in content that now contradict formats.json
      - Correct the direction (import/export/both) or remove
   b. New format support added
      - Update format tables if present

8. **Apply updates**:
   - Rewrite paragraphs with orphaned citations using current claims
   - Update code blocks with renamed/removed API
   - Correct format claims
   - Add new sections for significant new claims (confidence >= 0.8 only)
   - Preserve the page structure and template compliance

9. **Update frontmatter**: Set `lastmod` to today's date

10. **Write updated content** back to the file

## Output

```
PAGE UPDATE — {content-file-path}
Knowledge: {family}/{platform} (sha: {repo_sha})

Changes applied:
  Orphaned citations rewritten: {n}
  Modified claims updated:      {n}
  API references corrected:     {n}
  Format claims fixed:          {n}
  New sections added:           {n}

Items requiring human review:
  {list of changes that could not be automated}
```

## Post-conditions
- After updating, the chain continues:
  1. S-23 (ground-check) — verify updated content passes truth gate
  2. S-24 (evidence-cite) — refresh citations for new/changed content
  3. S-01 (path-guard) — validate write path

## Error handling
- If no citations found in file → treat as ungrounded page, recommend S-17/S-21 enhancement instead
- If knowledge is stale → abort, run S-14 first
- If >50% of page content is affected → flag for human review (major rewrite needed)
