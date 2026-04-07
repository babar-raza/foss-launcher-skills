---
name: knowledge-update
id: S-14
description: >
  Refresh the knowledge model from source using scout, enrich, promote, and index.
args: "{family} {platform}"
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

<!-- CONTRACT: scripts/pipeline/refresh_knowledge.py (runs scout.py + enrich.py + promote.py + index.py)
     postcondition: refresh_knowledge.py executes all 4 pipeline steps (scout → enrich → promote → index)
     postcondition: writes merged/pipeline_run.json confirming all 4 steps ran and index_succeeded status
     postcondition: refresh_knowledge.py auto-clears stale_since in merged/model.yaml on successful refresh
     verified: 2026-04-07
-->
# S-14: Knowledge Update - Refresh Knowledge Model from Source

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}`

## Clone Cache Resolution

The script resolves the repo path automatically from the local clone cache. No `{repo-path}` argument
is needed. If the clone cache directory is missing, the script auto-clones from `clone_url` in
`data/products.json` (disable with `--no-auto-clone`).

Override the cache root with `ASPOSE_CLONE_CACHE=/path/to/cache` if needed.

## Purpose

Refresh the knowledge model for a product by re-running the full knowledge pipeline:
repo-scout, knowledge-enrich, truth-merge, and truth-index. Use this when `model.yaml`
has `stale_since != null` or after upstream repo changes detected by S-12 (knowledge-diff).

> **Note on `refresh_knowledge.py`**: Running `python scripts/pipeline/refresh_knowledge.py
> {family} {platform}` executes all 4 pipeline steps: `scout.py → enrich.py → promote.py → index.py`.
> After a successful run, `merged/pipeline_run.json` confirms all steps completed and
> `merged/model.yaml` has `stale_since` cleared automatically.

## Pre-conditions

1. `scripts/pipeline/scout.py` exists
2. `scripts/pipeline/enrich.py` exists
3. `scripts/pipeline/promote.py` exists
4. `scripts/pipeline/index.py` exists
5. Current knowledge exists at `knowledge/{family}/{platform}/` (at least `model.yaml`)
6. Check `knowledge/{family}/{platform}/model.yaml` - if `stale_since` is null, warn that
   knowledge may not need updating (proceed if user confirms)

## Steps

1. **Parse arguments**: Extract `{family}` and `{platform}` from $ARGUMENTS.

2. **Back up current knowledge**: Copy `knowledge/{family}/{platform}/merged/` to
   `knowledge/{family}/{platform}/merged.bak/` so diffs can be computed later by S-20.

3. **Run refresh pipeline**:
   ```
   python scripts/pipeline/refresh_knowledge.py {family} {platform}
   ```
   This single command runs scout → enrich → promote → index in sequence.
   Verify `knowledge/{family}/{platform}/merged/pipeline_run.json` confirms all steps ran.
   Verify outputs: `model.yaml`, `api_surface.json`, `claims.json` in `knowledge/{family}/{platform}/scout/`.

4. **Run knowledge-enrich** (S-37):
   ```
   python scripts/pipeline/enrich.py {family} {platform}
   ```
   Verify `knowledge/{family}/{platform}/scout/enriched_claims.json` exists and is valid JSON.

5. **Run truth-merge** (S-35):
   ```
   python scripts/pipeline/promote.py {family} {platform}
   ```
   Verify `knowledge/{family}/{platform}/merged/merge_report.md` exists and shows merge statistics.

6. **Run truth-index** (S-31):
   Generate the knowledge index from the merged artifacts. Verify `knowledge/{family}/{platform}/merged/index.json` is created.

7. **Verify stale flag cleared**: Confirm `knowledge/{family}/{platform}/merged/model.yaml` has
   `stale_since: null`. This is now automated by `refresh_knowledge.py` — no manual edit needed.

8. **Diff report**: Compare `merged.bak/claims.json` with `merged/claims.json` to summarize:
   - New claims added
   - Claims removed
   - Claims with changed confidence
   - API surface additions/removals

9. **Clean up**: Remove `merged.bak/` after diff report is generated.

## Post-conditions

- `knowledge/{family}/{platform}/scout/` has fresh extraction artifacts
- `knowledge/{family}/{platform}/merged/` has updated merged artifacts
- `model.yaml` has `stale_since: null` and current `repo_sha`
- A diff summary is printed showing what changed

## Error handling

- If repo-scout fails, abort and preserve existing knowledge (do not corrupt merged/)
- If promote fails, restore from `merged.bak/`
- If clone cache is missing, script auto-clones from `clone_url` in `data/products.json`; use `--no-auto-clone` to disable
