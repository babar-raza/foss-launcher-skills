# Python Placement

Status: Current
Audience: Contributor, Agent
Canonical reference: `docs/reference/file-contracts.md#python-files`
Last code-backed audit: 2026-05-30

Use this before creating or moving Python files.

## Placement Rules

- Extend existing scripts before creating parallel helpers.
- Pipeline commands and libraries live under `scripts/pipeline/`.
- CI-only validators live under `scripts/ci/`.
- Operator-run maintenance scripts live under `scripts/maintenance/`.
- Subsystem tools live in their subsystem package.

## Verification

Use preflight for proposed paths and run relevant placement/registry checks before finishing.

References:

- [File contracts](../reference/file-contracts.md)
- [Governance gates](../reference/governance-gates.md)
- [Pipeline registry](../reference/pipeline-registry.md)
