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

`.github/workflows/content-audit.yml` is **not** the live gate. It is `pull_request`-triggered
only, and this repo's real production path is a direct push to `main` (AGENTS.md §2b,
CLAUDE.md) — that trigger structurally never fires. `.github/workflows/` is a blanket T-00
(never-deletable) path, so this file is kept permanently as inert dead weight rather than
removed; do not treat it as describing current behavior.

The live, push-triggered gate is **`.github/workflows/content-governance-checks.yml`**. It
runs checks for:

- Blog slug hygiene, family route coverage, platform indexes (advisory), family icon uniqueness.
- API accuracy audit + audit regression (currently landing, non-blocking).
- Grade presence/integrity on changed content files.
- Manifest/frontmatter consistency (GUARD-04), all-locale frontmatter structure validation.
- Evaluator freeze check (currently landing, non-blocking).
- Skill documentation coverage, skill registry completeness.
- DAR coverage alignment (currently landing, non-blocking), DAR-table skill-ID accuracy.
- Pipeline path integrity, clone cache reference checks, pipeline script registration
  (currently landing, non-blocking).
- Real Hugo build verification (`products.aspose.org`).

A number of checks that used to live only in `content-audit.yml` were deliberately **not**
migrated here because they already have a live local or push-triggered equivalent elsewhere
(pre-commit hooks, `skill-governance.yml`, etc.) — see the header comment of
`content-governance-checks.yml` for the full accounting, including
**Deletion approvals (GUARD-DEL-01)**, enforced locally by the pre-commit hook rather than
this workflow. See [deletion governance](../DELETION_GOVERNANCE.md).

Several other push-triggered workflows gate narrower path sets:
`skill-governance.yml` (skills/agent-tree sync), `extraction-pipeline.yml` (format
cross-reference), `ci-eval-consistency.yml` (eval rerun consistency + onboarding doc
integrity), `metrics-governance.yml`, `reference-index-structure.yml`,
`llms-generation.yml`. See [Testing and CI](../development/testing.md) for the full
CI-job-to-local-command parity table.

## Docs Root Hygiene

Post-migration, `docs/` root must contain only `README.md` plus directories. Root-level markdown files other than `README.md` are not allowed.
