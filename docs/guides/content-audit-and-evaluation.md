# Content Audit And Evaluation

Status: Current
Audience: Operator, Contributor, Agent
Canonical reference: `docs/reference/cli.md#content-eval`
Last code-backed audit: 2026-05-30

Goal: validate generated content against merged knowledge and evaluator rules.

## When To Use

- Before finishing generated content work.
- After evidence repair or content healing.
- When CI reports content audit or evaluator failures.

## Steps

1. Run token/evidence audit for changed content.
2. Run content evaluation on changed files or product scope.
3. Inspect FAIL findings before changing content.
4. Use healing or evidence repair guides for fixes.
5. Re-run the same checks after fixes.

## Verification

- API references resolve to merged `api_surface.json`.
- Evidence frontmatter is valid.
- Evaluator FAIL findings are gone or explicitly escalated through governed review.

## References

- [CLI reference](../reference/cli.md#content-eval)
- [Content contracts](../reference/content-contracts.md)
- [Knowledge artifacts](../reference/knowledge-artifacts.md)
- [Hard-stop recovery](../operations/hard-stop-recovery.md)
