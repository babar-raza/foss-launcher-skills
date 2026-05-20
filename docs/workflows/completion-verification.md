<!-- Adapted from aspose.org docs/workflows/ for standalone use -->

# Completion Verification Protocol

When reviewing whether a task, sprint, or acceptance criterion is complete, the agent or reviewer must assign one of the following verification tiers. A lower tier cannot be substituted for a higher tier to claim completion.

| Tier | Label | Meaning |
|------|-------|---------|
| 1 | Written | File was edited. No verification performed. Mark as `[written]`, not `[x]`. |
| 2 | Tested | Automated test covers the criterion. Test was run and passed. |
| 3 | Runtime-validated | Script or tool confirmed behavior at runtime. |
| 4 | Behaviorally proven | Confirmed in real agent execution, not only in file state. |

### Rules

1. A criterion is `[x]` (complete) only when it reaches the minimum tier required by the
   governing plan or specification. Where no minimum is stated, Tier 2 (Tested) is the
   default minimum.
2. `[written]` is not completion -- it is the start of the work. Do not mark criteria
   complete when only Tier 1 (Written) evidence exists.
3. Sprint summaries must include a tier breakdown (count per tier). A summary that marks
   everything `[x]` without naming verification actions is non-conforming.
4. Any criterion marked complete without a named verification action is automatically
   treated as OPEN on the next review cycle.
5. Claims about behavioral compliance (e.g., "agents follow skill chains") require at
   minimum Tier 4 (Behaviorally proven). They must not be asserted on the basis of
   documentation changes alone.
