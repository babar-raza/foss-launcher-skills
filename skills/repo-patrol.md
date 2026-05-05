---
name: repo-patrol
id: S-102
description: >
  Scan all Aspose GitHub organisations for new FOSS repositories, diff against the product registry,
  score discovery confidence, and produce a structured patrol report for operator review.
---

# S-102: Repo Patrol -- Scan and Diff

<!-- CONTRACT
purpose: Scan GitHub orgs for new FOSS repos, diff against registry, score confidence, produce patrol report
preconditions:
  - GITHUB_TOKEN env var set (or --token arg)
  - configs/families.yaml exists
  - scripts/pipeline/repo_patrol.py present (TC-P port pending)
postcondition: reports/discovery/patrol_report.json created; reports/discovery/history/ updated
idempotent: yes (--dry-run by default; --apply writes registry)
verified: '2026-04-27 (ported from aspose S-93)'
-->

## Purpose

Scan all Aspose GitHub organisations for new FOSS repositories, diff against the product registry,
score discovery confidence, and produce a structured patrol report for operator review.

## When to use

Run at the start of a session or weekly to check for new FOSS repositories that have been
added to the Aspose GitHub organisations.

## Pre-conditions

- `GITHUB_TOKEN` env var set (or `--token` arg supplied)
- `configs/families.yaml` exists (may be empty -- repo_patrol reads the registry for known products)
- `scripts/pipeline/repo_patrol.py` present (ported from aspose.org)

## Steps

1. Run the patrol scan:
   ```bash
   PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/repo_patrol.py scan
   ```
   - Default: dry-run (produces report only, does not modify registry)
   - With `--apply`: also writes discovered candidates to registry
   - With `--inactive-days N`: custom inactivity threshold (default: 180)
   - With `--force`: re-evaluate previously rejected repos

2. Read the report:
   ```bash
   cat reports/discovery/patrol_report.json
   ```
   Or generate the markdown summary:
   ```bash
   PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/repo_patrol.py report
   cat reports/discovery/combined_report.md
   ```

3. Route findings using /discovery-triage (S-104).

## Output

- `reports/discovery/patrol_report.json` -- structured JSON report
- `reports/discovery/history/YYYY-MM-DD-patrol.json` -- archived snapshot
- `reports/discovery/combined_report.md` -- human-readable summary (via report subcommand)

## Notes

- scan is read-only by default. Never modifies registry without `--apply`.
- Confidence scoring: >=0.70 = candidate, 0.40-0.69 = investigate, <0.40 = unclassifiable.
- Rejected repos stay rejected across rescans (use `--force` to override).
- Direct S-84 dispatch is NOT part of this skill. Route all findings through S-104 then S-98 backlog.

## Related skills

- S-103 `/change-sweep` -- companion sweep for active products
- S-104 `/discovery-triage` -- routes patrol findings to backlog actions
- S-98 `/backlog` -- receives triage items
