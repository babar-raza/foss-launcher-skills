---
# Governance child document — extracted from AGENTS.md
# Source: AGENTS.md §9b, §9c
# Plan: delightful-wondering-hartmanis (TC-04)
# Extracted: 2026-04-28
---

# Regeneration Triggers and Change-Trigger Matrix

## 9b. Regeneration After Extraction Script Changes

When a change is made to `scripts/pipeline/extraction/scout.py` or `scripts/pipeline/enrich.py` that alters what is extracted or how claims are synthesized:

1. **Re-run the knowledge bootstrap** for ALL affected products:
   ```bash
   python scripts/pipeline/scout.py {family} {platform}
   python scripts/pipeline/enrich.py {family} {platform}
   python scripts/pipeline/promote.py {family} {platform}
   ```
2. **Check for knowledge drift**: compare merged/api_surface.json and merged/formats.json before and after.
3. **Re-evaluate all content** for affected products:
   ```bash
   python -m scripts.pipeline.content_eval.cli evaluate {family} {platform} --write-grade
   ```
4. **Re-run the launch gate** before promoting any affected product.

**Rationale**: Extraction script changes can silently change the API surface model. Content generated before the change may reference APIs or formats that the new extraction no longer includes, or vice versa. This creates a hidden discrepancy that evaluators cannot catch without re-grounding.

**Scope**: Applies to changes to scout.py, enrich.py, and any extractor plugin under `scripts/pipeline/extraction/`. Does NOT apply to changes to content-evaluation logic (`content_eval/evaluators/`) — those follow the §9a checklist instead.

## 9c. Change-Trigger Matrix

Use this matrix to decide what action is required when a specific artifact or script changes.

| Changed artifact | Required action | Scope |
|-----------------|-----------------|-------|
| Clone cache updated (upstream repo changed) | Run S-12 → S-14 → re-evaluate affected pages | Per product |
| `scout.py` or `enrich.py` logic changed | Re-run knowledge bootstrap + full re-evaluate (§9b) | All products |
| `promote.py` logic changed | Re-run promote for all products; check merged artifacts | All products |
| `content_eval/evaluators/*.py` logic changed | Bump EVALUATOR_LOGIC_VERSION; re-grade all pages (§9a) | All products |
| `content/` page changed | Run S-23 (content-check) + audit.py + attach_evidence.py | Per file |
| `knowledge/{family}/{platform}/merged/*.json` updated | Re-run attach_evidence.py for affected product | Per product |
| `skills/*.md` skill file changed | Test with 1 representative run; verify post-conditions fire correctly | Per skill |
| `skills/publish-readiness-review.md` changed (S-90) | Run `python scripts/ci/check_dar_coverage.py` to verify DAR alignment; run S-90 dry-run on 1 product | Self-test |
| `scripts/pipeline/path_guard.py` changed | Run `pytest scripts/pipeline/tests/test_path_guard.py` — must exit 0 | Self-test |
| `AGENTS.md` changed | Verify CLAUDE.md §6 alignment (see CLAUDE.md alignment note) | Self |
| Running `batch_reference` (S-62) for a product | Verify member-doc ERC coverage ≥ 20% per product first: `python scripts/pipeline/description_coverage_audit.py`; if any product is below threshold, run `enrich --mode member-doc` then `promote.py` before generating reference pages | Per product |
| `enrich.py --mode member-doc` completed | Run `promote.py` to merge enriched claims, then verify coverage with `description_coverage_audit.py` | Per product |
| Refresh produces `coverage_report.md` showing < 100% subdomain coverage | Re-run `/refresh-product {family} {platform}` to fill gaps; or manually run `refresh_review.py {family} {platform} --report` to assess which subdomains were missed | Per product |
| Qualifying report written to `reports/` | Automatic harvest via producing skill (S-87 Phase 8 step 10, S-76 step 5b); safety net via `/backlog update` step 1b and `/session-start` step 6 advisory | Per report |
| `data/products.json` new candidate added (S-93 `--apply`) | Run S-95 `/discovery-triage` to route candidate to backlog | Per discovery scan |
| All active products swept for SHA changes (S-94) | Run S-95 `/discovery-triage` to route HIGH/MEDIUM findings to backlog items | Per sweep |

**Manual edit after content-only change**: Use S-73 (manual-edit) → re-run S-23 + audit.py. Do not re-run knowledge bootstrap unless `stale_since` is set — content-only edits do not require knowledge regeneration.

**Format/claims contradiction found**: Fix the higher-priority source (formats.json or claims.json) and re-run promote.py. If the contradiction is in the clone cache source itself, file an issue in the FOSS repo and document the discrepancy in `knowledge/{family}/{platform}/merged/limitations.md`.

