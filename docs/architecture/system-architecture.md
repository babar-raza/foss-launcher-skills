# System Architecture

Status: Current
Audience: Contributor, Operator
Canonical reference: `docs/_audit/system_audit.md`
Last code-backed audit: 2026-05-30

## Data Flow

1. `data/products.json` identifies active products and clone URLs.
2. `scripts/pipeline/core/clone_cache.py` resolves local source clones.
3. `scripts/pipeline/commands/knowledge/scout.py` extracts source facts.
4. `scripts/pipeline/commands/knowledge/promote.py` promotes scout output to merged knowledge.
5. Planning and generation commands create or update content.
6. Evidence and audit commands validate content against merged knowledge.
7. Governance hooks and CI enforce quality and placement.

## Components

See [system audit](../_audit/system_audit.md#component-map) for code evidence and [reference docs](../reference/file-contracts.md) for contracts.
