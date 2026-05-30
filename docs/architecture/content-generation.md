# Content Generation Architecture

Status: Current
Audience: Contributor, Operator
Canonical reference: `docs/reference/content-contracts.md`
Last code-backed audit: 2026-05-30

Generated content is an output artifact. It must reflect clone-cache and knowledge truth.

## Flow

1. Site planning chooses required pages and sections.
2. Generators create or update content files.
3. Evidence attachment maps content to claims/API refs.
4. Audit and evaluation verify generated output.

References:

- [Content contracts](../reference/content-contracts.md)
- [File contracts](../reference/file-contracts.md)
- [CLI reference](../reference/cli.md)
