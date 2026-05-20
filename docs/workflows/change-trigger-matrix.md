<!-- Adapted from aspose.org docs/workflows/ for standalone use -->

# Regeneration Triggers and Change-Trigger Matrix

## Regeneration After Extraction Script Changes

When a change is made to extraction or enrichment scripts that alters what is extracted or how claims are synthesized:

1. **Re-run the knowledge bootstrap** for ALL affected products:
   ```bash
   scripts/pipeline/commands/knowledge/scout.py {family} {platform}
   scripts/pipeline/commands/knowledge/enrich.py {family} {platform}
   scripts/pipeline/commands/knowledge/promote.py {family} {platform}
   ```
2. **Check for knowledge drift**: compare merged/api_surface.json and merged/formats.json before and after.
3. **Re-evaluate all content** for affected products:
   ```bash
   scripts/pipeline/content_eval/cli evaluate {family} {platform} --write-grade
   ```
4. **Re-run the launch gate** before promoting any affected product.

**Rationale**: Extraction script changes can silently change the API surface model. Content generated before the change may reference APIs or formats that the new extraction no longer includes, or vice versa. This creates a hidden discrepancy that evaluators cannot catch without re-grounding.

**Scope**: Applies to changes to scout.py, enrich.py, and any extractor plugin under `scripts/pipeline/extraction/`. Does NOT apply to changes to content-evaluation logic (`content_eval/evaluators/`) -- those follow the evaluator change checklist instead.

## Change-Trigger Matrix

Use this matrix to decide what action is required when a specific artifact or script changes.

| Changed artifact | Required action | Scope |
|-----------------|-----------------|-------|
| Clone cache updated (upstream repo changed) | Run knowledge-diff -> knowledge-update -> re-evaluate affected pages | Per product |
| `scout.py` or `enrich.py` logic changed | Re-run knowledge bootstrap + full re-evaluate (see above) | All products |
| `promote.py` logic changed | Re-run promote for all products; check merged artifacts | All products |
| `content_eval/evaluators/*.py` logic changed | Bump EVALUATOR_LOGIC_VERSION; re-grade all pages (evaluator change checklist) | All products |
| Content page changed | Run content-check + audit.py + attach_evidence.py | Per file |
| `knowledge/{family}/{platform}/merged/*.json` updated | Re-run attach_evidence.py for affected product | Per product |
| `skills/*.md` skill file changed | Test with 1 representative run; verify post-conditions fire correctly | Per skill |
| Publish-readiness review skill changed | Run DAR coverage check to verify alignment; run dry-run on 1 product | Self-test |
| Path guard script changed | Run path guard tests -- must exit 0 | Self-test |
| Governance document changed | Verify alignment with session gate document | Self |
| Running batch reference generation for a product | Verify member-doc ERC coverage >= 20% per product first; if below threshold, run enrich then promote before generating reference pages | Per product |
| `enrich.py --mode member-doc` completed | Run `promote.py` to merge enriched claims, then verify coverage with description coverage audit | Per product |
| Refresh produces coverage report showing < 100% subdomain coverage | Re-run refresh to fill gaps; or manually run refresh review to assess which subdomains were missed | Per product |
| Qualifying report written to `reports/` | Automatic harvest via producing skill; safety net via backlog update and session-start advisory | Per report |
| `data/products.json` new candidate added | Run discovery triage to route candidate to backlog | Per discovery scan |
| All active products swept for SHA changes | Run discovery triage to route findings to backlog items | Per sweep |

**Manual edit after content-only change**: Use manual-edit skill -> re-run content-check + audit.py. Do not re-run knowledge bootstrap unless `stale_since` is set -- content-only edits do not require knowledge regeneration.

**Format/claims contradiction found**: Fix the higher-priority source (formats.json or claims.json) and re-run promote.py. If the contradiction is in the clone cache source itself, file an issue in the upstream repo and document the discrepancy in `knowledge/{family}/{platform}/merged/limitations.md`.
