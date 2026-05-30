# Knowledge Pipeline Architecture

Status: Current
Audience: Contributor, Operator
Canonical reference: `docs/reference/knowledge-artifacts.md`
Last code-backed audit: 2026-05-30

The knowledge pipeline converts source code into grounded content inputs.

## Flow

1. Resolve clone cache.
2. Extract source facts with scout.
3. Promote scout artifacts into merged knowledge.
4. Use merged knowledge for planning, generation, evidence, audit, and evaluation.

References:

- [Knowledge artifacts](../reference/knowledge-artifacts.md)
- [Configuration](../reference/config.md#clone-cache)
- [CLI reference](../reference/cli.md#scout)
