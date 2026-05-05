---
name: change-sweep
id: S-103
description: >
  Batch SHA comparison across all active launched products to detect upstream repository changes
  with HIGH/MEDIUM/LOW impact classification; produces structured sweep report.
---

# S-103: Change Sweep -- Batch SHA Comparison

<!-- CONTRACT
purpose: Batch SHA comparison across all active launched products; detect upstream changes with impact classification
preconditions:
  - Registry (configs/families.yaml or products JSON) exists with active launched products
  - Clone cache populated or network available to fetch
  - scripts/pipeline/repo_patrol.py present (TC-P port pending)
postcondition: reports/discovery/sweep_report.json created; reports/discovery/history/ updated
idempotent: yes (read-only; only fetches upstream clones)
verified: '2026-04-27 (ported from aspose S-94)'
-->

## Purpose

Run a batch SHA comparison across all active launched products to detect upstream repository changes
with HIGH/MEDIUM/LOW impact classification and produce a structured sweep report.

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

3. Route findings using /discovery-triage (S-104).

## Output

- `reports/discovery/sweep_report.json` -- structured JSON with impact classification
- `reports/discovery/history/YYYY-MM-DD-sweep.json` -- archived snapshot
- Impact levels: HIGH (source files changed), MEDIUM (undetermined), LOW (non-source only)

## Notes

- Sweep is read-only. It does NOT set stale_since -- that is S-12 responsibility.
- S-104 routes HIGH/MEDIUM findings to backlog items. LOW findings are logged only.
- This skill does NOT invoke S-84 (refresh). Route findings to S-104 first.

## Related skills

- S-102 `/repo-patrol` -- companion scan for new repos
- S-104 `/discovery-triage` -- routes sweep findings to backlog actions
- S-12 `/knowledge-diff` -- per-product staleness detection (downstream of sweep)
