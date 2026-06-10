# S-43: Evidence Decide — Content Decision Engine

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}`

## Purpose
Given a mental model, verification reports, and (optionally) an evidence diff, determine the action per page: `create`, `update`, `enhance`, `verify_only`, or `no_change`. Produces a prioritized action manifest that guides content generation and maintenance.

## Pre-conditions
1. `evidence/{family}/{platform}/mental_model.json` must exist (run S-41 first)
2. Verification reports in `evidence/{family}/{platform}/verification/` are optional but recommended
3. Evidence diffs in `evidence/{family}/{platform}/diffs/` are optional

## Automated Script

Run the decision engine:
```
python scripts/decide.py {family} {platform}
```

## Decision Rules (deterministic)

| Condition | Action | Priority |
|-----------|--------|----------|
| Page missing + core page type or tier-1 reference | `create` | 1 |
| Page missing + tier 2/3 | `create` | 2 |
| Page exists + verification FAIL | `update` | 1 |
| Page exists + verification WARN + evidence drift | `update` | 2 |
| Page exists + verification WARN + no drift | `enhance` | 3 |
| Page exists + verification PASS + evidence drift | `verify_only` | 2 |
| Page exists + verification PASS + no drift | `no_change` | 5 |

## Output
- `evidence/{family}/{platform}/decision.json` with per-page actions, priorities, and affected sections

## Post-conditions
- `decision.json` exists with all evaluated pages
- Pages are sorted by priority (1 = highest)
- Summary counts match page list
- For `update` actions, `sections_to_update` identifies affected areas
