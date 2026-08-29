# S-117: LLMs Coverage -- Audit Coverage Gap

**Arguments**: $ARGUMENTS (all optional)

## Purpose
Confirm every eligible content page has a corresponding llms-output/ text
file, and report per-site coverage percentage.

## Pre-conditions
Run `/llms-generate` first (or accept that coverage will read as low/zero).

## Steps

1. Run the coverage audit:
   ```bash
   .venv/bin/python scripts/llms_coverage.py --output llms-output --report reports/llms-coverage.json
   ```

2. Enforce a gate (exit 1 if any site falls below threshold):
   ```bash
   .venv/bin/python scripts/llms_coverage.py --output llms-output --gate 95
   ```

## Gate
Default recommendation: 95% per site. If any site falls below, inspect that
site's `missing_pages` list in the JSON report -- missing pages usually mean
either a generator bug, or new content not yet regenerated (`/llms-generate`).

## Output
`reports/llms-coverage.json` (or wherever `--report` points): per-site
`{eligible_pages, covered_pages, coverage_pct, missing_pages}`.

## Related Skills
- `/llms-generate` -- regenerate outputs to close a coverage gap
- `/llms-fidelity` -- checks content *quality*, not just presence
