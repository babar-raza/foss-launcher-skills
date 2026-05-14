---
name: seo-review
id: S-109
description: >
  Governance-only review gate for pending SEO recommendations. Produces an
  approval manifest and never edits content directly.
args: "[--level HIGH|MEDIUM|LOW|all] [--site SITE] [--family FAMILY] [--limit N]"
---

# S-109: SEO Review — Recommendation Approval Gate

Review pending SEO recommendations, approve or reject safe field updates, and write an approval manifest for a separate apply step.

**Arguments:** `$ARGUMENTS`

## Status

This standalone skill restores the `seo-review` command surface from the embedded aspose.org skill set as a governance-only utility. The full SEO pipeline is not included in this standalone repo.

## Expected Format

```text
[--level HIGH|MEDIUM|LOW|all] [--site SITE] [--family FAMILY] [--limit N]
```

Default review scope is HIGH and MEDIUM recommendations across all sites.

## Inputs

One of:

- `reports/seo/safe_recommendations.json`
- `reports/reports/seo/safe_recommendations.json`

The recommendations must already have passed upstream safety checks.

## Workflow

1. Locate `safe_recommendations.json`.
2. Filter by level, site, family, and limit.
3. Present before/after diffs for SEO fields.
4. Collect approve, reject, skip, or quit decisions.
5. Write approved decisions to `patches/seo/patch_manifest.json`.
6. Run the separate SEO apply command in dry-run mode before any real application.

## Output Manifest

The approval manifest must use this shape:

```json
{
  "batch_id": "<ISO-timestamp>",
  "generated_at": "<YYYY-MM-DD>",
  "reviewed_by": "human",
  "total_patches": 0,
  "patches": []
}
```

Only approved, safety-checked field updates may appear in `patches`.

## Safety

- Never modify content files directly.
- Never modify `evidence`, `model_sha`, `claims`, `apis`, or `formats` frontmatter.
- Never approve fabricated API names.
- Never approve descriptions outside the project SEO length policy.
- If the knowledge model is stale for a page's family/platform, skip that page.
- The only allowed write for this skill is `patches/seo/patch_manifest.json`.

## Migration Note

The aspose.org reference implementation expects `scripts/seo/pipeline/*`. That pipeline is site-repo specific and is not ported here. A future taskcard may port it as an optional standalone SEO package; until then, this skill preserves the review gate contract and keeps SEO separate from evidence-grounded content generation.

## Verification

- Run `python scripts/validate_skills.py`.
- Confirm provider mirrors are synced.
- Future implementation must add fixture tests that load sample recommendations and produce a manifest without touching content.
