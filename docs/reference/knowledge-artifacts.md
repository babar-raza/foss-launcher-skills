# Knowledge Artifacts Reference

Status: Current
Audience: Operator, Contributor, Agent
Canonical reference: this page
Last code-backed audit: 2026-05-30

The knowledge layer is derived from source code and grounds generated content.

## Layers

| Layer | Path | Source | Purpose |
|---|---|---|---|
| Scout | `knowledge/{family}/{platform}/scout/` | Tree-sitter extraction from clone cache | Raw deterministic API, format, snippet, limitation, and claim artifacts. |
| Merged | `knowledge/{family}/{platform}/merged/` | Promotion from scout plus optional grounded enrichment | Canonical input for content generation and validation. |

## Core Files

| File | Contract |
|---|---|
| `model.yaml` | Product knowledge metadata including source revision and freshness fields. |
| `claims.json` | Semantic claims used for content grounding. |
| `api_surface.json` | Structured API surface extracted from source. |
| `api_surface.md` | Human-readable generated API surface. |
| `formats.json` | Format support facts. |
| `limitations.md` | Known limitations that override positive claims at same level. |
| `.pipeline_state.json` | Step completion manifest. |

## Workflow

1. Resolve clone cache path.
2. Run scout.
3. Promote scout artifacts into merged artifacts.
4. Generate or validate content against merged artifacts.

See [CLI reference](cli.md#scout) and [file contracts](file-contracts.md#knowledge-artifacts).
