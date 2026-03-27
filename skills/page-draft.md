# S-19: Page Draft — Draft Page Content from a Page Plan

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform} {section} {slug}` — e.g. `3d python developer-guide rendering`

## Purpose
Draft page content by consuming the output of S-18 (page-plan). Generates content following section-specific templates. All code must reference the verified API surface — no fabricated API names or snippets.

## Pre-conditions
1. S-18 (page-plan) has been run for this page — a plan exists (either in prior conversation context or as a saved artifact)
2. **Knowledge bootstrap**: Run `/knowledge-bootstrap {family} {platform}` and check status:
   - `STOP:partial` → halt (see printed message)
   - `REFRESHED` → STOP: "Knowledge was refreshed from upstream changes. Run /knowledge-diff to review what changed before generating content, then re-run this command."
   - `READY`, `BOOTSTRAPPED`, or `WARN:conflicts` → continue
3. `knowledge/{family}/{platform}/merged/` must have `claims.json`, `api_surface.json` after bootstrap
4. `knowledge/{family}/{platform}/snippets/` contains the snippets referenced in the plan

## Steps

1. **Parse arguments**: Extract `{family}`, `{platform}`, `{section}`, and `{slug}` from $ARGUMENTS.

2. **Load the plan**: Retrieve the S-18 plan output for this page (from conversation context or `reports/plans/{family}/{platform}/{slug}.yaml`).

3. **Load knowledge artifacts**:
   - Read `knowledge/{family}/{platform}/merged/claims.json` for claim text
   - Read `knowledge/{family}/{platform}/merged/api_surface.json` for API verification
   - Read referenced snippets from `knowledge/{family}/{platform}/snippets/`
   - Read `knowledge/{family}/{platform}/merged/install.md` for install instructions (if getting-started page)

4. **Generate frontmatter** appropriate to the page type:

   **Docs page**:
   ```yaml
   title: "{title}"
   description: "{description from plan}"
   type: docs
   weight: {N}
   lastmod: '{today}'
   ```

   **KB article**:
   ```yaml
   title: "{title}"
   description: "{description}"
   type: topic
   date: '{today}'
   lastmod: '{today}'
   keywords: [kw1, kw2, kw3, kw4, kw5]
   ```

   **Blog post**:
   ```yaml
   title: "{title}"
   description: "{description}"
   author: Aspose
   date: '{today}'
   lastmod: '{today}'
   categories: ["{family}"]
   tags: ["{platform}", ...]
   ```

5. **Draft content section by section** following the plan's `structure` array:
   - For each section, write prose grounded in the listed claims
   - Insert code blocks from the referenced snippets — copy verbatim, do not modify
   - All code blocks must have a language identifier (```python, ```csharp, etc.)
   - Use hedging language for claims with confidence < 0.7 (e.g., "typically", "in most cases")
   - Do NOT fabricate method names, class names, or parameter names — only use what appears in `api_surface.json`
   - Include limitations from the plan where relevant

6. **Add evidence frontmatter** (placeholder — S-24 will finalize):
   ```yaml
   evidence:
     model_sha: "{repo_sha from model.yaml}"
     model_version: "{version}"
     claims: [CLM-xxx, CLM-yyy, ...]
     apis: [Class.method, ...]
     formats: []
   ```

7. **Write the draft** to the target path from the plan (e.g., `content/docs.aspose.org/en/{family}/{platform}/{section}/{slug}.md`).

8. **Run ground-check**: Execute `python scripts/pipeline/audit.py --files {target_path}` to verify API accuracy.

9. **Report**: Print summary of draft — word count, sections, claims used, API tokens verified.

## Post-conditions
- Draft file is written to the correct content path
- All code blocks come from snippets (not fabricated)
- All API names in code are verified against `api_surface.json`
- Evidence frontmatter is present with claim IDs
- Ground-check (audit.py) returns PASS or lists specific issues to fix
- KB how-to pages include `{{% steps %}}` / `{{% /steps %}}` shortcodes

## Error handling
- If a referenced snippet is missing, leave a `{TODO: snippet needed}` placeholder and WARN
- If audit.py returns FAIL, list each failing token and attempt correction from api_surface.json
- If plan is not available, instruct user to run S-18 first
