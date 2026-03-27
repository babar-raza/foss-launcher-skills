# S-14: Knowledge Update — Refresh Knowledge Model from Source

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform} {repo-path}`

## Purpose
Refresh the knowledge model for a product by re-running the full knowledge bootstrap pipeline: repo-scout, truth-merge, and truth-index. Use this when `model.yaml` has `stale_since != null` or after upstream repo changes detected by S-12 (knowledge-diff).

## Pre-conditions
1. The repo at `{repo-path}` must be accessible and is a git repository
2. `scripts/pipeline/scout.py` exists
3. `scripts/pipeline/merge.py` exists
4. Current knowledge exists at `knowledge/{family}/{platform}/` (at least `model.yaml`)
5. Check `knowledge/{family}/{platform}/model.yaml` — if `stale_since` is null, warn that knowledge may not need updating (proceed if user confirms)

## Steps

1. **Parse arguments**: Extract `{family}`, `{platform}`, and `{repo-path}` from $ARGUMENTS.

2. **Back up current knowledge**: Copy `knowledge/{family}/{platform}/merged/` to `knowledge/{family}/{platform}/merged.bak/` so diffs can be computed later by S-20.

3. **Run repo-scout** (S-34):
   ```
   python scripts/pipeline/scout.py {family} {platform} {repo-path} knowledge/{family}/{platform}/scout/
   ```
   Verify outputs: `model.yaml`, `api_surface.json`, `claims.json` in `knowledge/{family}/{platform}/scout/`.

4. **Run truth-merge** (S-35):
   ```
   python scripts/pipeline/merge.py {family} {platform}
   ```
   Verify `knowledge/{family}/{platform}/merged/merge_report.md` exists and shows merge statistics.

5. **Run truth-index** (S-31):
   Generate the knowledge index from the merged artifacts. Verify `knowledge/{family}/{platform}/merged/index.json` is created.

6. **Clear stale flag**: Update `knowledge/{family}/{platform}/model.yaml` to set `stale_since: null` and update `last_refreshed` to today's date.

7. **Diff report**: Compare `merged.bak/claims.json` with `merged/claims.json` to summarize:
   - New claims added
   - Claims removed
   - Claims with changed confidence
   - API surface additions/removals

8. **Clean up**: Remove `merged.bak/` after diff report is generated.

## Post-conditions
- `knowledge/{family}/{platform}/scout/` has fresh extraction artifacts
- `knowledge/{family}/{platform}/merged/` has updated merged artifacts
- `model.yaml` has `stale_since: null` and current `repo_sha`
- A diff summary is printed showing what changed

## Error handling
- If repo-scout fails, abort and preserve existing knowledge (do not corrupt merged/)
- If merge fails, restore from `merged.bak/`
- If repo path is unreachable, abort with clear message
