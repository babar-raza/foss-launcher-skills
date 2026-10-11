# Heal Content

Status: Current
Audience: Operator, Agent
Canonical reference: `docs/reference/governance-gates.md`
Last code-backed audit: 2026-05-30

Goal: fix content quality failures while preserving source truth and evidence.

## When To Use

- Content audit reports FAIL findings.
- Evaluator grades or findings identify repairable issues.
- Evidence is stale or incomplete.

## Steps

1. Classify the failing finding.
2. Check whether the issue is content, evidence, knowledge, or pipeline behavior.
3. For evidence-only issues, use [Evidence repair](evidence-repair.md).
4. For stale knowledge, refresh knowledge before editing content.
5. Apply the smallest governed repair.
6. Re-run audit and evaluation.

## Verification

- Same finding no longer reproduces.
- No unrelated content churn appears in the diff.
- Evidence remains valid.

## References

- [Content audit and evaluation](content-audit-and-evaluation.md)
- [Content contracts](../reference/content-contracts.md)
- [Governance gates](../reference/governance-gates.md)
