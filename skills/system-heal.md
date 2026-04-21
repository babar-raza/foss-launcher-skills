---
name: system-heal
id: S-93
description: >
  Audit-driven content healing via gap-eval baseline and classified finding repair.
  Runs when refresh-product exits early but content is suspected stale. Produces a
  BEFORE baseline, classifies findings, heals CONTENT-class issues, and documents
  PIPELINE-class issues.
args: "{family} {platform} [--scope all|docs|products|kb|blog|reference] [--dry-run] [--max-findings N]"
---

# S-93: System Heal — Audit-Driven Content Healing

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform} [--scope all|docs|products|kb|blog|reference] [--no-tier3-cache] [--dry-run] [--max-findings N]`

## Purpose

Audit-driven, issue-by-issue healing for a family/platform. Runs when `refresh-product` (S-84)
exits early (no upstream SHA change) but content is known or suspected to be wrong. Produces a
deterministic BEFORE baseline, classifies each finding by pipeline origin, heals CONTENT-class
issues automatically, and generates a structured pipeline evidence report for PIPELINE-class
issues requiring human action.

**Not a replacement for S-84 (change-driven refresh).** These skills are complementary:
- S-84: triggered by upstream changes
- S-93: triggered by suspected content quality issues without upstream changes

## Pre-conditions

1. `knowledge/{family}/{platform}/merged/model.yaml` with `stale_since: null`
2. Content pages exist for the target scope
3. Clone cache accessible at `runs/.clone_cache/` (optional; disables Tier 2 grep if absent)

## Steps

1. **Parse arguments** and determine scope.

2. **BEFORE baseline**: Run content_eval across all pages in scope:
   ```bash
   python -m scripts.pipeline.content_eval evaluate \
     --family {family} --platform {platform} --scope {scope} --format json \
     > reports/system-heal/{family}-{platform}-before.json
   ```

3. **Classify findings** by origin:
   | Class | Indicators |
   |---|---|
   | `CONTENT` | Wrong claims, stale prose, missing sections, poor evidence |
   | `PIPELINE` | Script bugs, template defects, structural formatting issues |
   | `KNOWLEDGE` | Knowledge model incomplete or stale |

4. **Heal CONTENT-class findings** (if not `--dry-run`):
   - Grade C pages → S-21 (page-enhance)
   - Grade D/F pages → S-26 (heal-page)
   - Missing evidence → S-77 (evidence-repair)
   - Route up to `--max-findings` items (default: 50)

5. **Document PIPELINE-class findings**:
   Write to `reports/system-heal/{family}-{platform}-pipeline-issues.md`:
   - Exact finding with file and line
   - Suspected pipeline origin
   - Recommended investigation path
   Route to S-95 (publish-readiness-review) for governed inspection.

6. **Document KNOWLEDGE-class findings**:
   If `KNOWLEDGE`-class findings exist → recommend running S-12 (knowledge-diff) to check for upstream changes.

7. **AFTER baseline**: Re-run content_eval on healed pages:
   ```bash
   python -m scripts.pipeline.content_eval evaluate \
     --files {healed-pages} --format json \
     > reports/system-heal/{family}-{platform}-after.json
   ```

8. **Verification gate**:
   ```bash
   python scripts/pipeline/post_refresh_verify.py {family} {platform} --scope {scope}
   ```

9. **Summary report**:
   ```
   SYSTEM HEAL — {family}/{platform}
   Scope: {scope}
   Dry-run: {yes|no}

   BEFORE: grade distribution
     A: N  B: N  C: N  D: N  F: N

   Findings classified:
     CONTENT:  N (healed: N)
     PIPELINE: N (documented)
     KNOWLEDGE: N (routed to S-12)

   AFTER: grade distribution
     A: N  B: N  C: N  D: N  F: N

   Verification gate: PASS | FAIL
   Pipeline report: reports/system-heal/{family}-{platform}-pipeline-issues.md
   ```

## Post-conditions

- CONTENT-class findings healed (or queued if `--dry-run`)
- PIPELINE-class findings documented and routed
- Grade distribution improved or unchanged (no regressions)
