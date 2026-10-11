# Operator Quickstart

Status: Current
Audience: Operator
Canonical reference: `docs/reference/cli.md`
Last code-backed audit: 2026-05-30

Goal: get from a clean checkout to a validated operator workflow without learning every command first.

## Prerequisites

- Use Git Bash for local Windows operations.
- Install Python dependencies for the relevant subsystem.
- Install governance hooks before committing.

For complete config and dependency details, see:

- [Configuration reference](../reference/config.md)
- [Governance gates](../reference/governance-gates.md)
- [CLI reference](../reference/cli.md)

## First Session

1. Read the repo root operating instructions.
2. Confirm no `public-*` build artifacts exist in the repo root.
3. Install hooks with `scripts/install-hooks.sh`.
4. Use a scenario guide instead of ad hoc commands.

## Common Workflows

| Goal | Guide |
|---|---|
| Launch a product | [Launch a product](../guides/launch-product.md) |
| Refresh after upstream changes | [Refresh a product](../guides/refresh-product.md) |
| Scan repos or sweep changes | [Discovery and change sweep](../guides/discovery-and-change-sweep.md) |
| Audit/evaluate content | [Content audit and evaluation](../guides/content-audit-and-evaluation.md) |
| Heal content | [Heal content](../guides/heal-content.md) |
| Recover from hard stops | [Hard-stop recovery](../operations/hard-stop-recovery.md) |

## Verification

Before finishing a workflow:

- Run the validation command named by the guide.
- Confirm generated artifacts are in expected paths from [file contracts](../reference/file-contracts.md).
- Confirm docs root hygiene if the workflow touched `docs/`.
