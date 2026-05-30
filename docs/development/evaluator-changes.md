# Evaluator Changes

Status: Current
Audience: Contributor
Canonical reference: `docs/development/testing.md`
Last code-backed audit: 2026-05-30

Evaluator changes affect content quality gates and must be tested carefully.

## Checklist

1. Identify the evaluator and affected findings.
2. Add or update focused tests under `scripts/pipeline/tests/content_eval/`.
3. Run focused evaluator tests.
4. Run broader content eval tests if behavior affects shared grading or strict mode.
5. Update references only if CLI/config/contracts changed.

References:

- [Content audit and evaluation](../guides/content-audit-and-evaluation.md)
- [Testing and CI](testing.md)
- [Governance gates](../reference/governance-gates.md)
