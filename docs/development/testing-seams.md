# Testing Seams

Status: Current
Audience: Contributor
Canonical reference: `docs/development/testing.md`
Last code-backed audit: 2026-05-30

Testing seams should make code testable without weakening runtime behavior.

## Rules

- Prefer explicit dependency injection seams over broad monkeypatching.
- Keep CLI entry points thin and test implementation modules directly where possible.
- Add focused tests for new shared behavior.

See [Testing and CI](testing.md).
