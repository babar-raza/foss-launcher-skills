# commands/ — Domain Reference

Quick reference for the 9 domain directories under `scripts/pipeline/commands/`.

## Domain Table

| Domain | Scripts | Description |
|--------|---------|-------------|
| `content/` | 17 | Content auditing, evaluation, validation, batch reference, remediation, backfills |
| `diagnostics/` | 7 | Smoke tests, truth audits, coverage audits, provenance checks, repo patrol |
| `governance/` | 11 | Path guard, grade checks, change guard, structural lock, skill context, overrides |
| `healing/` | 5 | Backtrack controller, dependency resolver, evidence attachment, page retirement |
| `kilocode/` | 4 | Kilocode gate, postcheck, skill chain, skill validator |
| `knowledge/` | 12 | Scout, enrich, promote, index, embed, refresh, coverage, stale detection |
| `launch/` | 8 | Site planner, launch gate, preflight, readiness, plan check, write classifier |
| `migration/` | 14 | One-shot backfills, field fixes, provenance migration, plugin structure |
| `ops/` | 18 | Session management, LLM routing, skill runs, sync, link validation, registry |

**Total**: 96 entry-point scripts across 9 domains.

## Domain Assignment Rules

When adding a new script, choose the domain by primary responsibility:

| If the script... | Domain |
|------------------|--------|
| Audits, evaluates, or validates content files | `content/` |
| Diagnoses system health or produces diagnostic reports | `diagnostics/` |
| Enforces write boundaries, grade integrity, or access control | `governance/` |
| Repairs, reverts, or resolves dependency issues | `healing/` |
| Interfaces with Kilocode provider sync or validation | `kilocode/` |
| Extracts, enriches, or manages knowledge artifacts | `knowledge/` |
| Orchestrates product launches, readiness gates, or site planning | `launch/` |
| Performs one-shot data backfills or schema migrations | `migration/` |
| Manages sessions, syncs providers, routes LLM calls, or handles operational tasks | `ops/` |

If a script spans two domains, assign it to the domain of its **primary consumer**.
If still ambiguous, prefer `ops/`.

## Adding Scripts

See [PIPELINE.md](../PIPELINE.md) for the full new-script protocol (header, registration,
tests). CI enforces placement via `check_new_script_placement.py`.

## Shared Libraries

Pure-library modules live in `lib/`, not in any domain directory. A module qualifies
for `lib/` when 3+ scripts across different domains import it. See PIPELINE.md
§Shared Module Rules for details.
