# ADR-003: Evidence-First Content Generation

**Date:** 2026-05-25
**Status:** Accepted
**Deciders:** Project maintainers

---

## Context

Early content generation trials used LLMs to write documentation pages directly from product names and descriptions. The resulting content frequently contained:
- Fabricated API method names that did not exist in the actual library
- Incorrect format claims (e.g., claiming PDF/A support for products that lacked it)
- Outdated version information
- Code snippets that did not compile

These fabrications eroded user trust and required manual correction after every generation run.

## Decision

We adopted an **evidence-first content generation model** with three mandatory pre-conditions:

1. **Knowledge model must exist**: A `knowledge/{family}/{platform}/model.yaml` file must be present for the product before any content page is written. This model is built by the repo-scout (S-34) and truth-merge (S-35) skills from actual source code inspection.

2. **Knowledge must be fresh**: If `model.yaml` has `stale_since != null`, content generation is blocked. The stale detection skill (S-13) and knowledge update skill (S-14) must be run first.

3. **Ground-check must pass**: Before any content write, `scripts/pre_write.py` runs ground-check (S-23) to verify that all claims in the planned content map to evidence in the knowledge model. Unverified claims block the write.

The evidence hierarchy is: **source code > tests > CI artifacts > operational artifacts > documentation > naming**.

## Alternatives Considered

- **Post-generation validation**: Check content after writing. Rejected because it doesn't prevent the write and creates cleanup burden.
- **Human review of all content**: Rejected as it eliminates automation benefit.
- **LLM self-evaluation**: Ask the LLM to verify its own claims. Rejected as insufficient; the LLM may fabricate the verification as readily as the claim.

## Consequences

**Positive:**
- All published content is grounded in verified source code evidence.
- Fabricated API names and format claims are blocked before they reach the content repo.
- The knowledge model serves as a single source of truth that can be updated independently of content.

**Negative:**
- Content cannot be generated for products without a knowledge model (requires running repo-scout first).
- Ground-check adds latency to the generation workflow.
- Evidence model quality depends on repo-scout quality; gaps in source code coverage create gaps in evidence.

## Enforcement

- `scripts/pre_write.py` enforces ground-check on every content write.
- AGENTS.md Section 5 specifies the evidence requirements as non-negotiable.
- claim coverage reports (`reports/claim-coverage-*.md`) track verified vs. unverified claims.
