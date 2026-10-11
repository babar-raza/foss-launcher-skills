# Troubleshooting

Status: Current
Audience: Operator, Agent
Canonical reference: `docs/reference/governance-gates.md`
Last code-backed audit: 2026-05-30

## Start Here

1. Identify the failing command or gate.
2. Check [CLI reference](../reference/cli.md) for correct invocation.
3. Check [governance gates](../reference/governance-gates.md) for gate behavior.
4. Check [file contracts](../reference/file-contracts.md) for expected paths.

## Common Symptoms

| Symptom | Likely area | Next page |
|---|---|---|
| Path denied | Governance/file placement | [Governance gates](../reference/governance-gates.md) |
| Content audit fails | API/evidence mismatch | [Content audit and evaluation](../guides/content-audit-and-evaluation.md) |
| Evidence is stale | Knowledge changed | [Evidence repair](../guides/evidence-repair.md) |
| Eval report has FAIL findings | Content quality | [Heal content](../guides/heal-content.md) |
| CLI import fails | Invocation/path issue | [CLI reference](../reference/cli.md) |
