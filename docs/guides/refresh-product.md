# Refresh A Product

Status: Current
Audience: Operator, Agent
Canonical reference: `docs/reference/cli.md`
Last code-backed audit: 2026-05-30

Goal: update existing generated content after upstream source changes.

## Prerequisites

- Product source clone exists or can be created.
- Current product is listed in `data/products.json`.
- Existing content is not manually protected unless the workflow explicitly supports it.

## Steps

1. Update the product clone.
2. Re-run knowledge extraction.
3. Promote updated knowledge.
4. Generate an update site plan.
5. Run section-specific generators or refresh workflows.
6. Reattach or refresh evidence.
7. Run audit/evaluation gates.
8. Review diffs for unintended broad churn.

## Verification

- Knowledge `repo_sha` changes only when the source changed.
- Content changes map to changed APIs, claims, formats, or planned surfaces.
- Audit and evaluator checks pass.

## References

- [CLI reference](../reference/cli.md#site-planner)
- [Knowledge artifacts](../reference/knowledge-artifacts.md)
- [Content audit and evaluation](content-audit-and-evaluation.md)
- [Governance gates](../reference/governance-gates.md)
