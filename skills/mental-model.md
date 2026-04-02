---
name: mental-model
id: S-45
description: >
  Build a structured mental model from the PEF showing capability tiers,
  page coverage, gap analysis, and launch readiness.
args: "{family} {platform} | all"
---

# S-45: Mental Model — Build Product Mental Model

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}` or `all`

## Purpose
Derive a structured summary from the PEF that content operators and agents use to understand what content to create, what gaps exist, and what capabilities exist at each tier. The mental model bridges raw evidence and content operations.

## Pre-conditions
1. `evidence/{family}/{platform}/pef.json` must exist (run S-40 first)

## Automated Script

Run the mental model builder:
```
python scripts/mental_model.py {family} {platform}   # Single product
python scripts/mental_model.py all                     # All products with evidence
```
The script:
- Classifies API classes into capability tiers (tier 1: 5+ methods, tier 2: 2-4, tier 3: 0-1)
- Builds format import/export matrix
- Scans content directories for existing pages
- Identifies gaps: uncovered tier-1 classes, missing page types, undocumented formats
- Assesses readiness: launch_ready, needs_work, or blocked

## Output
- `evidence/{family}/{platform}/mental_model.json`

## Key Sections in Output
- `capability_tiers` — classes sorted by evidence density and method count
- `page_coverage` — which pages exist per site type (docs, blog, kb, reference)
- `gap_analysis` — what is missing or underserved
- `readiness` — overall assessment with blockers and warnings

## Post-conditions
- `mental_model.json` exists and passes schema validation
- Readiness assessment is consistent with api_confidence and gap analysis
