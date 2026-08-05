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
  - GH_TOKEN env var set with a CLASSIC PAT (or --token arg). GITHUB_TOKEN holds a
    fine-grained PAT that every aspose-*-foss org rejects — see Credentials below
  - data/products.json exists (may be empty)
postcondition: reports/discovery/patrol_report.json created and history/ updated — UNLESS the scan reached no org, in which case nothing is written and the last good report is preserved (exit 2)
idempotent: yes (--dry-run by default; --apply writes registry)
verified: '2026-08-05'
-->

## Purpose

Scan all 25 Aspose GitHub organisations for new FOSS repositories, diff against the product registry, score discovery confidence, and produce a structured patrol report for operator review.

## When to use

Run at the start of a session or weekly to check for new FOSS repositories that have been
added to the 25 Aspose GitHub organisations.

## Credentials (ST-058 — read this before debugging an apparent "hang")

Use **`GH_TOKEN`** (a classic `ghp_` PAT). The scan resolves its credential in this order:
`--token` → `GH_TOKEN` → `GITHUB_TOKEN`.

`GITHUB_TOKEN` holds a **fine-grained** PAT, and every `aspose-*-foss` org rejects
fine-grained PATs whose lifetime exceeds 366 days. GitHub signals that rejection with
HTTP **403** — the same status it uses for rate limiting. Verified live 2026-08-05:
`GITHUB_TOKEN` → 403 (with 4993 requests still remaining), `GH_TOKEN` → 200.

The scanner distinguishes the two and **fails fast in ~2 seconds** on an authorization
denial instead of sleeping until `X-RateLimit-Reset`. If you see
`token rejected by GitHub (authorization/org policy...)`, switch to `GH_TOKEN`.

## Steps

1. Run the patrol scan:
   ```bash
   PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/diagnostics/repo_patrol.py scan
   ```
   - Default: dry-run (produces report only, does not modify data/products.json)
   - With --apply: also writes discovered candidates to data/products.json
   - With --inactive-days N: custom inactivity threshold (default: 180)
   - With --force: re-evaluate previously rejected repos
   - With --no-auth: explicit unauthenticated mode (public API, 60 req/hr)
   - With --allow-degraded: exit 0 even when some orgs were unreachable
   - With --max-rate-wait N: cap a single rate-limit backoff (default: 300s)

   **Check the exit code. Never read an empty finding list as "nothing new exists"
   without first confirming `scan_health.status == "ok"`:**

   | Exit | `scan_health.status` | Meaning |
   |------|----------------------|---------|
   | 0 | `ok` | Every org reached; findings are complete |
   | 1 | `degraded` | Some orgs unreachable; report written but **incomplete** |
   | 2 | `failed` | No org reached, or no credential. **Nothing written** — the previous report is preserved on purpose |

   On exit 2 the last good `patrol_report.json` is deliberately left untouched, so it keeps
   ageing and keeps triggering the session-start discovery advisory. Fix the credential and
   re-run; do not treat the preserved report as current.

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
