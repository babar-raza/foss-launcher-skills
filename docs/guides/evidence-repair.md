# Evidence Repair

Status: Current
Audience: Operator, Agent
Canonical reference: `docs/reference/content-contracts.md`
Last code-backed audit: 2026-05-30

Goal: repair missing or stale evidence frontmatter without inventing claims.

## Prerequisites

- Merged knowledge exists for the target product.
- Content audit findings identify evidence issues.
- Proposed claims and API references can be traced to knowledge artifacts.

## Steps

1. Inspect the audit finding and target file.
2. Confirm product family/platform from the content path.
3. Run evidence attachment for the file or product.
4. Re-run content audit.
5. Re-run content evaluation if the page is part of a broader quality workflow.

## Verification

- Evidence block includes current knowledge identifiers.
- API refs and claim IDs are grounded in merged knowledge.
- Audit passes.

## References

- [Content contracts](../reference/content-contracts.md#evidence)
- [CLI reference](../reference/cli.md)
- [Knowledge artifacts](../reference/knowledge-artifacts.md)
