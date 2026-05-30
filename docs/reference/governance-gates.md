# Governance Gates Reference

Status: Current
Audience: Operator, Contributor, Agent
Canonical reference: this page
Last code-backed audit: 2026-05-30

This page owns current gate behavior. Guides should link here instead of repeating gate tables.

## Preflight

`scripts/pipeline/commands/launch/preflight.py` runs:

1. Path guard.
2. Python placement check.
3. Content workflow marker check for `content/` paths.

See [CLI reference](cli.md#preflight).

## Path Guard

`scripts/pipeline/commands/governance/path_guard.py` evaluates:

1. Forbidden exact paths.
2. Forbidden prefixes.
3. Allowed prefixes.
4. Default deny.

Use [file contracts](file-contracts.md) for allowed documentation structure.

## Hook Installation

`scripts/install-hooks.sh` installs:

- `pre-commit`
- `commit-msg`
- `post-commit`
- `reference-transaction`

See [Hook installation](../operations/hook-installation.md).

## CI Gates

The content audit workflow runs checks for:

- Reports boundary.
- Blog slug hygiene.
- Content filename conventions.
- API accuracy audit.
- Audit regression.
- Grade presence/integrity/downgrade/churn.
- Strict content evaluation.
- Frontmatter validation.
- Skill documentation/sync/registry checks.
- Clone cache reference checks.
- Pipeline registration.
- Python placement.

## Docs Root Hygiene

Post-migration, `docs/` root must contain only `README.md` plus directories. Root-level markdown files other than `README.md` are not allowed.
