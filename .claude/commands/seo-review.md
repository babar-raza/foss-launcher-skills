# SEO Review — Human Review Gate for Pending SEO Recommendations

**Arguments**: $ARGUMENTS
Expected format: `[--level HIGH|MEDIUM|LOW|all] [--site <site>] [--family <family>] [--limit <N>]`
Default: review MEDIUM + HIGH opportunities, all sites.

## Purpose

Load `safe_recommendations.json`, present pending MEDIUM/HIGH SEO field updates as
before/after diffs, collect approve/reject decisions per page, then write approved
patches to `patches/seo/patch_manifest.json`.

This is the human review gate (D1) that unblocks `apply.py`. It replaces the stale
`requires_human_review` bottleneck by letting the maintainer quickly review and
approve proposed seoTitle, description, and tag changes.

## Pre-conditions

Before running this skill, verify:
1. `reports/seo/safe_recommendations.json` or `reports/reports/seo/safe_recommendations.json` exists
2. Pipeline has been run at least through `safety.py` (SEO-006)

```bash
# Check prerequisites
ls reports/seo/safe_recommendations.json 2>/dev/null || \
ls reports/reports/seo/safe_recommendations.json 2>/dev/null || \
echo "MISSING — run pipeline first"
```

## Steps

### 1. Locate inputs

```bash
# Find safe_recommendations.json
RECS_PATH=$(ls reports/seo/safe_recommendations.json 2>/dev/null || \
            ls reports/reports/seo/safe_recommendations.json 2>/dev/null)
echo "Using: $RECS_PATH"
```

### 2. Load and filter recommendations

Load `safe_recommendations.json`. Filter based on $ARGUMENTS:
- Default: include `opportunity_level` in {MEDIUM, HIGH}
- If `--level LOW`: include LOW only
- If `--level all`: include all levels
- If `--site <site>`: filter to that site (e.g. `products.aspose.org`)
- If `--family <family>`: filter to that product family
- If `--limit <N>`: review at most N pages this session

Skip pages where:
- `safety_checks_passed=False`
- All field recommendations have `proposed=null` (nothing to apply)

### 3. Present diffs interactively

For each page in the filtered set, display:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Page: content/products.aspose.org/en/3d/_index.md
Level: MEDIUM | Site: products.aspose.org | Family: 3d
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TAGS
  Current : []
  Proposed: ["aspose 3d converter", "aspose 3d conversion"]
  Rationale: Tag gap detected: 3 high-impression queries not in tags.

Decision? [a]pprove / [r]eject / [s]kip / [q]quit:
```

### 4. Collect decisions and write patch manifest

After review session, write approved patches to `patches/seo/patch_manifest.json`.

The manifest structure must follow this schema:
```json
{
  "batch_id": "<ISO-timestamp>",
  "generated_at": "<YYYY-MM-DD>",
  "reviewed_by": "human",
  "total_patches": N,
  "patches": [
    {
      "page_path": "content/...",
      "fields_to_update": {
        "seoTitle": "<value or null>",
        "description": "<value or null>",
        "tags_to_add": ["tag1", "tag2"]
      },
      "requires_human_review": false,
      "safety_checks_passed": true
    }
  ]
}
```

Only include `fields_to_update` entries where proposed value is non-null. Omit null fields.
Set `requires_human_review: false` for all approved patches (human has already reviewed).

### 5. Verify the manifest

```bash
python3 -c "
import json
m = json.load(open('patches/seo/patch_manifest.json'))
print(f'batch_id: {m[\"batch_id\"]}')
print(f'total_patches: {m[\"total_patches\"]}')
for p in m['patches'][:5]:
    fields = p['fields_to_update']
    tags = fields.get('tags_to_add', [])
    title = fields.get('seoTitle')
    print(f'  {p[\"page_path\"]} | tags={tags} | seoTitle={str(title)[:40]}')
"
```

### 6. Dry-run apply

Run `apply.py` in dry-run mode to preview what will change:

```bash
.venv/Scripts/python scripts/seo/pipeline/apply.py --dry-run
```

Confirm output shows expected frontmatter updates before proceeding.

### 7. Report session summary

After review, print:
- Total pages presented
- Approved count (with field breakdown)
- Rejected count
- Skipped count
- Patches written to manifest
- Next step: run `apply.py` to apply changes

## Safety constraints

- NEVER modify `evidence:`, `model_sha`, `claims`, `apis`, `formats` frontmatter
- NEVER approve seoTitle containing fabricated API names not in source keywords
- NEVER approve description > 160 chars or < 130 chars
- ONLY write to `patches/seo/patch_manifest.json` — do not modify content files directly
- If `model.yaml.stale_since != null` for the page's family/platform, flag and skip

## Evidence

After completion, confirm:
- `patches/seo/patch_manifest.json` exists and `total_patches > 0`
- All approved patches have `safety_checks_passed: true`
- No patches modify evidence blocks or body content
