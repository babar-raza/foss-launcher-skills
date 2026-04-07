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
     postcondition: refresh_knowledge.py creates merged.bak/ before pipeline, writes knowledge_delta.json
                    after successful promote, then deletes merged.bak/ in finally block (always cleaned up)
     postcondition: knowledge_delta.json contains base_sha, current_sha, new_claims, removed_claims,
                    modified_claims, new_apis, removed_apis, modified_apis
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
> After a successful run, `merged/pipeline_run.json` confirms all steps completed,
> `merged/model.yaml` has `stale_since` cleared automatically, and `merged/knowledge_delta.json`
> is written with the semantic diff of what changed.

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

2. **Run refresh pipeline** (handles backup, diff, and cleanup internally):
   ```
   python scripts/pipeline/refresh_knowledge.py {family} {platform}
   ```
   Internally, `refresh_knowledge.py`:
   - Sets `stale_since` in `merged/model.yaml` to today before running the pipeline
   - Creates a temporary backup of `merged/` to `merged.bak/` for delta computation
   - Runs scout → enrich → promote → index in sequence
   - After successful `promote.py`, writes `knowledge_delta.json` to `merged/` with the
     semantic diff (new/removed/modified claims and APIs)
   - Clears `stale_since` in `merged/model.yaml` after success
   - Always deletes `merged.bak/` on exit (success or failure) — never committed

   Verify `knowledge/{family}/{platform}/merged/pipeline_run.json` confirms all steps ran.
   Verify outputs: `model.yaml`, `api_surface.json`, `claims.json` in `knowledge/{family}/{platform}/scout/`.

3. **Run knowledge-enrich** (S-37) if not already run by refresh pipeline:
   ```
   python scripts/pipeline/enrich.py {family} {platform}
   ```
   Verify `knowledge/{family}/{platform}/scout/enriched_claims.json` exists and is valid JSON.

4. **Run truth-merge** (S-35) if not already run:
   ```
   python scripts/pipeline/promote.py {family} {platform}
   ```
   Verify `knowledge/{family}/{platform}/merged/merge_report.md` exists and shows merge statistics.

5. **Run truth-index** (S-31):
   Generate the knowledge index from the merged artifacts. Verify `knowledge/{family}/{platform}/merged/index.json` is created.

6. **Verify stale flag cleared**: Confirm `knowledge/{family}/{platform}/merged/model.yaml` has
   `stale_since: null`. This is automated by `refresh_knowledge.py` — no manual edit needed.

7. **Diff report**: Read `merged/knowledge_delta.json` to summarize:
   - New claims added (`new_claims`)
   - Claims removed (`removed_claims`)
   - Claims with changed text or confidence (`modified_claims`)
   - API surface additions/removals (`new_apis`, `removed_apis`, `modified_apis`)

   Note: `merged.bak/` is NOT available here — cleanup was automatic inside `refresh_knowledge.py`.
   The `knowledge_delta.json` file is the durable diff artifact for downstream skills (S-20, S-62 --update).

## Post-conditions

- `knowledge/{family}/{platform}/scout/` has fresh extraction artifacts
- `knowledge/{family}/{platform}/merged/` has updated merged artifacts
- `model.yaml` has `stale_since: null` and current `repo_sha`
- `merged/knowledge_delta.json` exists with semantic diff of what changed
- `merged.bak/` does NOT exist (always cleaned up by refresh_knowledge.py)
- A diff summary is printed showing what changed

## Error handling

- If repo-scout fails, abort and preserve existing knowledge (do not corrupt merged/)
- If promote fails, `knowledge_delta.json` is NOT written (no partial delta); `merged.bak/` is cleaned up
- If clone cache is missing, script auto-clones from `clone_url` in `data/products.json`; use `--no-auto-clone` to disable
