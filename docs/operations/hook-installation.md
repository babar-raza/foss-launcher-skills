# Hook Installation

Status: Current
Audience: Operator, Contributor
Canonical reference: `docs/reference/governance-gates.md`
Last code-backed audit: 2026-05-30

The hook installer is `scripts/install-hooks.sh`.

It installs:

- `pre-commit`
- `commit-msg`
- `post-commit`
- `reference-transaction`

Run it after cloning or when hooks are missing. See [governance gates](../reference/governance-gates.md) for what the hooks enforce.
