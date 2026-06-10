# S-15: Embed Knowledge — Vector Store Generation

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}` or `all`

## Purpose
Embed knowledge artifacts into dual vector stores using the three-tier embedding infrastructure (professionalize.com → Ollama → TF-IDF).

## Pre-conditions
1. `knowledge/{family}/{platform}/merged/` must exist
2. For Tier 1: `PROFESSIONALIZE_API_KEY` environment variable must be set
3. For Tier 2: Ollama must be running locally (`curl http://localhost:11434/api/tags`)
4. Tier 3 (TF-IDF) is always available as last resort

## Steps

1. **Parse arguments**: `{family} {platform}` or `all`
2. **Run embedding**: `python scripts/pipeline/commands/knowledge/embed.py {family} {platform}`
3. **Verify outputs**: Check that vector files were created in `knowledge/_vectors/`
4. **Report**: Print which tiers were used and how many vectors were generated

## Post-conditions
- At least one tier of vectors exists in `knowledge/_vectors/`
- `knowledge/_vectors/config.json` is updated with `last_embedded` timestamps
- Vector counts match claim counts in merged knowledge

## Notes
- Tier 1 and Tier 2 use different models, so vectors are NOT interchangeable
- Each tier has its own subdirectory (`api/`, `local/`)
- If neither Tier 1 nor Tier 2 is available, TF-IDF is computed on demand by consuming skills
