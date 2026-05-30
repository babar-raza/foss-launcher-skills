# Concepts

Status: Current
Audience: User, Operator, Contributor
Canonical reference: `docs/reference/file-contracts.md`
Last code-backed audit: 2026-05-30

## Product

A product is identified by `{family}/{platform}`, for example `cells/python` or `slides/java`.

## Clone Cache

The local source checkout for each FOSS product. The default location is `runs/.clone_cache/`; see [configuration](../reference/config.md#clone-cache).

## Knowledge

Structured truth extracted from source. The two main layers are:

- `knowledge/{family}/{platform}/scout/`
- `knowledge/{family}/{platform}/merged/`

See [knowledge artifacts](../reference/knowledge-artifacts.md).

## Content

Generated Hugo markdown under `content/`. Content is not source truth; it must reflect the clone cache and knowledge artifacts.

## Evidence

Frontmatter data that ties content claims and API references to knowledge. See [content contracts](../reference/content-contracts.md#evidence).

## Guide

A scenario-driven procedure. Guides link to references rather than repeating exhaustive tables.

## Reference

The canonical home for exhaustive facts such as CLI flags, config keys, file contracts, schemas, and gates.
