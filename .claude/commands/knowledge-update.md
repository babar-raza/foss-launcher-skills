# S-14: Knowledge Update — Refresh Knowledge from Source

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform} {repo-path}`

## Purpose
Refresh the knowledge model after S-12 (knowledge-diff) detected upstream repository changes and S-13 (stale-detect) identified affected content. Orchestrates the full knowledge pipeline: scout → merge → index → embed.

## Pre-conditions
1. S-12 diff report or S-13 stale report should exist (recommended but not mandatory)
2. The FOSS repository at `{repo-path}` must be accessible
3. Current knowledge directory should exist: `knowledge/{family}/{platform}/`

## Steps

1. **Record pre-update state**:
   - Read current `knowledge/{family}/{platform}/merged/model.yaml`
   - Note current `repo_sha`, `claim_count`, `last_merged`
   - These will be compared post-update to summarize changes

2. **Re-scout the repository** (S-34 repo-scout):
   - Run: `python scripts/scout.py {family} {platform} {repo-path} knowledge/{family}/{platform}/scout/`
   - Verify outputs: model.yaml, api_surface.json, claims.json, formats.json, class_graph.json
   - If scout fails → abort with error details

3. **Re-sync external source** (S-30 truth-sync, if external source configured):
   - Check if `knowledge/{family}/{platform}/external/` exists
   - If found → invoke S-30 truth-sync to refresh it from the original source
   - If not found → skip (scout-only mode, which is the default)

4. **Re-merge sources** (S-35 truth-merge):
   - Run: `python scripts/merge.py {family} {platform}`
   - Verify outputs in `knowledge/{family}/{platform}/merged/`
   - Note any new conflicts in `merge_conflicts.md`

5. **Re-index** (S-31 truth-index):
   - Run: `python scripts/index.py {family} {platform}`
   - Verify `knowledge/{family}/{platform}/merged/index.json` is updated

6. **Re-embed** (S-15 embed-knowledge, if vectors existed):
   - Check if `knowledge/_vectors/{tier}/{family}/{platform}/` has existing vectors for this product
   - If yes → run: `python scripts/embed.py {family} {platform}`
   - If no → skip (embeddings not yet initialized for this product)

7. **Clear staleness**:
   - Update `knowledge/{family}/{platform}/merged/model.yaml`:
     - Set `stale_since: null`
     - Update `repo_sha` to new value
     - Update `last_diff_check` to current timestamp

8. **Compute change summary**:
   - Claims added: new claims not in pre-update set
   - Claims removed: pre-update claims no longer present
   - Claims modified: same claim_id with changed text or confidence
   - API changes: classes/methods added or removed
   - Format changes: format support added or removed

## Output

```
KNOWLEDGE UPDATE — {family}/{platform}
Repository: {repo-path}

Pipeline results:
  Scout:  {OK | FAILED}
  Sync:   {OK | SKIPPED | FAILED}
  Merge:  {OK | FAILED} ({n} conflicts)
  Index:  {OK | FAILED}
  Embed:  {OK | SKIPPED | FAILED}

Previous SHA: {old_sha}
Current SHA:  {new_sha}

Changes:
  Claims added:    {n}
  Claims removed:  {n}
  Claims modified: {n}
  API added:       {n} classes, {n} methods
  API removed:     {n} classes, {n} methods
  Formats changed: {n}

Staleness: CLEARED
Next step: Run /page-update on affected content pages (see S-13 stale report)
```

## Post-conditions
- `stale_since` is null in model.yaml
- All knowledge artifacts are refreshed
- If there are affected content pages (from S-13) → run S-20 (page-update) for each

## Error handling
- If scout fails → abort entire update, keep old knowledge intact
- If merge fails → abort, keep old merged/ intact
- If only embed fails → continue (embeddings are optional)
- If repo-path doesn't exist → abort with clear message
- Log all pipeline step results for debugging
