# Refresh A Product

Status: Current
Audience: Operator, Agent
Canonical reference: `docs/reference/cli.md`
Last code-backed audit: 2026-05-30

Goal: update existing generated content after upstream source changes.

## Prerequisites

- Product source clone exists or can be created.
- Current product is listed in `data/products.json`.
- Existing content is not manually protected unless the workflow explicitly supports it.

## Steps

1. Update the product clone.
2. Re-run knowledge extraction.
3. Promote updated knowledge.
4. Generate an update site plan.
5. Run section-specific generators or refresh workflows.
6. Reattach or refresh evidence.
7. Run audit/evaluation gates.
8. Review diffs for unintended broad churn.

## Verification

- Knowledge `repo_sha` changes only when the source changed.
- Content changes map to changed APIs, claims, formats, or planned surfaces.
- Audit and evaluator checks pass.

## Two-Step Reference Page Regeneration

When a knowledge delta contains `removed_apis` (classes removed from the FOSS source),
reference pages for classes **not in `modified_apis`** may retain phantom methods —
methods that only existed because they were defined in the now-deleted classes and
were inherited or referenced by still-existing classes.

**When this applies**: `knowledge_delta.json` has `removed_apis` count > 0.

**Pattern**:
```bash
# Step 1 — update only modified classes
.venv/Scripts/python scripts/pipeline/commands/content/batch_reference.py {family} {platform} --update

# Step 2 — rebuild all to clear phantom methods in non-modified classes
.venv/Scripts/python scripts/pipeline/commands/content/batch_reference.py {family} {platform} --rebuild-all
```

**Why step 2 is required**: `--update` regenerates only classes listed in
`modified_apis`. Classes not in that list are skipped — even if they had
phantom methods from the removed classes as side effects. Only `--rebuild-all`
regenerates every reference page and removes those phantom entries.

**Proof**: `pdf/java` sprint 2026-06-12 — `Rectangle.md` was not in `modified_apis`
but had phantom `fromCOSArray`/`toCOSArray` methods that survived `--update`.
Only resolved by `--rebuild-all` after `COSBase` and related COS classes were removed.

This rule is also encoded in the `refresh-product` skill spec (S-84, Step 7).

## References

- [CLI reference](../reference/cli.md#site-planner)
- [Knowledge artifacts](../reference/knowledge-artifacts.md)
- [Content audit and evaluation](content-audit-and-evaluation.md)
- [Governance gates](../reference/governance-gates.md)
