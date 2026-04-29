---
name: embed-knowledge
id: S-15
description: >
  Embed knowledge artifacts into dual vector stores using three-tier
  embedding infrastructure (professionalize.com, Ollama, TF-IDF).
args: "{family} {platform} | all"
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

<!-- CONTRACT: scripts/pipeline/commands/knowledge/embed.py (standard mode)
     postcondition: knowledge/_vectors/api/ exists (if Tier 1 succeeded)
     postcondition: knowledge/_vectors/local/ exists (if Tier 2 succeeded)
     postcondition: paths do NOT include family/platform subdirectories (flat structure)
     postcondition: gap-index mode writes knowledge/_vectors/{family}/{platform}/api.vectors.json
     verified: 2026-04-01
-->
# S-15: Embed Knowledge — Vector Store Generation

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}` or `all`

## Purpose
Embed knowledge artifacts into dual vector stores using the three-tier embedding infrastructure
(Professionalize API → Ollama → TF-IDF). Vectors are consumed by S-43 (gap-eval) and S-45
(gap-report) for semantic similarity search. This skill is optional — content generation does
not require vectors, but gap evaluation quality degrades without them.

## Pre-conditions
1. `knowledge/{family}/{platform}/merged/` must exist with `claims.json`.
2. For Tier 1: `PROFESSIONALIZE_API_KEY` environment variable must be set.
3. For Tier 2: Ollama must be running locally (`curl http://localhost:11434/api/tags` returns 200).
4. Tier 3 (TF-IDF) is always available — no pre-condition.

## Steps

> **Skill context gate** — run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-15 --scope "*"
> ```


1. **Parse arguments**: Extract `{family}` and `{platform}` (or `all`).

2. **Attempt Tier 1 — Professionalize API**:
   ```bash
   .venv/Scripts/python scripts/pipeline/commands/knowledge/embed.py {family} {platform} --tier api
   ```
   - If `PROFESSIONALIZE_API_KEY` is set and the call succeeds: vectors written to
     `knowledge/_vectors/api/` (flat structure — all products share the same tier directory).
   - If the API key is missing or the call fails: log "Tier 1 unavailable" and proceed to Tier 2.

3. **Attempt Tier 2 — Ollama (local)**:
   ```bash
   .venv/Scripts/python scripts/pipeline/commands/knowledge/embed.py {family} {platform} --tier local
   ```
   - If Ollama is running and returns vectors: written to
     `knowledge/_vectors/local/` (flat structure).
   - If Ollama is not running or returns an error: log "Tier 2 unavailable" and proceed to Tier 3.

4. **Tier 3 — TF-IDF (always available)**:
   - TF-IDF vectors are computed on-demand by consuming skills (S-43, S-45) and do NOT
     produce persistent files. If neither Tier 1 nor Tier 2 succeeded, log:
     "No persistent vectors generated. Gap-eval will use TF-IDF computed on demand."
   - This is not an error — TF-IDF is a valid fallback, just less semantically precise.

5. **Update config**: Update `knowledge/_vectors/config.json` with `last_embedded` per tier:
   ```json
   {
     "tiers": [
       { "id": "api", "provider": "professionalize", "last_embedded": "{ISO timestamp}", ... },
       { "id": "local", "provider": "ollama", "last_embedded": "{ISO timestamp}", ... }
     ],
     "active_tier": "api",
     "claim_count": N,
     "content_chunk_count": N
   }
   ```
   Note: config.json is only updated when ALL attempted tiers succeed. If any tier fails,
   config.json is left unchanged to preserve consistency with the actual vector files on disk.

6. **Report**: Print which tiers succeeded, which failed, and how many vectors were generated per tier.

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-15 --status completed
> ```

## Post-conditions
- If Tier 1 or Tier 2 succeeded: vector files exist under `knowledge/_vectors/{tier}/`
  (e.g., `knowledge/_vectors/api/claims.vectors.json`, `knowledge/_vectors/api/api.vectors.json`).
- `knowledge/_vectors/config.json` is updated with `last_embedded` timestamps (only when all
  attempted tiers succeed — see step 5 note).
- Vector counts match claim counts in merged knowledge (within 5% tolerance for filtering).
- If neither Tier 1 nor Tier 2 succeeded: no vector files are created — this is acceptable.
  Log a notice so the user knows gap-eval will use degraded TF-IDF mode.

## Gap-index mode (S-43 Tier 2)
For per-product API surface vectors (used by S-43), use the `gap-index` subcommand instead:
```bash
python scripts/pipeline/commands/knowledge/embed.py gap-index {family} {platform}
```
This mode writes to `knowledge/_vectors/{family}/{platform}/api.vectors.json` (with
family/platform subdirectories). It is a separate operation from standard knowledge embedding.

## Notes
- Tier 1 and Tier 2 use different embedding models — their vectors are NOT interchangeable.
  Each tier has its own flat subdirectory under `knowledge/_vectors/` (`api/`, `local/`) and
  must not be mixed.
- If neither Tier 1 nor Tier 2 is available, TF-IDF is computed on demand by consuming skills
  (S-43, S-45). The gap-eval verdict will be less precise but still valid.
- Re-running this skill is idempotent: it overwrites existing vectors for the same tier.

## Error handling
- All three tiers fail (Tier 3 cannot fail, so this cannot happen).
- `embed.py` script missing: abort; check that `scripts/pipeline/commands/knowledge/embed.py` exists.
- `merged/claims.json` is empty (no claims to embed): skip; log "Nothing to embed — run S-35 first."
- `all` mode: process each product independently; failures for one product do not abort others.
