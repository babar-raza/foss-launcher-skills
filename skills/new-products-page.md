<!-- CONTRACT: agent-executed
     purpose: generate products.aspose.org landing page with YAML-heavy plugin layout
     preconditions: knowledge model bootstrapped; claims.json + snippets available
     postcondition: products page with feature table, code examples, FAQ, and evidence attached
     idempotent: no — LLM-generated feature descriptions and code selection vary
     verified: 2026-04-11
-->
# S-61: New Products Page — Generate products.aspose.org Landing Page

**Arguments**: $ARGUMENTS
**Expected format**: `{family} {platform}` — e.g. `3d java` or `slides python`

## Purpose

Generate or update the products.aspose.org landing page for a FOSS product. Products pages use
`layout: plugin` YAML-heavy structure and serve as the primary developer discovery entry point.

## Knowledge Pre-conditions

1. **Bootstrap knowledge**: Run `/knowledge-bootstrap {family} {platform}` and check status:
   - `KNOWLEDGE: STOP:partial` → halt (see printed message)
   - `KNOWLEDGE: REFRESHED` → STOP: "Knowledge was refreshed from upstream changes. Run
     `/knowledge-diff` to review what changed before generating content, then re-run this command."
   - `KNOWLEDGE: READY`, `KNOWLEDGE: BOOTSTRAPPED`, or `KNOWLEDGE: WARN:conflicts` → continue

2. **Load verified artifacts**:
   - Read `knowledge/{family}/{platform}/merged/claims.json`
   - Read `knowledge/{family}/{platform}/merged/api_surface.md` (human-readable; feature bullets must use only members present here)
   - Read `knowledge/{family}/{platform}/merged/formats.json` (for code examples and format support)
   - Read `knowledge/{family}/{platform}/merged/limitations.md` (for honest capability statements)
   - Read `forbidden_claims` from `knowledge/{family}/{platform}/merged/index.json`
   - Read `knowledge/{family}/{platform}/scout/model.yaml` for:
     - `canonical_import` (package name — never use commercial Aspose package name)
     - `version`, `license`, `runtime_requirement`, `install_command`
   - Read `knowledge/{family}/{platform}/merged/snippets/` for verified code examples
     (ALL code in `single.block` MUST come from snippets/ — do NOT generate code from scratch)

3. **Read FAQ source** (if available):
   - Read `content/kb.aspose.org/en/{family}/{platform}/faq.md` for `faq.list[]` pairs
   - Do not invent FAQ questions — use only questions from the KB file

## Steps

> **Skill context gate** — run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-61 --scope "*"
> ```


1. **Parse arguments**: Extract `{family}` and `{platform}` from $ARGUMENTS.

2. **Check if existing platform product page exists**:
   - Read `content/products.aspose.org/en/{family}/{platform}/_index.md` if it exists (read only)
   - Note: The platform product page (`layout: plugin`) lives at `{family}/{platform}/_index.md`.
     The family landing page (`layout: family`) at `{family}/_index.md` is managed by `/family-sync`
     — **do not read or write the family page from this skill**.
   - Invoke **no-downgrade-guard** before writing (see Step 8)

3. **Resolve product metadata** from `scout/model.yaml`:
   - `plugin_name` = "{ProductName} FOSS for {Platform display name}"
   - `install_command` from model.yaml (never from LLM knowledge)
   - `canonical_import` for package name in code blocks

4. **Build `plugin_description`**: 1-sentence summary from claims with `kind: "identity"` and
   highest confidence. Must not exceed 160 characters.

5. **Build `overview` section**:
   - `title`: "{ProductName} FOSS — Open Source {Platform} Library"
   - `content`: 2-3 paragraphs from high-confidence claims (confidence >= 0.8)
     - Paragraph 1: what the library is and who it is for
     - Paragraph 2: key capabilities (only claims that appear in api_surface.md)
     - Paragraph 3: licensing (MIT), install method, zero-dependency nature

6. **Build `content.block[]`** — 4-6 feature blocks, each with:
   - `title_left`: Feature name (from claims with `kind: "capability"`)
   - `content_left`: 3-5 bullet points — every class/method name MUST exist in api_surface.md
   - `title_right`: Use cases / who uses this feature
   - `content_right`: 3-4 bullet points (practical real-world scenarios)
   - **Hard constraint**: Never reference capabilities in `limitations.md` as working

7. **Build `single.block[]`** — 3-4 code example blocks, each with:
   - `title`: Short description (e.g. "Load and Save 3D Scene")
   - `content`: Brief prose intro (1 sentence) + fenced code block
   - **Code must come from `knowledge/{family}/{platform}/merged/snippets/`** — do NOT generate
     code from scratch. If no matching snippet exists, omit that block rather than fabricating.
   - Code fence language resolved from `{platform}`:
     - `python` → `python`, `net` → `csharp`, `java` → `java`, `cpp` → `cpp`, `typescript` → `typescript`

8. **Build `faq.list[]`** — 4-6 Q&A pairs:
   - Source from `content/kb.aspose.org/en/{family}/{platform}/faq.md`
   - Do not invent questions — omit `faq` block entirely if KB FAQ does not exist

9. **Invoke no-downgrade-guard**: Before writing, check if existing page has a higher quality grade.
   If BLOCK → do not write; report to user.

10. **Write** to `content/products.aspose.org/en/{family}/{platform}/_index.md`.
    ALL content sections MUST be inside the YAML frontmatter (between `---` delimiters).
    The Hugo `plugin.html` template reads sections via `.Params.overview`, `.Params.content`,
    `.Params.single`, `.Params.faq` — these are ONLY populated from frontmatter, NOT from
    the page body. **The page body after the closing `---` MUST be empty.**

    Use this frontmatter structure (reference pages: slides/net, email/net, cells/python):
    ```yaml
    ---
    layout: plugin
    family_name: "{ProductName} FOSS"
    plugin_description: "{1-sentence, max 160 chars}"
    plugin_platform: "{platform display name per §3b; see [docs/governance/naming-conventions.md](../docs/governance/naming-conventions.md)}"
    head_title: "{ProductName} FOSS for {Platform} | Open-Source {Category} Library"
    head_description: "{SEO description, max 160 chars}"
    title: "{ProductName} FOSS for {Platform display name}"
    description: >
      {plugin_description}
    submenu:
      enable: true
    github_url: "{repo URL from scout/model.yaml repo_url}"
    overview:
      enable: true
      title: "..."
      content: |
        {overview paragraphs}
    content:
      enable: true
      block:
      - title_left: "..."
        content_left: |
          {bullet points}
        title_right: "..."
        content_right: |
          {bullet points}
    single:
      enable: true
      block:
      - title: "..."
        content: |
          {prose + fenced code block}
    faq:
      enable: true
      list:
      - question: "..."
        answer: "..."
    supportandlearning:
      enable: true
    more_formats:
      enable: true
    back_to_top:
      enable: true
    provenance:
      content_origin: skill-generated
      last_mechanism: skill
      auto_updatable: true
    evidence:
      model_sha: ""
      model_version: ""
      claims: []
      apis: []
    ---
    ```
    If no KB FAQ exists, set `faq: enable: false` (omit the `list` key).
    **Do NOT write to `{family}/_index.md`** — that is the family landing page managed by `/family-sync`.

11. **Structural completion**: Run the deterministic skeleton filler to ensure all
    display-control boilerplate sections are present regardless of LLM output variance:
    `.venv/Scripts/python scripts/pipeline/commands/migration/complete_plugin_structure.py --files content/products.aspose.org/en/{family}/{platform}/_index.md`
    This inserts `supportandlearning`, `more_formats`, and `back_to_top` sections if the
    LLM omitted them. It is idempotent and does not modify LLM-generated content sections.

12. **Attach evidence**: `.venv/Scripts/python scripts/pipeline/commands/healing/attach_evidence.py --files content/products.aspose.org/en/{family}/{platform}/_index.md`

13. **Run structural validator**: `.venv/Scripts/python scripts/pipeline/commands/content/validate_plugin_structure.py --files content/products.aspose.org/en/{family}/{platform}/_index.md`
    — must exit 0 (no FATAL or ERROR findings). This catches body-content-leak, missing frontmatter keys,
    and missing display-control sections on English pages.

14. **Run audit**: `.venv/Scripts/python scripts/pipeline/commands/content/audit.py --files content/products.aspose.org/en/{family}/{platform}/_index.md`
    — must exit with 0 FAIL before committing.

15. **Run full evaluation**: `.venv/Scripts/python -m scripts.pipeline.content_eval evaluate --files content/products.aspose.org/en/{family}/{platform}/_index.md --format json --remediation`
    — runs 22 evaluators (api_accuracy, content_substance, page_role, prose_truth, risk_language, evidence_depth, code_plausibility, etc.).
    If grade < B, review FAIL findings and fix before committing. Update `graded_evaluators` to `full` in frontmatter.

16. **Run smoke test** (Python platform only): `.venv/Scripts/python scripts/pipeline/commands/diagnostics/smoke_test.py --files content/products.aspose.org/en/{family}/{platform}/_index.md`
    — must exit 0. All code blocks must compile cleanly.

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-61 --status completed
> ```

## Hard Constraints

- Every class/method name in feature bullets must exist in `api_surface.md`
- No format claims unless they appear in `formats.json` with confirmed support
- No limitation denials — if `limitations.md` lists a method as unimplemented, do not claim it works
- `install_command` comes from `scout/model.yaml`, NOT from LLM knowledge
- `canonical_import` must not contain the commercial Aspose package name
- All code in `single.block` comes from verified `snippets/` — no fabrication

## Post-conditions

- Platform product page exists at `content/products.aspose.org/en/{family}/{platform}/_index.md`
- `layout: plugin` present in frontmatter
- `family_name`, `plugin_platform`, `plugin_description` fields populated in frontmatter
- `head_title` and `head_description` present in frontmatter
- `submenu: enable: true` present in frontmatter
- `github_url` present in frontmatter
- `overview`, `content`, `single` sections present in frontmatter with `enable: true`
- `supportandlearning: enable: true` and `back_to_top: enable: true` present
- **Page body (after closing `---`) is empty** — all content is in frontmatter
- `evidence:` frontmatter block populated by `attach_evidence.py`
- `validate_plugin_structure.py` exits with 0 (no FATAL/ERROR)
- `audit.py` exits with 0 FAIL
- `content_eval` grade is B or above; `graded_evaluators: full` in frontmatter
- Smoke test passes (Python platform) — all code blocks compile
- No forbidden claims present
- Family page at `content/products.aspose.org/en/{family}/_index.md` is **NOT modified** by this skill
