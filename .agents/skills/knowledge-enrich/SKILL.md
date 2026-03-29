---
name: knowledge-enrich
id: S-37
description: >
  Generate LLM-enriched semantic claims from scout artifacts. Reads
  scout/api_surface.json and clone cache source, calls LLM in bounded-description
  mode, and writes scout/enriched_claims.json. No FOSS Launcher dependency.
args: "{family} {platform}"
---

> Cross-skill references like `/repo-scout` refer to sibling skills in this directory.

# S-37: Knowledge Enrich — LLM Semantic Enrichment from Scout Artifacts

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}`

## Purpose

Generate LLM-enriched semantic claims for a product by:
1. Reading the deterministic API surface from `scout/api_surface.json` (verified facts)
2. Reading source context from the internal clone cache (`runs/.clone_cache/`)
3. Calling the LLM in **bounded-description mode**: produce one user-facing claim per
   verified API fact, constrained to only reference identifiers that exist in the API surface
4. Writing deduplicated, validated claims to `scout/enriched_claims.json`

This replaces the FOSS Launcher FL layer with fresh, locally-generated enrichment that
can be re-run on demand whenever the scout knowledge is updated.

## Pre-conditions

1. **Scout artifacts exist** — `knowledge/{family}/{platform}/scout/api_surface.json` must be present.
   If missing, run S-34 (`/repo-scout {family} {platform}`) first.

2. **Clone cache populated** — `runs/.clone_cache/aspose_{family}_{platform}/` should exist for
   best source context. If absent, enrichment still runs but with minimal context (README-only).

3. **`fl/` must NOT exist** — `knowledge/{family}/{platform}/fl/` must not be present.
   The FL layer has been removed. If it exists, delete it before running this skill.

4. **Verify `scripts/pipeline/enrich.py` exists**:
   ```
   ls scripts/pipeline/enrich.py
   ```

## Steps

1. **Parse arguments** from $ARGUMENTS: `family`, `platform`

2. **Check pre-conditions**:
   ```
   ls knowledge/{family}/{platform}/scout/api_surface.json
   ```
   Abort if missing.

3. **Run enrichment**:
   ```
   python scripts/pipeline/enrich.py {family} {platform}
   ```
   This will:
   - Build a verified-facts block from api_surface.json (up to 80 classes)
   - Collect source context from clone cache (README, docs, examples — up to 12 000 chars)
   - Call `llm.professionalize.com` (gpt-oss) with temperature=0.0 in bounded-description mode
   - Fall back to Ollama llama3.2 if `PROFESSIONALIZE_API_KEY` is not set
   - Validate claims: reject hallucinations (CamelCase names not in API surface), low-confidence, duplicates
   - Write `knowledge/{family}/{platform}/scout/enriched_claims.json`

4. **Validate output** — verify file was created:
   - `knowledge/{family}/{platform}/scout/enriched_claims.json` — valid JSON, `claim_count >= 0`

5. **Report** — print summary:
   ```
   {family}/{platform}: {N} enriched claims written to scout/enriched_claims.json
   model: {gpt-oss|llama3.2|none}
   ```

## Post-conditions
- `scout/enriched_claims.json` exists with keys: `generated_at`, `model`, `source`, `claim_count`, `claims`
- `claims` is a JSON array (may be empty if LLM was unavailable — this is not an error)
- All claims have `claim_source: "llm_enriched"` and `claim_id` starting with `ERC-`
- `.pipeline_state.json` records step `enrich` as completed

## Chain

```
S-34 (repo-scout) → S-37 (knowledge-enrich) → S-35 (promote) → S-31 (truth-index)
```

Run S-37 after S-34 completes and before S-35 (promote.py).

## Claim provenance

Enriched claims appear in `merged/claims.json` with `provenance: "enriched"`.
They are grounded in `api_surface.json` (verified facts) and therefore cannot reference
phantom API members — this is enforced both in the prompt and in post-LLM validation.

## Error handling

| Condition | Behaviour |
|-----------|-----------|
| `scout/api_surface.json` missing | Abort: `run S-34 first` |
| `fl/` directory present | Abort: `FL layer removed — delete fl/ first` |
| LLM unreachable | Write empty `enriched_claims.json` (graceful degradation) |
| All claims rejected by validator | Write empty `enriched_claims.json` + warning |
| Clone cache absent | Enrich with minimal context (README only) |

## Skip condition

`scout/enriched_claims.json` already exists and `api_surface_sha` matches current
`scout/api_surface.json` → skip re-enrichment (idempotent). Delete the file to force re-run.
