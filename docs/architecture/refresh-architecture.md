# Refresh Architecture

Status: Current
Audience: Contributor, Operator
Canonical reference: `docs/guides/refresh-product.md`
Last code-backed audit: 2026-05-30

Refresh work updates generated content after source or knowledge changes.

## Flow

1. Update source clone.
2. Re-extract knowledge.
3. Promote merged knowledge.
4. Compute planning/update decisions.
5. Regenerate affected content.
6. Reattach evidence and revalidate.

References:

- [Refresh a product](../guides/refresh-product.md)
- [Knowledge artifacts](../reference/knowledge-artifacts.md)
- [CLI reference](../reference/cli.md)
