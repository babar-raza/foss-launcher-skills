# Completion Verification Protocol

> Source: AGENTS.md §14
> Status: Current (restored from archive 2026-06-24)
> Override token: 20260624-113217-docs-workflows-mental-model-refresh-md

When reviewing whether a task, sprint, or acceptance criterion is complete, assign one of these
verification tiers. A lower tier cannot substitute for a higher tier.

## Verification Tiers

| Tier | Label | Meaning |
|------|-------|---------|
| 1 | Written | File was edited. No verification performed. Mark `[written]`, not `[x]`. |
| 2 | Tested | Automated test covers the criterion. Test was run and passed. |
| 3 | Runtime-validated | Script or tool confirmed behavior at runtime. |
| 4 | Behaviorally proven | Confirmed in real agent execution, not only file state. |

## Rules

1. A criterion is `[x]` (complete) only when it reaches the minimum tier required by the
   governing plan. Where no minimum is stated, Tier 2 (Tested) is the default minimum.
2. `[written]` is not completion — it is the start of the work. Do not mark complete when
   only Tier 1 evidence exists.
3. Sprint summaries must include a tier breakdown (count per tier).
4. Any criterion marked complete without a named verification action is automatically
   downgraded to Tier 1 for audit purposes.

## How to Apply

After completing any task:
- State which tier the verification reached
- Name the specific verification action (e.g., "pytest tests/test_foo.py — 5 passed")
- If a higher tier was not reached, explain why and what would be needed

## Archive

Pre-refactor version:
[docs/_archive/pre-refactor/workflows/completion-verification.md](../_archive/pre-refactor/workflows/completion-verification.md)
