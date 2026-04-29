---
name: repo-patrol
id: S-93
description: >
  Scan all 26 Aspose GitHub organisations for new FOSS repositories, diff against the product registry, score discovery confidence, and produce a structured patrol report for operator review.
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# S-93: Repo Patrol -- Scan and Diff

<!-- CONTRACT
purpose: Scan GitHub orgs for new FOSS repos, diff against registry, score confidence, produce patrol report
preconditions:
  - GITHUB_TOKEN env var set (or --token arg)
  - data/products.json exists (may be empty)
postcondition: reports/discovery/patrol_report.json created; reports/discovery/history/ updated
idempotent: yes (--dry-run by default; --apply writes registry)
verified: '2026-04-26'
-->

## Purpose

Scan all 26 Aspose GitHub organisations for new FOSS repositories, diff against the product registry, score discovery confidence, and produce a structured patrol report for operator review.

## When to use

Run at the start of a session or weekly to check for new FOSS repositories that have been
added to the 26 Aspose GitHub organisations.

## Steps

1. Run the patrol scan:
   ```bash
   PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/diagnostics/repo_patrol.py scan
   ```
   - Default: dry-run (produces report only, does not modify data/products.json)
   - With --apply: also writes discovered candidates to data/products.json
   - With --inactive-days N: custom inactivity threshold (default: 180)
   - With --force: re-evaluate previously rejected repos

2. Read the report:
   ```bash
   cat reports/discovery/patrol_report.json
   ```
   Or generate the markdown summary:
   ```bash
   PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/diagnostics/repo_patrol.py report
   cat reports/discovery/combined_report.md
   ```

3. Route findings using /discovery-triage (S-95).

## Output

- reports/discovery/patrol_report.json -- structured JSON report
- reports/discovery/history/YYYY-MM-DD-patrol.json -- archived snapshot
- reports/discovery/combined_report.md -- human-readable summary (via report subcommand)

## Notes

- scan is read-only by default. It never modifies data/products.json without --apply.
- Confidence scoring: >=0.70 = candidate, 0.40-0.69 = investigate, <0.40 = unclassifiable.
- Rejected repos stay rejected across rescans (use --force to override).
- Direct S-84 dispatch is NOT part of this skill. Route all findings through S-95 then S-88 backlog.
