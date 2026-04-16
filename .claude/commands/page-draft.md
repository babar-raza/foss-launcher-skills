<!-- CONTRACT: agent-executed
     purpose: draft page content from a page plan with evidence-grounded prose and code
     preconditions: page plan from S-18 exists; knowledge artifacts loaded
     postcondition: page file written with frontmatter, evidence block, and knowledge-grounded content
     idempotent: no — LLM-generated content varies between invocations
     verified: 2026-04-11
-->
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

> **Skill context gate** — run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/skill_context.py begin --skill S-19 --scope "*"
> ```


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
   provenance:
     content_origin: skill-generated
     last_mechanism: skill
     auto_updatable: true
   ```

   **KB article**:
   ```yaml
   title: "{title}"
   description: "{description}"
   type: topic
   date: '{today}'
   lastmod: '{today}'
   keywords: [kw1, kw2, kw3, kw4, kw5]
   provenance:
     content_origin: skill-generated
     last_mechanism: skill
     auto_updatable: true
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
   provenance:
     content_origin: skill-generated
     last_mechanism: skill
     auto_updatable: true
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

7. **Pre-write quality check**: Invoke `no-downgrade-guard` before writing:
   - Target path: as specified in the plan (e.g., `content/docs.aspose.org/en/{family}/{platform}/{section}/{slug}.md`)
   - If BLOCK → do not write; report the blocking reason to the user
   - If WARN → present the warning to the user; await confirmation before writing
   - If ALLOW → proceed with write

8. **Write the draft** to the target path from the plan (e.g., `content/docs.aspose.org/en/{family}/{platform}/{section}/{slug}.md`).

9. **Run ground-check**: Execute `python scripts/pipeline/audit.py --files {target_path}` to verify API accuracy.

10. **Report**: Print summary of draft — word count, sections, claims used, API tokens verified.

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/skill_context.py end --skill S-19 --status completed
> ```

## Post-conditions
- Draft file is written to the correct content path
- All code blocks come from snippets (not fabricated)
- All API names in code are verified against `api_surface.json`
- Evidence frontmatter is present with claim IDs
- Ground-check (audit.py) returns PASS or lists specific issues to fix
- KB how-to pages include `{{% steps %}}` / `{{% /steps %}}` shortcodes

## Error Handling

| Error | Cause | Fix |
|-------|-------|-----|
| `Plan not found` | S-18 page-plan was not run | Run `/page-plan {family} {platform} {topic}` first |
| `Knowledge unavailable` | Knowledge not bootstrapped | Run `/knowledge-bootstrap {family} {platform}` |
| `{TODO: snippet needed}` in output | Referenced snippet missing from knowledge | Generate snippet via `/knowledge-enrich {family} {platform} --mode member-doc` |
| `audit.py FAIL: unknown token {name}` | API token in code block not in api_surface.json | Correct the token to match `api_surface.json`, or re-run `/repo-scout` if api_surface is stale |
| `change_guard BLOCK` | Path or content violates change guard | Check the blocking reason; may need human override token |
| Grade D or F after draft | Content failed critical evaluators | Run `/heal-page {path}` to auto-repair |
