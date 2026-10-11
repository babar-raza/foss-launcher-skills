# Launch A Product

Status: Current
Audience: Operator, Agent
Canonical reference: `docs/reference/cli.md`
Last code-backed audit: 2026-05-30

Goal: launch a product by building grounded knowledge, planning content, generating pages, attaching evidence, and validating outputs.

## Prerequisites

- Product registry entry exists in `data/products.json`.
- Clone cache can resolve the product source; see [configuration](../reference/config.md#clone-cache).
- Knowledge artifacts are fresh; see [knowledge artifacts](../reference/knowledge-artifacts.md).

## Steps

1. Resolve or refresh the clone cache.
2. Run knowledge extraction with scout.
3. Promote scout artifacts into merged knowledge.
4. Generate or refresh the site plan.
5. Generate content through the appropriate product/content workflow.
6. Attach evidence.
7. Run content audit and content evaluation.
8. Verify git status contains only intended files.

## Verification

- `knowledge/{family}/{platform}/merged/` exists and is current.
- Generated content is under the allowed `content/` tree.
- Content audit and evaluator checks pass.
- Evidence frontmatter exists on generated content pages.

## References

- [CLI reference](../reference/cli.md)
- [File contracts](../reference/file-contracts.md)
- [Knowledge artifacts](../reference/knowledge-artifacts.md)
- [Content contracts](../reference/content-contracts.md)
- [Governance gates](../reference/governance-gates.md)
