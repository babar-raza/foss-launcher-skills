---
name: project-phase-store
id: S-10
description: >
  Record the project scope and planning context for a new page creation task.
  Stores intent, target audience, and knowledge state for downstream skills.
args: "{family} {platform} {site-type} {slug} \"{purpose}\""
---

# S-10: Project Phase Store — Record Page Creation Intent

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform} {site-type} {slug} "{purpose}"`
- `{site-type}`: one of `docs`, `blog`, `kb`, `reference`
- `{purpose}`: quoted string describing why this page is needed

Example: `3d python docs installation "Getting started guide for installing Aspose.3D for Python"`

> **Configuration**: Target content paths are defaults for the aspose.org repo. See `config.yaml` for your project's path configuration.

## Purpose
Record the project scope and planning context for a new page creation task. This ensures downstream skills (S-18 page-plan, S-19 page-draft) have consistent context about what to create and why.

## Pre-conditions
1. Knowledge model must exist: `knowledge/{family}/{platform}/merged/index.json`
2. Knowledge must not be stale

## Steps

1. **Parse arguments**: Extract family, platform, site-type, slug, and purpose from $ARGUMENTS

2. **Validate site-type**: Must be one of: `docs`, `blog`, `kb`, `reference`

3. **Verify knowledge exists**:
   - Read `knowledge/{family}/{platform}/merged/index.json`
   - If not found → STOP with "Knowledge model missing — run /repo-scout and /truth-merge first"
   - If `stale: true` → STOP with "Knowledge is stale — run /knowledge-update first"
   - Record `repo_sha` from model.yaml

4. **Determine target path** based on site-type:
   - `docs` → `content/docs.aspose.org/en/{family}/{platform}/` (section determined by S-18)
   - `blog` → `content/blog.aspose.org/{family}/{platform}/{slug}/index.md`
   - `kb` → `content/kb.aspose.org/en/{family}/{platform}/{slug}.md`
   - `reference` → `content/reference.aspose.org/en/{family}/{platform}/{slug}.md`

5. **Check target does not exist**: If the target file already exists:
   - STOP with "Target file already exists — use /page-update (S-20) to modify existing content"

6. **Write plan file** to `reports/plans/{family}-{platform}-{slug}.yaml`:
   ```yaml
   family: {family}
   platform: {platform}
   site_type: {site-type}
   slug: {slug}
   purpose: "{purpose}"
   knowledge_sha: {repo_sha}
   target_path: {determined path}
   created_at: {ISO-8601 timestamp}
   status: planned
   ```

## Output

```
PHASE STORE — {family}/{platform}
Site type: {site-type}
Slug:      {slug}
Purpose:   {purpose}
Target:    {target-path}
Knowledge: sha {repo_sha}
Status:    PLANNED

Plan file: reports/plans/{family}-{platform}-{slug}.yaml
Next step: Run /page-plan {family} {platform} {site-type} {slug}
```

## Error handling
- Invalid site-type → list valid options and abort
- Knowledge missing → instruct to run knowledge pipeline first
- Target exists → suggest S-20 page-update instead
