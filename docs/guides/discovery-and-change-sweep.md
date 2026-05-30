# Discovery And Change Sweep

Status: Current
Audience: Operator
Canonical reference: `docs/reference/cli.md#repo-patrol`
Last code-backed audit: 2026-05-30

Goal: find new FOSS repositories and detect upstream source changes for active products.

## When To Use

- You need to discover candidate repositories.
- You need to sweep active launched products for source SHA changes.
- You need a combined discovery report for triage.

## Steps

1. Run repo patrol scan when looking for new or changed repositories.
2. Run sweep when checking active products for upstream changes.
3. Generate a report for operator triage.
4. Route actionable findings to product refresh work.

## Verification

- Discovery reports are written under the reports area.
- Product registry changes, if any, are intentional and reviewed.
- Refresh work uses [Refresh a product](refresh-product.md), not ad hoc content edits.

## References

- [Repo patrol CLI](../reference/cli.md#repo-patrol)
- [Configuration](../reference/config.md)
- [File contracts](../reference/file-contracts.md#reports)
