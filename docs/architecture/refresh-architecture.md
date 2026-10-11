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

## Family Subtitle Governance

Family-level `_index.md` subtitle fields on docs/kb/reference are **not refreshed by S-84**.
The V-03 CI check (`check_family_display_names.py`) enforces subtitle presence and a 55-character
hard max at commit time. V-03 runs in CI only (not the pre-commit hook) — this is intentional
since family `_index.md` files change rarely. If subtitle refresh is needed in future, extend
S-48 or create a new skill for docs/kb/reference family sync.

References:

- [Refresh a product](../guides/refresh-product.md)
- [Knowledge artifacts](../reference/knowledge-artifacts.md)
- [CLI reference](../reference/cli.md)
