# S-35: Truth Merge - Scout-Only Promotion with Enrichment

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}`

## Purpose

Promote `knowledge/{family}/{platform}/scout/` plus any `scout/enriched_claims.json`
enrichment into `knowledge/{family}/{platform}/merged/`, applying provenance tagging and
current runtime rules. The FL layer has been removed.

## Pre-conditions

1. `scout/claims.json` must exist and be valid JSON with a `claims` array.
2. `scout/enriched_claims.json` is optional but must be used when present.
3. If both exist, both must refer to the same product (family/platform match in `model.yaml`).
4. `scout/api_surface.json` must exist — it is the validation source for enriched claim hallucination detection.

## Automated Script

Run the promotion engine first, then review:
```bash
python scripts/pipeline/promote.py {family} {platform}
```
Review `knowledge/{family}/{platform}/merged/merge_report.md` for scout/enriched promotion counts.

## Conflict Detection Algorithm

A **conflict** exists when:
- A claim in `enriched_claims.json` makes a factual assertion (capability, format, API) that
  directly contradicts a claim in `scout/claims.json` on the same subject.
- Specifically: enriched `kind=format` claim lists a format as supported when `scout/formats.json`
  lists it as `not_implemented`, OR an enriched `kind=capability` claim asserts a feature that
  `scout/limitations.md` documents as unimplemented.

**Conflict resolution rules**:
- Scout wins over enrichment on factual contradictions. The scout claim is kept; the conflicting
  enriched claim is excluded and recorded in `merged/merge_conflicts.md`.
- Enriched claims that ADD information without contradicting scout (elaborating, explaining, rephrasing)
  are kept regardless of overlap.
- If `merged/merge_conflicts.md` would contain more than 10% of total enriched claims, set
  `has_conflicts: true` in `merged/model.yaml` and stop. Do not proceed to content generation
  until the user reviews the conflict report.

## Provenance Tagging Algorithm

Every claim in `merged/claims.json` must have a `provenance` object with these fields:

```json
{
  "source": "scout_only | scout_plus_enriched",
  "scout_claim_id": "CLM-xxx | null",
  "enriched_claim_id": "ENRICH-xxx | null",
  "confidence": 0.0–1.0,
  "validated": true | false
}
```

- `source = "scout_only"` when: only a scout claim exists, OR enrichment was absent/rejected.
- `source = "scout_plus_enriched"` when: both a scout claim and a validated enriched claim
  exist for the same subject. `confidence = max(scout_confidence, enriched_confidence)`.
- `validated = true` when: the claim's API names were verified against `api_surface.json`.
- `validated = false` when: the claim references a class or method not in `api_surface.json`
  (this should be rare for scout claims; more common for enriched claims). Unvalidated claims
  are included in merged but must not be used in content generation.

**Hallucination rejection**: An enriched claim is rejected (excluded entirely) if:
- It references a class name not in `scout/api_surface.json`, OR
- It references a method name not in the class's `methods` array in `api_surface.json`.
The rejected claim is recorded in `merged/merge_conflicts.md` under a `## Hallucinated Claims` section.

## Provenance rules summary

| Scout | Enriched claim | Result |
|-------|-----------------|--------|
| Present | Present and validated | `scout_plus_enriched`, confidence = max |
| Present | Absent / rejected | `scout_only` |
| Present | Present but hallucinated / invalid | `scout_only`; invalid enrichment excluded and logged |
| Present | Present but contradicts scout | Scout wins; conflict logged in `merge_conflicts.md` |

## Output Schema

After promotion, `merged/` must contain these files:

**`merged/model.yaml`** — authoritative metadata:
```yaml
family: {family}
platform: {platform}
source: "scout_only | scout_plus_enriched"
repo_sha: "{from scout/model.yaml}"
last_merged: "{ISO timestamp}"
stale_since: null
has_conflicts: true | false
api_confidence: "high | medium | low"
```

**`merged/claims.json`** — all promoted claims with provenance:
```json
{
  "claims": [
    {
      "claim_id": "CLM-xxx",
      "subject": "ClassName",
      "predicate": "supports|can|has|implements",
      "object": "...",
      "kind": "capability|format|api|limitation",
      "confidence": 0.0–1.0,
      "provenance": { "source": "...", "scout_claim_id": "...", "enriched_claim_id": "...", "confidence": 0.0, "validated": true }
    }
  ]
}
```

**`merged/merge_report.md`** — human-readable promotion summary:
```markdown
# Merge Report: {family}/{platform}
Merged: {ISO timestamp}

## Stats
- Scout claims: {N}
- Enriched claims input: {N}
- Enriched claims accepted: {N}
- Enriched claims rejected (hallucination): {N}
- Conflicts (scout wins): {N}
- Final merged claims: {N}

## Source
- source: scout_only | scout_plus_enriched
- api_confidence: high | medium | low
```

**`merged/merge_conflicts.md`** — only written when `has_conflicts: true`:
```markdown
# Merge Conflicts: {family}/{platform}

## Contradicted Claims (Scout Wins)
- ENRICH-xxx contradicts CLM-yyy on subject {ClassName}: enriched said "{X}", scout says "{Y}"

## Hallucinated Claims (Rejected)
- ENRICH-xxx: references {ClassName}.{method} — not in api_surface.json
```

## Post-conditions

- `merged/` directory has all required files listed above.
- Every claim in `merged/claims.json` has a valid `provenance` field.
- `merged/model.yaml` has `source: "scout_only"` or `source: "scout_plus_enriched"`.
- `merged/model.yaml` has `has_conflicts: false` (or `true` with `merge_conflicts.md` present).
- `merged/api_surface.md` is generated for LLM prompt grounding.
- If `has_conflicts: true` and conflict count > 10% of total enriched claims: STOP; ask user to review `merge_conflicts.md`.

## Error handling

- `scout/claims.json` missing or invalid JSON: abort; run S-34 (repo-scout) first.
- `scout/api_surface.json` missing: abort; run S-34 (repo-scout) first.
- `enriched_claims.json` malformed (not valid JSON): skip enrichment entirely; proceed as `scout_only`.
- `promote.py` script fails: print the error; do not partially write `merged/`; leave existing `merged/` intact.
- All enriched claims rejected (100% hallucination rate): proceed as `scout_only`; log a WARN in `merge_report.md`.
