# S-LG-03: llms-coverage — Audit Coverage Gap

## Description

Walks content/ for all eligible English .md pages, compares against llms-output/ .txt files,
and reports coverage percentage per domain. Gate: all domains >= 95% coverage.

## Contract

**Backing script**: `scripts/generator/audit_coverage.py`
**Input**: `content/` (source pages) + `llms-output/` (generated outputs)
**Output**: `reports/agent-consumption/coverage-report.json` (local only)

## Steps

1. Ensure generator outputs are current (run `/llms-generate` if stale):

2. Run coverage audit:
   ```bash
   .venv/Scripts/python scripts/generator/audit_coverage.py \
     --content content \
     --llms-output llms-output \
     --output reports/agent-consumption/coverage-report.json
   ```

3. Check per-domain coverage:
   ```bash
   .venv/Scripts/python -c "
   import json
   d = json.load(open('reports/agent-consumption/coverage-report.json'))
   for k, v in d.items():
       pct = v.get('coverage_pct', 0)
       status = 'PASS' if pct >= 95 else 'FAIL'
       print(f'{k}: {pct:.1f}% [{status}]')
   "
   ```

## Gate

All 5 domains >= 95%. If any fail, inspect `missing_pages` list in the report.
Missing pages indicate either:
- Generator bug (source not processed)
- Draft pages (excluded by design)
- New pages not yet regenerated (run `/llms-generate`)

## Committed Baseline

Coverage baseline (without missing_pages list) is committed to:
`scripts/generator/baselines/coverage-baseline.json`

Use this for regression comparison after regeneration.

## Related Skills

- `/llms-generate` — regenerate outputs to fix coverage gaps
- `/llms-fidelity` — verify content quality (not just presence)
- `/llms-stale` — detect hash-level staleness
