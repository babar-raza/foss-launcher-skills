# System Purpose And Concepts

Status: Current
Audience: User, Operator, Contributor
Canonical reference: `docs/reference/file-contracts.md`
Last code-backed audit: 2026-05-30

This repository powers a governed documentation generation and maintenance pipeline for Aspose FOSS products. Source repositories are discovered or cloned, code is extracted into knowledge artifacts, generated content is validated against that knowledge, and governance gates prevent ungrounded or misplaced changes.

The code-derived audit identifies these primary components:

| Component | Responsibility | Reference |
|---|---|---|
| Clone cache | Resolve and update local FOSS clones | [Configuration](../reference/config.md#clone-cache) |
| Knowledge extraction | Extract APIs, formats, snippets, limitations, and claims | [Knowledge artifacts](../reference/knowledge-artifacts.md) |
| Knowledge promotion | Promote `scout/` artifacts into `merged/` contracts | [Knowledge artifacts](../reference/knowledge-artifacts.md) |
| Site planning | Build deterministic product plans | [CLI reference](../reference/cli.md#site-planner) |
| Content generation | Create or update product, docs, KB, blog, and reference pages | [File contracts](../reference/file-contracts.md#content-trees) |
| Evidence and audit | Attach and validate evidence frontmatter | [Content contracts](../reference/content-contracts.md) |
| Governance gates | Enforce path, content, grade, and CI rules | [Governance gates](../reference/governance-gates.md) |
| Metrics | Capture professionalize calls and aggregate run rows | [Metrics](../reference/metrics.md) |

## Core Ideas

- Code is the source of truth for system behavior.
- FOSS source clones under `runs/.clone_cache/` are the source for API truth.
- Knowledge artifacts under `knowledge/{family}/{platform}/` ground content generation.
- Content under `content/` is output and must be validated against knowledge.
- Long reference material belongs in `docs/reference/`; guides link to it.

## Where Content Lives

See [file contracts](../reference/file-contracts.md#content-trees) for the canonical content path table.
