# Content Contracts Reference

Status: Current
Audience: Operator, Contributor, Agent
Canonical reference: this page
Last code-backed audit: 2026-05-30

Generated content must reflect higher-priority source truth from clone cache and knowledge artifacts.

## Content Paths

See [file contracts](file-contracts.md#content-trees) for canonical site paths.

## Evidence

Every content page that participates in the governed pipeline needs evidence frontmatter that ties claims and API references to knowledge artifacts.

Evidence attachment is implemented by:

- `scripts/pipeline/commands/healing/attach_evidence.py`
- `scripts/pipeline/evidence/runner.py`

The runner parses frontmatter, skips drafts/current evidence, verifies tokens, maps verified tokens to claims/API refs, and writes evidence frontmatter.

## Content Audit

Content audit is implemented by `scripts/pipeline/commands/content/audit.py`. It verifies API tokens and evidence blocks against merged knowledge.

Use [CLI reference](cli.md#content-eval) for evaluator commands and [Content audit and evaluation](../guides/content-audit-and-evaluation.md) for scenario steps.

## Naming

Content filenames must follow the validators enforced by CI and pre-commit checks. Reference pages may allow API-style names; prose trees use lowercase hyphenated slugs.

## Provenance

Provenance belongs in frontmatter, not inline comments. Pages generated or evaluated without knowledge must not be treated as fully grounded.

## Hugo Rendering

For theme assignment, layout selection, shortcode availability per site, data file
consumption, frontmatter contracts per content type, link generation rules, locale
rules, allowed/forbidden edit paths, post-change inspection, the evidence contract,
common failure modes, and the agent edit checklist, see [hugo-rendering.md](hugo-rendering.md).
