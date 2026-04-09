<!-- CONTRACT: scripts/pipeline/promote.py
     postcondition: merged/claims.json exists (flat JSON array of claims with string provenance)
     postcondition: merged/model.yaml exists (source always "scout_only", has_conflicts always false)
     postcondition: merged/merge_report.md exists
     postcondition: merged/merge_conflicts.md does NOT exist (deleted by script if present)
     verified: 2026-04-01
-->
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
.venv/Scripts/python scripts/pipeline/promote.py {family} {platform}
```
Review `knowledge/{family}/{platform}/merged/merge_report.md` for scout/enriched promotion counts.

## Provenance Model

Every claim in `merged/claims.json` has a `provenance` field set to a string by source file:

| Claim origin | `provenance` string written |
|---|---|
| `scout/claims.json` | `"scout"` |
| `scout/enriched_claims.json` | `"enriched"` |
| `scout/supplemental_claims.json` | `"supplemental"` |

`promote.py` is additive: all claims from all sources are merged with no cross-source
deduplication or conflict detection. Each claim gets the provenance string for its source file.

> **Planned enhancement**: Structured conflict detection (scout wins over enriched on
> contradictions, hallucination exclusion with conflict log, `merge_conflicts.md` output) is not
> implemented in the current `promote.py`. The current model is additive-only.

## model.yaml source field

`merged/model.yaml` always writes `source: "scout_only"` regardless of whether enriched or
supplemental claims are present. This reflects the architectural intent (scout is the
authoritative ground truth); the `stats.enriched_claims` count records actual enrichment usage.

## merge_conflicts.md

If `merged/merge_conflicts.md` exists from a previous run, `promote.py` **deletes** it. This
file is not created by the current implementation — it is a reset-on-each-run cleanup. A future
implementation may write it when conflict detection is added.

## Output Schema

After promotion, `merged/` must contain these files:

**`merged/model.yaml`** — authoritative metadata:
```yaml
family: {family}
platform: {platform}
product_name: "..."
version: "..."
license: "..."
repo_url: "..."
repo_sha: "{from scout/model.yaml}"
stale_since: null
promoted_at: "{ISO timestamp}"
source: "scout_only"    # always "scout_only" regardless of enriched claims
has_conflicts: false    # always false in current implementation
stats:
  scout_claims: N
  enriched_claims: N
  supplemental_claims: N
  total_claims: N
  class_count: N
  forbidden_count: N
  snippet_count: N
```

**`merged/claims.json`** — flat list of all promoted claims with string provenance:
```json
[
  {
    "text": "...",
    "kind": "api|feature|format|install|...",
    "provenance": "scout"
  },
  {
    "text": "...",
    "kind": "feature",
    "provenance": "enriched"
  }
]
```

Claims from scout preserve all their original fields; `provenance` is added/overwritten.
Claims from enriched and supplemental sources also preserve their original fields.

**`merged/merge_report.md`** — human-readable promotion summary:
```markdown
# Promote Report: {family}/{platform}
Date: {ISO timestamp}
Scout SHA: {sha}
Source: scout-only (standalone pipeline, no FL dependency)

## Statistics
| Metric | Value |
|--------|-------|
| Scout claims | N |
| Enriched claims (S-37) | N |
| Supplemental claims (bridge) | N |
| Total claims | N |
| Classes | N |
| Forbidden claims | N |
| Snippets | N |
```

**`merged/merge_conflicts.md`** — **this file is DELETED** by `promote.py` if it exists.
It is not written. If a previous run left it, it is removed as part of the reset cycle.

## Post-conditions

- `merged/` directory contains: `claims.json`, `api_surface.json`, `api_surface.md`,
  `model.yaml`, `merge_report.md`, and copies of `formats.json`, `class_graph.json`,
  `limitations.md`, `install.md` (if present in scout).
- Every claim in `merged/claims.json` has a `provenance` string field.
- `merged/model.yaml` has `source: "scout_only"` and `has_conflicts: false`.
- `merged/merge_conflicts.md` does NOT exist.

## Error handling

- `scout/claims.json` missing or invalid JSON: abort; run S-34 (repo-scout) first.
- `enriched_claims.json` malformed (not valid JSON): skip enrichment; proceed with scout only.
- `promote.py` script fails (non-zero exit): print the error; do not partially write `merged/`.
- `fl/` directory exists: abort with error — FL layer has been removed; delete `fl/` and re-run.
