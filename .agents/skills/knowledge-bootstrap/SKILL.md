---
name: knowledge-bootstrap
description: >
  Shared pre-condition gate for knowledge state
args: "{family} {platform}"
---

# Knowledge Bootstrap

Current chain:

```text
repo-scout -> knowledge-enrich -> truth-merge -> truth-index
```

Do not use `truth-sync`. If knowledge is stale, refresh with the current pipeline.

## Post-Scout Validation Gate

After running repo-scout, validate the extraction output before proceeding:

```bash
source .venv/Scripts/activate  # Windows
python -m extraction.validate_scout_output knowledge/{family}/{platform}/scout/model.yaml {repo_path} {platform}
```

Act on the verdict:
- `VERDICT: OK` — continue to enrich + merge
- `VERDICT: EXTRACTION_FAILURE` — **HARD STOP**. Scout produced 0 classes but the repo contains class-bearing source files. The extraction failed silently. Diagnose before proceeding. Do NOT propagate empty knowledge.
- `VERDICT: PRE_ALPHA` — the repo genuinely contains no class-bearing files. Emit `STOP:pre_alpha` and halt.

## Maturity Tier

After successful extraction, classify the product maturity tier based on scout stats:

| Tier | class_count | claim_count | Justified launch scope |
|------|-------------|-------------|----------------------|
| **full** | >= 50 | >= 500 | All 5 subdomains |
| **reduced** | 10-49 | >= 50 | products + 1 blog + kb FAQ + reference (no docs except install) |
| **minimal** | 1-9 | >= 10 | products page only + README blog intro |
| **skip** | 0 | < 10 | No launch — defer to future |

Include the tier in the output status: `BOOTSTRAPPED (tier: reduced)` or `READY (tier: full)`.
The `launch-product` skill uses this tier to determine which stages to execute.

## Output Statuses

- READY — knowledge is current, enrichment meets thresholds, safe for content generation
- BOOTSTRAPPED — knowledge was freshly built from source; completeness gate passed
- REFRESHED — knowledge was rebuilt after detecting a stale SHA; completeness gate passed
- STOP:incomplete — enrichment or snippet coverage is below threshold; run
  `python scripts/pipeline/enrich.py {family} {platform} --min-coverage 0.25`
  then `python scripts/pipeline/promote.py {family} {platform}` before generating content
- STOP:pre_alpha — repo contains no class-bearing source files; defer launch
- STOP:extraction_failure — scout produced 0 classes from a non-empty repo; diagnose
- WARN:low_enrichment — enriched_claims / class_count < 0.25; content generation
  may produce WEAK/UNSUPPORTED semantic audit results
