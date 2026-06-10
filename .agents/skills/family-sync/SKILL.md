---
name: family-sync
id: S-58
description: >
  Update the family-level _index.md on products.aspose.org so its description
  and overview accurately reflect all currently launched platforms. Reads
  knowledge from each platform and rewrites the three text fields.
args: "{family}"
---

# S-58: Family Sync — Update Family Page for All Launched Platforms

**Arguments**: $ARGUMENTS
Expected format: `{family}` — e.g. `email` or `3d`

## Purpose

Update the family-level `_index.md` at `$CONTENT_REPO_PATH/content/products.aspose.org/en/{family}/_index.md`
so its `head_description`, `description`, and `overview.content` fields accurately reflect
all currently launched platforms. Reads knowledge from each platform, computes shared
capabilities, and rewrites the three text fields to be platform-agnostic.

## Pre-conditions

1. Run `/knowledge-bootstrap {family} {platform}` for each platform in the family
2. Family page must exist at the target path with `layout: family`. If missing, create it manually.
3. At least one platform product page (`layout: plugin`) must exist for the family

## Steps

1. **Parse arguments**: Extract `{family}`.

2. **Discover launched platforms**: Find all `content/products.aspose.org/en/{family}/{platform}/_index.md`
   files with `layout: plugin`. These are the launched platforms.

3. **Load knowledge for each platform**:
   - Read `knowledge/{family}/{platform}/merged/claims.json`
   - Read `knowledge/{family}/{platform}/merged/model.yaml`
   - Extract `version`, `canonical_import`, `description` for each platform

4. **Compute shared capabilities**: Find claims with `confidence >= 0.8` present across ALL
   launched platforms. These become the family-level feature bullets.

5. **Build updated fields**:
   - `head_description`: Platform-agnostic 160-char SEO summary
   - `description`: 2-3 sentence overview covering all platforms
   - `overview.content`: 2-3 paragraphs covering shared capabilities

6. **Invoke no-downgrade-guard** (S-56): Check if existing family page has a higher quality grade.
   If BLOCK → do not write; report to user.

7. **Write** only the three fields (`head_description`, `description`, `overview.content`)
   in the family page frontmatter. Do NOT modify `layout`, `family_name`, `plugin_platform`,
   `content.block[]`, `single.block[]`, `faq.list[]`, or any platform-specific sections.

8. **Reattach evidence**:
   ```bash
   python scripts/pipeline/commands/content/attach_evidence.py \
     --files $CONTENT_REPO_PATH/content/products.aspose.org/en/{family}/_index.md
   ```

9. **Run audit**:
   ```bash
   python scripts/pipeline/commands/content/audit.py \
     --files $CONTENT_REPO_PATH/content/products.aspose.org/en/{family}/_index.md
   ```
   Must exit with 0 FAIL.

## Post-conditions

- Family page `head_description`, `description`, `overview.content` updated
- All platform-specific sections unchanged
- Evidence block updated; audit passes
