# S-94: Change Sweep -- Batch SHA Comparison

<!-- CONTRACT
purpose: Batch SHA comparison across all active launched products; detect upstream changes with impact classification
preconditions:
  - data/products.json exists with active launched products
  - Clone cache populated (runs/.clone_cache/) or network available to fetch
postcondition: reports/discovery/sweep_report.json created; reports/discovery/history/ updated
idempotent: yes (read-only; only fetches upstream clones)
verified: false
-->

## Purpose

Run a batch SHA comparison across all active launched products to detect upstream repository changes with HIGH/MEDIUM/LOW impact classification and produce a structured sweep report.

## When to use

Run weekly or before a knowledge refresh session to identify which products have upstream
changes that require documentation updates.

## Steps

1. Run the sweep:
   ```bash
   PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/repo_patrol.py sweep
   ```
   This fetches upstream for all active launched products and compares SHAs.

2. Read the report:
   ```bash
   cat reports/discovery/sweep_report.json
   ```
   Or generate the markdown summary:
   ```bash
   PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/repo_patrol.py report
   cat reports/discovery/combined_report.md
   ```

3. Route findings using /discovery-triage (S-95).

## Output

- reports/discovery/sweep_report.json -- structured JSON with impact classification
- reports/discovery/history/YYYY-MM-DD-sweep.json -- archived snapshot
- Impact levels: HIGH (source files changed), MEDIUM (undetermined), LOW (non-source only)

## Notes

- Sweep is read-only. It does NOT set stale_since -- that is S-12 responsibility.
- S-95 routes HIGH/MEDIUM findings to backlog items. LOW findings are logged only.
- This skill does NOT invoke S-84 (refresh). Route findings to S-95 first.
