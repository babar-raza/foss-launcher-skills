# S-58: New KB How-To — Generate KB How-To Article

Generate a new KB how-to article.

**Arguments:** `$ARGUMENTS`
**Expected format:** `{family} {platform} {slug}` — e.g. `3d python how-to-convert-fbx-to-gltf`

## Knowledge Pre-conditions

1. **Bootstrap knowledge**: Run `/knowledge-bootstrap {family} {platform}` and check status:
   - `KNOWLEDGE: STOP:partial` → halt; see printed message
   - `KNOWLEDGE: REFRESHED` → STOP: "Knowledge refreshed from upstream changes. Run `/knowledge-diff` to review what changed, then re-run this command."
   - `KNOWLEDGE: READY`, `KNOWLEDGE: BOOTSTRAPPED`, or `KNOWLEDGE: WARN:conflicts` → continue

2. **Load verified artifacts**:
   - Read `knowledge/{family}/{platform}/merged/claims.json`
   - Read `knowledge/{family}/{platform}/merged/api_surface.json`
   - Read `knowledge/{family}/{platform}/merged/api_surface.md` (human-readable; every class/method name used in content MUST appear here)
   - Read `knowledge/{family}/{platform}/merged/formats.json`
   - Read `forbidden_claims` from `knowledge/{family}/{platform}/merged/index.json`
   - Read `knowledge/{family}/{platform}/merged/snippets/` for verified code examples
   - Read `knowledge/{family}/{platform}/merged/limitations.md` (if the file exists — skip this step
     if absent) — **limitations cross-check**: for every format or capability claim in the how-to
     (e.g., "save as PDF", "export to OBJ"), verify it does not contradict a limitation marked as
     "not supported", "read-only", or "detect-only". Remove or correct contradicting claims before
     generating content.

## Steps

> **Skill context gate** — run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-58 --scope "*"
> ```


1. **Parse** `$ARGUMENTS` into: `family`, `platform`, `slug` (slug becomes the filename and title source).

   **Step 0a — Slug self-check (HALT guard):** After parsing the slug, extract the noun
   part (strip `how-to-{verb}-` prefix and `-{platform}` suffix). Check TWO conditions:

   **Condition 1 — CamelCase leak (C1):** If the noun is a **single word longer than
   12 characters** (e.g. "javascriptextensions", "logicalstructure"), HALT immediately:
   > "HALT: The slug noun `{noun}` appears to be an unsplit CamelCase namespace name.
   > This slug was likely generated from a C# namespace not registered in
   > `_FAMILY_SUBPKG_LABELS`. Do NOT proceed — fix the slug in site_planner.py first,
   > then re-run `/new-kb-howto`."

   **Condition 2 — Context-free compound (C4):** If the noun is hyphenated (compound
   noun) and **none of its words start with a product-family keyword** for `{family}`,
   HALT:
   > "HALT: The slug noun `{noun}` contains no `{family}`-specific keyword.
   > The slug is ambiguous without URL path context — it does not self-identify the
   > product. This was likely generated from a merged cluster label without a family
   > prefix. Fix the label in `_FAMILY_SUBPKG_LABELS['{family}']` first, then
   > re-run `/new-kb-howto`."
   >
   > Family keyword reference (from `_FAMILY_PRODUCT_KEYWORDS` in site_planner.py):
   > pdf → pdf, xmp, javascript, facades | cells → cell, xlsx, workbook, spreadsheet, excel |
   > slides → slide, presentation, pptx | words → word, docx, paragraph, doc |
   > email → email, mailbox, mime, smtp, eml, msg, attachment | 3d → 3d, mesh, scene, material |
   > font → font, glyph, ttf, woff

   Do not generate any content until both conditions are cleared.

2. **Read existing KB content for reference** (do not copy text — read only to confirm patterns):
   - Read one existing how-to file from `content/kb.aspose.org/en/{family}/{platform}/` to confirm exact frontmatter fields
   - Read `content/reference.aspose.org/en/{family}/{platform}/_index.md` to identify available classes, methods, and package names you may reference

3. **Generate frontmatter** using this exact structure (fill in placeholders):
   ```yaml
   ---
   title: {Human-readable title — convert slug hyphens to words, capitalise naturally}
   description: >
     {2 sentences: what the reader learns + which classes/methods are involved}
   date: '{today as YYYY-MM-DD}'
   lastmod: '{today as YYYY-MM-DD}'
   weight: 10
   draft: false
   type: topic
   keywords:
   - {action verb + noun + platform — e.g. "convert fbx to gltf python"}
   - {6–10 more SEO-oriented phrases, each on its own line}
   provenance:
     content_origin: skill-generated
     last_mechanism: skill
     auto_updatable: true
   ---
   ```

4. **Generate body** using this exact section order:
   - Opening paragraph: what the library does for this task; state the package manager used (resolved from `{platform}` below)
   - `## Step-by-Step Guide`
   - `{{% steps %}}`
   - `### Step 1: Install the Package` — install command (platform-resolved) + version check snippet
   - `### Step 2: Import Required Classes` — exact import statements matching the package used in existing content
   - `### Step 3–N:` — one step per logical task action, each with a prose explanation followed by a working code block (language resolved from `{platform}` below)
   - `{{% /steps %}}`
   - `## Common Issues and Fixes` — 3–5 bold-question + answer-paragraph pairs for likely errors
   - `## Frequently Asked Questions` — 3–5 `### Question?` + answer-paragraph pairs
   - `## See Also` — 3–5 links using absolute `https://` URLs without `/en/`:
     `[Article Title](https://kb.aspose.org/{family}/{platform}/slug/)`

5. **Constraints** (hard rules — never violate):
   - **Code fence language** — resolve from `{platform}` argument (never hardcode `python`):
     `python` → ` ```python `, `net` → ` ```csharp `, `java` → ` ```java `, `cpp` → ` ```cpp `,
     `typescript` → ` ```typescript `.
   - **Install instructions: never write `pip install {package-name}` / `dotnet add package
     {package-name}` / `npm install {package-name}` (or any package-manager identity) from
     LLM knowledge — always render it via a shortcode reading `data/package_registry.json`.**
     This is the same mandatory rule `new-products-page.md` (S-61) and `new-docs-page.md` (S-56)
     enforce (Mission MT015-2026-07-30-PACKAGE-REGISTRY, root cause 1: a generation step must
     never guess a live install command for an unconfirmed package):
     - **for `platform: java`**: in Step 1's install section, write exactly
       `{{< maven-coord "{family}" "java" >}}` on its own line (blank line before/after) instead
       of a fenced Maven XML block. For any inline mention of the coordinate elsewhere in the
       page, use `{{< maven-gav "{family}" "java" >}}` with NO surrounding backticks (it already
       emits its own `<code>` wrapper).
     - **for `platform: rust`**: use `{{< cargo-crate "{family}" "rust" >}}`.
     - **for every other platform** (net, cpp, python, typescript, javascript, go, ...): use
       `{{< package-install "{family}" "{platform}" >}}`.
     - **If `data/package_registry.json` has no entry at all for this family/platform**: do not
       invoke any of the above shortcodes (they will `errorf` the build) and do not write a
       specific command by hand either — write the plain-prose fallback ("A {registry} package
       has not been published yet — build from source until it ships") matching the wording
       already used for words/net.
     All of these shortcodes read `data/package_registry.json` at build time and fail the build
     loudly (`errorf`) if no entry exists — see Mission MT015 (unified schema) in
     `plans/master-plan.md`.
   - Shell/terminal commands always use ` ```bash `
   - Use `---` horizontal divider between each step inside `{{% steps %}}`
   - **Package name** for import statements/code blocks always comes from
     `knowledge/{family}/{platform}/scout/model.yaml` → `canonical_import`. Never use the
     commercial Aspose package name. This governs the **import package** only — it is a separate
     fact from the install-instruction identity above; do not conflate them.
   - **Python import paths — never infer from source-file location.** `class_import` /
     `canonical_namespace` in `api_surface.json` name where a class is DEFINED (used only for
     internal same-name disambiguation in `batch_reference.py`), not where it can be imported
     from — using them to build an import statement produced ~20 wrong-import pages across
     font/python (MT028-2026-08-09-FONT-PYTHON-BLIND-SPOT-HEAL, RC-font-python-01: e.g.
     `from aspose_font.loader import FontLoader` published everywhere instead of the real
     public `from aspose_font import FontLoader`). Check the class's own entry in
     `knowledge/{family}/{platform}/merged/api_surface.json` instead:
     - `exported_via_package_init: true` → genuinely public. Write
       `from {canonical_import}[.{public_import_module}] import {ClassName}` — omit the
       `.{public_import_module}` segment when it is `""` (re-exported at the package root);
       otherwise append it verbatim (e.g. `public_import_module: "cff"` →
       `from aspose_font.cff import CffCharset`, not `from aspose_font import CffCharset`,
       which raises `ImportError`).
     - absent/`false` → not part of the declared public surface. Only use it in an example if
       the source genuinely demonstrates it; write the real working (submodule) import path
       and mark it `# internal API — may change between releases` every time it appears —
       never list such a class as if it were stable public API without that disclaimer.
   - Class names, method names, and (for non-Python platforms, which have no
     `__init__.py`/`__all__` convention) import paths must exactly match what appears in the
     reference content you read — do not invent new API names
   - All cross-subdomain links must be absolute `https://` URLs without `/en/` (e.g. `https://docs.aspose.org/{family}/{platform}/...`)
   - All claims must be backed by entries in `knowledge/{family}/{platform}/merged/claims.json`

6. **Pre-write quality check**: Invoke `no-downgrade-guard` before writing:
   - Target path: `content/kb.aspose.org/en/{family}/{platform}/{slug}.md`
   - If BLOCK → do not write; report the blocking reason to the user
   - If WARN → present the warning to the user; await confirmation before writing
   - If ALLOW → proceed with write

7. **Write** the file to `content/kb.aspose.org/en/{family}/{platform}/{slug}.md`

7b. **Backlink injection**: After writing, ensure the `## See Also` section includes the
    reciprocal aspose.com backlink (idempotent — skips if already present):
    ```bash
    .venv/Scripts/python scripts/pipeline/commands/ops/backlink_backfill.py \n      --family {family} --platform {platform} --subdomain kb.aspose.org --write
    ```
    If BLOCKED_TARGET: log WARN and continue.
    **Anchor policy v2**: platform targets → `Aspose.{Family} for {Platform} Enterprise Product`; family targets → `Aspose.{Family} Enterprise Product Family` (governed by `docs/governance/positioning-policy.md`).

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-58 --status completed
> ```

## Knowledge Post-conditions

After generating the article:

1. **Attach evidence**: Run `python scripts/pipeline/commands/healing/attach_evidence.py --files content/kb.aspose.org/en/{family}/{platform}/{slug}.md`
   — this writes the `evidence:` YAML frontmatter block (`model_sha`, `claims`, `apis`).
2. **Run content check**: Execute `/content-check content/kb.aspose.org/en/{family}/{platform}/{slug}.md` to validate structure and knowledge alignment
3. **Run change guard**: Execute `/change-guard {family} {platform}` with any new claims to verify they don't contradict known facts
4. **Run audit**: `python scripts/pipeline/commands/content/audit.py --files content/kb.aspose.org/en/{family}/{platform}/{slug}.md`
   — must exit with 0 FAIL before committing.
5. **Run format eval**: `python -m scripts.pipeline.content_eval.cli evaluate {family} {platform} --evaluators format_truth,format_completeness --files content/kb.aspose.org/en/{family}/{platform}/{slug}.md --strict`
   — must exit 0 (no FAIL findings) before committing.

7. **Confirm** by printing the output file path and a short summary of steps covered.

---

## LLM Metrics Obligation

If this skill invokes `llm.professionalize.com` directly or through `LLMRouter`,
the run carries a **metrics obligation** (METRICS-PLAN-001, `AGENTS.md §15`):

- All professionalize calls must use `ProfessionalizeClient`, `LLMRouter`, or a
  registered adapter entry in `metrics_callsite_registry.yaml`.
- Each run must capture per-call `MetricsEvent` records and aggregate them into a
  validated `MetricsRow` via `RunMetrics`.
- Default mode is **dry-run**. Live posting requires explicit owner approval and
  `AGENT_METRICS_ENDPOINT` / `AGENT_METRICS_TOKEN` set locally.
- Non-professionalize calls (Gemini, Ollama, M2M) are excluded from
  `token_usage` and `api_calls_count`.
- Metrics failures must not crash or block the parent pipeline job.
