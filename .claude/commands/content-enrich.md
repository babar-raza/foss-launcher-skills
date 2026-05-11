# S-98: Content Enrich -- Post-Launch Cross-Subdomain Enrichment

<!-- CONTRACT
purpose: Audit cross-subdomain content coverage, generate enrichment candidates with denominator invariant, and produce governed execution manifests for downstream skills.
preconditions:
  - knowledge/{family}/{platform}/merged/model.yaml exists (knowledge bootstrapped)
  - data/site_plans/{family}/{platform}/site_plan.yaml exists (site planned)
  - Clone cache populated at runs/.clone_cache/{family}.{platform}/
postcondition: reports/enrichment/{family}/{platform}/ populated with coverage matrix, candidates, and optionally execution manifest
idempotent: yes (audit and plan modes are read-only; execute mode is additive via manifest)
verified: '2026-05-11'
-->

## Purpose

Audit content coverage across all five subdomains (products, docs, kb, blog, reference) for a launched product, identify enrichment gaps, generate scored candidates with denominator invariant enforcement, and produce governed execution manifests for downstream skill invocation.

## When to use

After a product is launched and has knowledge bootstrapped + site planned:
- **audit**: Get a coverage matrix showing where content exists and where gaps are
- **plan / dry-run**: Generate scored candidates, classify actions, enforce denominator invariant
- **execute**: Create handoff manifests for downstream skills (S-56, S-57, S-58, S-20)

## Pre-conditions

- S-54 `/knowledge-bootstrap` must have run (knowledge artifacts exist)
- S-47 `/site-plan` must have run (site plan exists)
- Clone cache must be populated at `runs/.clone_cache/{family}.{platform}/`

## Modes

### audit (read-only)
Builds a coverage matrix across all subdomains. No candidates generated, no writes to content/.

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/enrichment/content_enrich.py {family} {platform} --mode audit
```

### plan / dry-run (read-only)
Generates candidates from coverage gaps, applies scoring, classifies actions, and enforces the denominator invariant. Produces candidate list, decisions, and handoff manifest with `dry_run: true`. No writes to content/.

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/enrichment/content_enrich.py {family} {platform} --mode dry-run
```

### execute (manifest-based, no direct content writes)
Creates a governed execution manifest for downstream skill invocation. Requires `--allow-local-content-write` flag. Does NOT directly write content pages -- operators invoke the listed skills.

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/enrichment/content_enrich.py {family} {platform} --mode execute --allow-local-content-write
```

## Denominator Invariant

Every run enforces:
```
total_candidates = generate_now + update_existing + deferred_to_backlog + rejected_with_reason + blocked_with_reason
```
Delta must be 0. If the invariant fails, execution halts.

## Blog Quality Gate

Blog candidates with medium scores (between defer and generate thresholds) are automatically deferred to backlog rather than generated. Only high-confidence blog candidates proceed.

## Backlog / Taskcard Handoff

Deferred and rejected candidates are routed to `backlog/BACKLOG.md` with structured entries.
**Caveat**: `backlog/` is gitignored -- entries are local-only and do not persist across clones.

## Three-Tier Content Model

| Tier | Name | Content Types |
|------|------|---------------|
| A | Mandatory | products landing page, reference API docs |
| B | Threshold-optional | docs guides, KB how-tos |
| C | Enrichment-optional | blog posts, advanced tutorials |

## Architecture Decisions

- **Manifest-based execution**: S-98 does not invoke downstream skills directly. It produces a handoff manifest (handoff-manifest.json) that maps candidates to target skills (S-56, S-57, S-58, S-20). Operators invoke those skills manually. This avoids coupling and preserves operator control.
- **Local-only execute mode**: Execute mode requires `--allow-local-content-write` and produces manifests locally. No remote mutations.
- **Denominator invariant**: Every candidate must be accounted for in exactly one disposition bucket. This is enforced programmatically and tested.
- **Metrics integration deferred**: The repo has metrics infrastructure (metrics_submitter.py, check_metrics_*) but S-98 MVP defers integration to a follow-up sprint. Enrichment JSON outputs are structured for future metrics ingestion.

## Outputs

All outputs written to `reports/enrichment/{family}/{platform}/`:
- `coverage-matrix.json` / `coverage-matrix.md` -- subdomain coverage by cluster
- `candidate-list.json` -- all candidates with scores and dispositions
- `enrichment-decisions.json` -- candidates grouped by disposition
- `handoff-manifest.json` -- manifest for downstream skill invocation
- `denominator-check.json` -- invariant validation result
- `execution-log.json` -- execute mode log (execute mode only)
- `enrichment-report.md` -- human-readable report (execute mode only)

## Safety Constraints

- No direct content page writes by S-98
- No publish, deploy, push, or PR
- Execute mode requires explicit `--allow-local-content-write` flag
- Conservative pilot limit: 2 items per execute run
- Manifest pattern delegates to S-56/S-57/S-58/S-20

## Evidence Requirements

- Denominator check must pass (delta = 0)
- Coverage matrix must be generated before candidates
- All deferred/rejected candidates must have reasons

## Pilot Commands

```bash
# font/python audit
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/enrichment/content_enrich.py font python --mode audit

# font/python full dry-run
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/enrichment/content_enrich.py font python --mode dry-run

# slides/python audit (second repo validation)
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/enrichment/content_enrich.py slides python --mode audit
```
