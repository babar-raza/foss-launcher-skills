# Aspose.org Documentation

Status: Current

Audience: User, Operator, Contributor, Agent

This documentation covers the governed content generation and maintenance system in this repository. Code is the source of truth. The audit-backed reference pages link each documented behavior to the code surfaces identified in `docs/_audit/system_audit.md`.

## Start By Persona

| Persona | Start here | You likely need |
|---|---|---|
| User | [System overview](overview/system-purpose.md) | What the repo produces and where generated content lives |
| Operator | [Operator quickstart](getting-started/operator-quickstart.md) | Launch, refresh, discovery, audit, recovery |
| Contributor | [Contributor quickstart](getting-started/contributor-quickstart.md) | Testing, repo structure, Python placement, architecture |
| Agent | [Agent session start](getting-started/agent-session-start.md) | Read order, root hygiene, preflight, verification |

## Start By Scenario

| Scenario | Guide |
|---|---|
| Launch a new product | [Launch a product](guides/launch-product.md) |
| Refresh existing content after source changes | [Refresh a product](guides/refresh-product.md) |
| Discover repos or sweep upstream changes | [Discovery and change sweep](guides/discovery-and-change-sweep.md) |
| Audit generated content | [Content audit and evaluation](guides/content-audit-and-evaluation.md) |
| Repair evidence or claims | [Evidence repair](guides/evidence-repair.md) |
| Heal content after quality failures | [Heal content](guides/heal-content.md) |
| Integrate with git safely | [Git integration](guides/git-integration.md) |
| Recover from hard stops | [Hard-stop recovery](operations/hard-stop-recovery.md) |

## Canonical References

Guides should link here instead of repeating tables.

| Reference | Owns |
|---|---|
| [CLI reference](reference/cli.md) | Commands, flags, entry points |
| [Configuration reference](reference/config.md) | Env vars, config files, defaults |
| [File contracts](reference/file-contracts.md) | Inputs, outputs, folder contracts |
| [Knowledge artifacts](reference/knowledge-artifacts.md) | Scout and merged knowledge files |
| [Content contracts](reference/content-contracts.md) | Content paths, evidence, provenance |
| [Governance gates](reference/governance-gates.md) | Path guard, preflight, CI, hooks |
| [Metrics](reference/metrics.md) | Metrics schema, event ledger, run rows |
| [Skills](reference/skills.md) | Skill catalog and routing contracts |
| [Pipeline registry](reference/pipeline-registry.md) | Registered command inventory |

## Architecture And Development

- [System architecture](architecture/system-architecture.md)
- [Knowledge pipeline architecture](architecture/knowledge-pipeline.md)
- [Governance enforcement architecture](architecture/governance-enforcement.md)
- [Refresh architecture](architecture/refresh-architecture.md)
- [Development and contributing](development/contributing.md)
- [Testing and CI](development/testing.md)
- [Python placement](development/python-placement.md)
- [Reporting](development/reporting.md)

## Operations

- [Runbook](operations/runbook.md)
- [Troubleshooting](operations/troubleshooting.md)
- [Hard-stop recovery](operations/hard-stop-recovery.md)
- [Telemetry and metrics](operations/telemetry-and-metrics.md)
- [Hook installation](operations/hook-installation.md)

## Root Hygiene

The `docs/` root is reserved for this `README.md` plus category and meta folders. Do not add new root-level markdown files under `docs/`. Place new docs in `overview/`, `getting-started/`, `guides/`, `reference/`, `architecture/`, `operations/`, or `development/`.
