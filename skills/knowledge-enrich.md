<!-- CONTRACT: scripts/pipeline/commands/knowledge/enrich.py
     postcondition: scout/enriched_claims.json exists as a JSON array
     postcondition: claim_id format is ERC-{family}-{platform}-{8-char-hash}
     postcondition: claim fields are: claim_id, text, kind, confidence, claim_source, evidence
     postcondition: all claims have confidence >= 0.60 (lower dropped before write)
     verified: 2026-04-01
-->
# S-37: Knowledge Enrich - LLM Semantic Enrichment from Scout Artifacts

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}`

## Purpose

Generate LLM-enriched semantic claims from `knowledge/{family}/{platform}/scout/`
artifacts. The enrichment step reads verified API facts from `scout/api_surface.json`,
uses the clone cache for bounded context, and writes `scout/enriched_claims.json`.
This is the current replacement for the removed FL enrichment layer.

## Pre-conditions

1. `knowledge/{family}/{platform}/scout/api_surface.json` must exist.
2. `runs/.clone_cache/aspose_{family}_{platform}/` should exist for richer context.
3. `scripts/pipeline/commands/knowledge/enrich.py` must exist.

## Steps

> **Skill context gate** — run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-37 --scope "*"
> ```


1. Parse `{family}` and `{platform}` from `$ARGUMENTS`.
2. Verify `knowledge/{family}/{platform}/scout/api_surface.json` exists.
3. Run:
   ```bash
   .venv/Scripts/python scripts/pipeline/commands/knowledge/enrich.py {family} {platform}
   ```
   Optional flags:
   - `--knowledge-root <path>` to override the knowledge root
   - `--no-llm` to skip the LLM call and write an empty enrichment file
4. Verify `knowledge/{family}/{platform}/scout/enriched_claims.json` exists and is valid JSON.
5. Report the number of enriched claims written.

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-37 --status completed
> ```

## Output Schema

`scout/enriched_claims.json` is a JSON array (not a wrapped object) conforming to this schema:

```json
[
  {
    "claim_id": "ERC-{family}-{platform}-{8-char-hash}",
    "text": "human-readable claim about the API or feature",
    "kind": "api | feature | format | install | troubleshoot",
    "confidence": 0.75,
    "claim_source": "llm_enriched",
    "evidence": [
      { "source_file": "relative/path/to/source.py", "snippet": "relevant code or doc excerpt" }
    ]
  }
]
```

**Field rules**:
- `claim_id`: Stable hash-based ID. Format: `ERC-{family}-{platform}-{sha256_8chars}` where the
  hash is derived from `text + kind`. Assigned automatically by `enrich.py`.
- `text`: The complete, self-contained claim text. Grounded in `api_surface.json` evidence.
  Claims whose text contains CamelCase words not in `api_surface.json` are dropped (hallucination
  guard in `_validate_claim()`).
- `kind`: Must be one of `api`, `feature`, `format`, `install`, `troubleshoot`.
- `confidence`: LLM-assigned confidence. Claims with `confidence < 0.60` are dropped before
  writing. No claims below this threshold appear in the output file.
- `claim_source`: Always `"llm_enriched"` for LLM-generated claims.
- `evidence`: Source grounding — the file excerpts the LLM used to generate the claim.

## Post-conditions

- `scout/enriched_claims.json` exists as a JSON array (may be `[]` if `--no-llm` was used
  or LLM was unavailable).
- All `claim_id` values use `ERC-{family}-{platform}-{hash}` format and are unique within the file.
- All claims pass the hallucination guard: any claim whose text contains CamelCase words absent
  from `api_surface.json` is excluded before writing.
- All claims have `confidence >= 0.60` — lower-confidence claims are dropped.
- The enrichment is grounded in `api_surface.json`, not in fabricated API names.

## LLM Fallback Sequence

If the primary LLM endpoint is unavailable:

1. **Retry once** (transient network failure).
2. **Fall back to `--no-llm` mode**: Write `enriched_claims.json` as an empty JSON array `[]`.
   - Downstream impact: S-35 (truth-merge) will proceed as `scout_only`.
   - Content generation proceeds with scout claims only — no enrichment. This is safe but
     produces less semantically rich content.
3. **Do NOT abort** — empty enrichment is a valid output. Log: "LLM unavailable; proceeding
   with empty enrichment. Run S-37 again with LLM access to improve claim quality."

If the LLM returns claims that fail hallucination detection (subject not in api_surface.json):
- Exclude those claims.
- If ALL claims are hallucinated (100% rejection), write `claims: []` and log the rejection.
- Do NOT write the hallucinated claims under any circumstances.

## Chain

```
S-34 (repo-scout) -> S-37 (knowledge-enrich) -> S-35 (truth-merge) -> S-31 (truth-index)
```

## Error handling

- Missing scout artifacts: abort and run S-34 (repo-scout) first.
- LLM unavailable: follow the fallback sequence above; write `claims: []` and continue.
- Invalid hallucinated claims: reject them individually; write only validated claims.
- `enrich.py` script error (non-zero exit): do not write partial output; leave any existing
  `enriched_claims.json` intact; print the script error.
- `enriched_claims.json` already exists from a prior run: the script overwrites it; this is safe.

---

## LLM Metrics Obligation

If this skill invokes `llm.professionalize.com` directly or through `LLMRouter`,
the run carries a **metrics obligation** (METRICS-PLAN-001, `AGENTS.md §15`):

- All professionalize calls must use `ProfessionalizeClient`, `LLMRouter`, or a
  registered adapter entry in `metrics_callsite_registry.yaml`.
- Each run must capture per-call `MetricsEvent` records and aggregate them into a
  validated `MetricsRow` via `RunMetrics`.
- Default mode is **dry-run**. Live posting requires explicit owner approval and
  `AGENT_METRICS_ENDPOINT` / `AGENT_METRICS_TOKEN` set locally.
- Non-professionalize calls (Gemini, Ollama, M2M) are excluded from
  `token_usage` and `api_calls_count`.
- Metrics failures must not crash or block the parent pipeline job.
