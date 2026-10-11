# Hard-Stop Recovery

Status: Current
Audience: Operator, Agent
Canonical reference: `docs/reference/governance-gates.md`
Last code-backed audit: 2026-05-30

Use this when a governed workflow blocks progress.

## Recovery Pattern

1. Identify the blocking gate.
2. Read the relevant canonical reference.
3. Fix the root cause rather than bypassing the gate.
4. Re-run the same command that failed.
5. Record the outcome in the workflow report if the task requires one.

## Common Blocks

| Block | Recovery |
|---|---|
| Path guard denial | Verify the target path in [file contracts](../reference/file-contracts.md) and [governance gates](../reference/governance-gates.md). |
| Content audit failure | Use [Content audit and evaluation](../guides/content-audit-and-evaluation.md), then repair content/evidence/knowledge as appropriate. |
| Missing or stale knowledge | Refresh knowledge before generation or healing. |
| Evidence failure | Use [Evidence repair](../guides/evidence-repair.md). |
| CI gate failure | Match the CI step to the reference or development page, then rerun locally where possible. |

## References

- [Governance gates](../reference/governance-gates.md)
- [CLI reference](../reference/cli.md)
- [Testing and CI](../development/testing.md)
