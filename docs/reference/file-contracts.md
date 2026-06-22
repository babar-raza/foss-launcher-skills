# File And Artifact Contracts

Status: Current
Audience: Operator, Contributor, Agent
Canonical reference: this page
Last code-backed audit: 2026-05-30

This page owns path and artifact contracts. Guides must link here instead of repeating path tables.

## Content Trees

| Site | Content path | Contract |
|---|---|---|
| `www.aspose.org` | `content/www.aspose.org/` | Marketing homepage content. |
| `products.aspose.org` | `content/products.aspose.org/en/{family}/` and `content/products.aspose.org/en/{family}/{platform}/` | Family and platform product pages. |
| `docs.aspose.org` | `content/docs.aspose.org/en/{family}/{platform}/` | Technical documentation. |
| `kb.aspose.org` | `content/kb.aspose.org/en/{family}/{platform}/` | How-to and FAQ content. |
| `reference.aspose.org` | `content/reference.aspose.org/en/{family}/{platform}/` | API reference pages. |
| `blog.aspose.org` | `content/blog.aspose.org/{family}/{platform}/` | Blog post bundles. |
| `websites.aspose.org` | `content/websites.aspose.org/en/` | Websites hub content. |

## Knowledge Artifacts

| Path | Contract |
|---|---|
| `knowledge/{family}/{platform}/scout/` | Deterministic extraction output from source code. |
| `knowledge/{family}/{platform}/merged/` | Promoted knowledge consumed by generators/evaluators. |
| `knowledge/{family}/{platform}/.pipeline_state.json` | Step completion state for knowledge pipeline stages. |

See [knowledge artifacts](knowledge-artifacts.md).

## Clone Cache

| Path | Contract |
|---|---|
| `runs/.clone_cache/` | Canonical local cache for FOSS source clones. |
| `runs/.clone_cache/aspose_{family}_{platform}` | Expected clone directory for a product. |

The clone cache is managed by `scripts/pipeline/core/clone_cache.py`.

## Reports

| Path | Contract |
|---|---|
| `reports/session-invocations/` | Session invocation JSONL logs. |
| `reports/metrics/events/` | Metrics event JSONL ledgers. |
| `reports/content-check/` | Content check pass markers used by preflight. |
| `reports/discovery/` | Discovery and sweep reports. |

`reports/` is local evidence/output space and should not be treated as canonical documentation.

## Docs Tree

| Path | Contract |
|---|---|
| `docs/README.md` | Docs home and navigation. |
| `docs/overview/` | Purpose and concepts. |
| `docs/getting-started/` | Persona-specific quickstarts. |
| `docs/guides/` | Scenario procedures. |
| `docs/reference/` | Canonical exhaustive reference. |
| `docs/architecture/` | Design and decisions. |
| `docs/operations/` | Runbooks and recovery. |
| `docs/development/` | Contributor documentation. |
| `docs/_audit/` | Audit and planning artifacts. |
| `docs/_archive/` | Historical/superseded docs. |
| `docs/content-system/` | Hugo content system reference: page resolution, themes, localization, content types. |

The `docs/` root may contain only `README.md` plus directories. Any other root-level file is a root orphan.

## Python Files

New Python files must be placed in the subsystem that owns the behavior. See [Python placement](../development/python-placement.md).

## Write Paths

Write path enforcement is owned by [governance gates](governance-gates.md). Use preflight before writes.
