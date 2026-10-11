# Governance Enforcement Architecture

Status: Current
Audience: Contributor, Operator
Canonical reference: `docs/reference/governance-gates.md`
Last code-backed audit: 2026-05-30

Governance enforcement is layered:

1. Preflight and path guard before writes.
2. Hooks for local commit-time enforcement.
3. CI checks for pull request validation.

Reference behavior lives in [Governance gates](../reference/governance-gates.md).
