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

1. **Parse arguments**: Extract `{family}` and `{platform}` (or `all`).

2. **Attempt Tier 1 — Professionalize API**:
   ```bash
   python scripts/pipeline/embed.py {family} {platform} --tier api
   ```
   - If `PROFESSIONALIZE_API_KEY` is set and the call succeeds: vectors written to
     `knowledge/_vectors/{family}/{platform}/api/`.
   - If the API key is missing or the call fails: log "Tier 1 unavailable" and proceed to Tier 2.

3. **Attempt Tier 2 — Ollama (local)**:
   ```bash
   python scripts/pipeline/embed.py {family} {platform} --tier local
   ```
   - If Ollama is running and returns vectors: written to
     `knowledge/_vectors/{family}/{platform}/local/`.
   - If Ollama is not running or returns an error: log "Tier 2 unavailable" and proceed to Tier 3.

4. **Tier 3 — TF-IDF (always available)**:
   - TF-IDF vectors are computed on-demand by consuming skills (S-43, S-45) and do NOT
     produce persistent files. If neither Tier 1 nor Tier 2 succeeded, log:
     "No persistent vectors generated. Gap-eval will use TF-IDF computed on demand."
   - This is not an error — TF-IDF is a valid fallback, just less semantically precise.

5. **Update config**: Write `knowledge/_vectors/config.json` with `last_embedded` timestamps:
   ```json
   {
     "last_embedded": "{ISO timestamp}",
     "tiers_used": ["api", "local"],
     "counts": { "{family}/{platform}": { "api": N, "local": N } }
   }
   ```

6. **Report**: Print which tiers succeeded, which failed, and how many vectors were generated per tier.

## Post-conditions
- If Tier 1 or Tier 2 succeeded: vector files exist in `knowledge/_vectors/{family}/{platform}/{tier}/`.
- `knowledge/_vectors/config.json` is updated with `last_embedded` timestamps.
- Vector counts match claim counts in merged knowledge (within 5% tolerance for filtering).
- If neither Tier 1 nor Tier 2 succeeded: no vector files are created — this is acceptable.
  Log a notice so the user knows gap-eval will use degraded TF-IDF mode.

## Notes
- Tier 1 and Tier 2 use different embedding models — their vectors are NOT interchangeable.
  Each tier has its own subdirectory (`api/`, `local/`) and must not be mixed.
- If neither Tier 1 nor Tier 2 is available, TF-IDF is computed on demand by consuming skills
  (S-43, S-45). The gap-eval verdict will be less precise but still valid.
- Re-running this skill is idempotent: it overwrites existing vectors for the same tier.

## Error handling
- All three tiers fail (Tier 3 cannot fail, so this cannot happen).
- `embed.py` script missing: abort; check that `scripts/pipeline/embed.py` exists.
- `merged/claims.json` is empty (no claims to embed): skip; log "Nothing to embed — run S-35 first."
- `all` mode: process each product independently; failures for one product do not abort others.
