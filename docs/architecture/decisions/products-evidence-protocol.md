# Decision Record: products.aspose.org Evidence Protocol

**Plan ID**: zippy-imagining-candle (TC-CLAIM-10)
**Date**: 2026-05-02
**Status**: ACCEPTED

---

## Context

`products.aspose.org` occupies a unique position in the site architecture:
- Family-level landing pages (`cells/_index.md`) serve product introductions
- Platform-level pages (`cells/java/_index.md`) serve technical overviews with API context
- Evidence injection is listed as `validate_only` in `data/refresh-dependencies.json` with no `backing_generator`
- 145 files under `content/products.aspose.org/` have ERC IDs (agent-executed injection)
- Platform-level pages have evidence blocks with CLM/ERC claims and grade A
- Family-level landing pages have no evidence block (current state, no urgency to change)

## Decisions

### 1. Keep existing products claims as-is
**Decision**: YES — preserve existing claims until TC-CLAIM-05 stale detection identifies specific orphans.

Rationale: existing claims passed audit checks. Mass revert without evidence of staleness would create unnecessary churn.

### 2. Validate-only behavior
**Decision**: products pages participate in `--detect-stale-claims` report (TC-CLAIM-05) but receive no write-path injection from scripts.

Script-driven injection is out of scope for products. Agent-executed injection is the current pattern per dependency registry.

### 3. Future script-driven injection
**Decision**: DEFERRED — requires separate design.

The `validate_only` surface designation is intentional. No script-backed path exists because products pages require editorial review before claim injection. Any future automation must be designed with a dedicated products-injection skill.

### 4. Family landing pages with no evidence block
**Decision**: DEFER — current state (`cells/_index.md` without evidence block) is valid for `validate_only` surfaces.

No CI failure fires for missing evidence on products family pages. This is by design until a products injection protocol is established.

### 5. ClaimPolicy and ClaimValidator participation
**Decision**: YES — products pages are included in:
- ClaimPolicy evaluation (TC-CLAIM-08): WARN on page_role mismatch, BLOCK on unknown claim IDs in report output
- ClaimValidator stale detection (TC-CLAIM-05): included in stale detection report with no write output
- WARN-only CI reporting (TC-CLAIM-11): included in non-reference claim CI report

### 6. CI for products
**Decision**: WARN-only (Sprint 1).

No blocking until the first stale detection report is reviewed and false-positive rate is confirmed. Existing `validate_frontmatter.py` P-03/P-04 checks (non-empty claims/apis) apply only to blog posts, not products pages.

## Non-Goals

- Write-path evidence injection to `products.aspose.org` content files (in this sprint)
- Automatic removal of existing claims without stale detection report review
- page_role routing enforcement on products pages
- `claims_hash` frontmatter writes (deferred to TC-CLAIM-04 Phase 2)
- Hugo rendering changes

## References

- `data/refresh-dependencies.json`: products surface as `validate_only`
- `scripts/pipeline/evidence/claim_validator.py`: stale detection module (TC-CLAIM-05)
- `scripts/pipeline/evidence/claim_policy.py`: policy evaluation module (TC-CLAIM-08)
- `scripts/pipeline/commands/content/claim_report.py`: WARN-only CI report (TC-CLAIM-11)
- Plan: `zippy-imagining-candle.md` Section T (Products Scope Policy)
