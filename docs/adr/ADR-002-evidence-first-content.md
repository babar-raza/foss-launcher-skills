# ADR-002: Evidence-First Content Generation

**Date:** 2026-04-01
**Status:** Accepted
**Deciders:** @prora

## Context

LLM-generated documentation tends to hallucinate API names, method signatures, format support, and behavioral claims. For a technical product documentation system covering 24 Aspose FOSS libraries, hallucinated facts are a serious trust and accuracy problem.

The prior approach (generate content from a product name alone) produced content that described non-existent methods and claimed format support that wasn't implemented.

## Decision

We adopt an **evidence-first generation model** enforced at three layers:

1. **Knowledge gate** (`scripts/pre_write.py`): Every content write is preceded by a `pre_write_check()` call that verifies the target product has a valid, non-stale `knowledge/{family}/{platform}/merged/model.yaml`. Writes to products without bootstrapped knowledge are blocked (exit code 1).

2. **Evidence frontmatter** (`scripts/pipeline/audit.py`): All generated content pages must include an `evidence:` block in their YAML frontmatter, citing the `model_sha`, `model_version`, and specific `claims`, `apis`, and `formats` referenced. Pages without this block are flagged as FAIL by the audit pipeline.

3. **Path guard** (`scripts/path_guard.py`): Content writes to arbitrary paths are blocked unless the path matches the allowed content layout (e.g., `content/docs.aspose.org/en/{family}/{platform}/`).

The knowledge model is sourced from real FOSS repository analysis using tree-sitter (S-34: repo-scout), merged with external truth sources (S-35: truth-merge), and stored as structured JSON/YAML artifacts in `knowledge/`.

## Alternatives Considered

- **Post-publication fact-checking**: Rejected — errors are more costly to fix after publishing; the gate pattern prevents them at source.
- **Manual review of all content**: Rejected — not scalable across 1800 content surfaces.
- **API documentation scraping**: Rejected — Aspose FOSS repos have structured source code that tree-sitter can extract more reliably than scraping.

## Consequences

- No content can be generated for products without a bootstrapped knowledge model
- Knowledge models must be refreshed when upstream repos change (S-12 → S-14 workflow)
- Evidence frontmatter creates a verifiable audit trail per content page
- False negatives are possible if the knowledge model is outdated (stale_since check addresses this)

## Implementation

- Pre-write gate: [`scripts/pre_write.py`](../../scripts/pre_write.py)
- Path guard: [`scripts/path_guard.py`](../../scripts/path_guard.py)
- Knowledge model schema: `knowledge/{family}/{platform}/merged/model.yaml`
- Audit pipeline: `scripts/pipeline/audit.py`
- Stale detection: S-13 (stale-detect skill)
- Evidence-first mandate: [`AGENTS.md`](../../AGENTS.md) Section 5
