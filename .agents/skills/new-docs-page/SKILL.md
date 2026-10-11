<!-- CONTRACT: agent-executed
     purpose: generate a documentation page for docs.aspose.org with evidence provenance
     preconditions: knowledge model bootstrapped; claims.json + api_surface.json available
     postcondition: new page at docs.aspose.org path with frontmatter, evidence, and audit pass
     idempotent: no — LLM-generated content varies between invocations
     verified: 2026-04-11
-->
# S-56: New Docs Page — Generate Documentation Page for docs.aspose.org

Generate a new documentation page for docs.aspose.org.

**Arguments:** `$ARGUMENTS`
**Expected format:** `{family} {platform} {section} {slug}` — e.g. `3d python developer-guide mesh-operations`
Valid sections: `getting-started` | `developer-guide`

## Knowledge Pre-conditions

Before generating any content, you MUST:

1. **Bootstrap knowledge**: Run `/knowledge-bootstrap {family} {platform}` and check status:
   - `KNOWLEDGE: STOP:partial` → halt (see printed message)
   - `KNOWLEDGE: REFRESHED` → STOP: "Knowledge was refreshed from upstream changes. Run
     `/knowledge-diff` to review what changed before generating content, then re-run this command."
   - `KNOWLEDGE: READY`, `KNOWLEDGE: BOOTSTRAPPED`, or `KNOWLEDGE: WARN:conflicts` → continue

2. **Load verified artifacts**:
   - Read `knowledge/{family}/{platform}/merged/claims.json`
   - Read `knowledge/{family}/{platform}/merged/api_surface.json`
   - Read `knowledge/{family}/{platform}/merged/api_surface.md` — the human-readable API reference.
     Every class name, method, property, and enum value in your generated content MUST appear in
     this file. If a name is not in api_surface.md, do not use it.
   - Read `knowledge/{family}/{platform}/merged/formats.json` — only reference formats confirmed here
   - Read `forbidden_claims` from `knowledge/{family}/{platform}/merged/index.json` — never include these
   - Check `knowledge/{family}/{platform}/merged/snippets/` for verified code examples

## Steps

> **Skill context gate** — run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-56 --scope "*"
> ```


1. **Parse** `$ARGUMENTS` into: `family`, `platform`, `section`, `slug`.

2. **Read existing docs for reference** (read only — do not copy text):
   - List files in `content/docs.aspose.org/en/{family}/{platform}/{section}/` to see what already exists
   - Read the `_index.md` for that section to understand the section's scope and tone
   - Read `content/reference.aspose.org/en/{family}/{platform}/_index.md` for available API classes and methods

3. **Determine the next `weight`** by reading existing pages in the section and using the next available multiple of 10 (e.g. if highest existing weight is 20, use 30).

4. **Generate frontmatter**:
   ```yaml
   ---
   page_role: howto_article
   title: {Human-readable title from slug}
   description: >-
     {1–2 sentences: what the reader learns and which classes/methods are covered}
   weight: {next weight}
   type: docs
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

5. **Generate body** — structure differs by section:

   ### For `getting-started` pages:
   - `## {Title}`
   - Opening paragraph: one-sentence purpose statement
   - `---`
   - `### Prerequisites` — markdown table: Requirement | Detail rows (runtime/compiler version, OS, system packages — resolved from `{platform}`)
   - `---`
   - Numbered steps for the task (install, configure, verify)
   - Each step: prose explanation + code block (bash or platform-resolved language)
   - `---`
   - `### Next Steps` — 3–5 links to related getting-started or developer-guide pages using `[Title](../slug/)`

   ### For `developer-guide` pages:
   - `## {Title}`
   - Opening paragraph: what feature/capability this covers and which class is the entry point
   - `---`
   - `### {Feature subsection}` blocks — one per major capability or concept, each with:
     - 1–2 prose sentences
     - Working code block (language resolved from `{platform}` — see Constraints below)
   - `---`
   - `### Tips and Best Practices` — 3–5 bullet points
   - `---`
   - `### Common Issues` — markdown table: Issue | Cause | Fix
   - `---`
   - `### FAQ` — 3–5 `#### Question?` + answer pairs
   - `---`
   - `### API Reference Summary` — markdown table: Class/Method | Description, limited to what you confirmed exists in reference content

6. **Constraints**:
   - **Code fence language** — resolve from `{platform}` argument (never hardcode `python`):
     - `python` → ` ```python `
     - `net` → ` ```csharp `
     - `java` → ` ```java `
     - `cpp` → ` ```cpp `
     - `typescript` → ` ```typescript `
   - **Install instructions in any generated section — never a literal command, never from
     LLM knowledge.** Same mandatory rule as new-products-page (S-61), root cause 1 (Mission
     MT015-2026-07-30-PACKAGE-REGISTRY: a generation step must never guess a live install
     command for an unconfirmed package — this exact defect class already shipped once,
     3D-NET-REFRESH-002's wrong NuGet command across 19 files):
     - `java` → `{{< maven-coord "{family}" "java" >}}` on its own line (blank line before/after)
       instead of a fenced Maven XML block; `{{< maven-gav "{family}" "java" >}}` (no surrounding
       backticks) for inline mentions.
     - `rust` → `{{< cargo-crate "{family}" "rust" >}}`.
     - every other platform (`net`, `cpp`, `python`, `typescript`, `javascript`, `go`, ...) →
       `{{< package-install "{family}" "{platform}" >}}` on its own line for a block-level
       mention; `{{< package-install-inline "{family}" "{platform}" >}}` (no surrounding
       backticks) for inline mid-sentence mentions.
     - If `data/package_registry.json` has no entry for this family/platform, STOP — do not
       invoke any shortcode (it will `errorf`) and do not hand-write install prose of any vintage
       (neither a guessed command nor a "not yet published" fallback sentence). Add a
       `data/package_registry.json` entry first (even a `published: false` one — 14 real products
       already ship pages this way), then the shortcode renders correctly automatically. See
       `registry_backfill.py` / TC-MT015-07's `naming_convention_candidate()`.
     All of these read `data/package_registry.json` at build time and fail the build loudly if no
     entry exists — see Mission MT008 (Java/Maven) and Mission MT015 (unified schema + the other
     platforms) in `plans/master-plan.md`.
   - Shell/terminal commands always use ` ```bash `
   - `---` divider between every major section
   - **Package name** for import statements/code blocks always comes from
     `knowledge/{family}/{platform}/scout/model.yaml` → `canonical_import`. Never use the
     commercial Aspose package name. This is a separate fact from the Java Maven groupId above
     — do not conflate them.
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
       never list such a class in the API Reference Summary table without that disclaimer.
   - Class names and method names must exactly match what you read from reference content —
     no invented API. For non-Python platforms (no `__init__.py`/`__all__` convention), the
     same holds for import/namespace paths too.
   - **Internal links within docs.aspose.org**: use relative paths (`../slug/`)
   - **Cross-subdomain links** (to kb, blog, reference): use absolute `https://` URLs without `/en/` — e.g. `https://kb.aspose.org/{family}/{platform}/slug/`
   - Do not add a `sidebar:` key unless the section `_index.md` uses it

7. **Pre-write quality check**: Invoke `no-downgrade-guard` before writing:
   - Target path: `content/docs.aspose.org/en/{family}/{platform}/{section}/{slug}.md`
   - If BLOCK → do not write; report the blocking reason to the user
   - If WARN → present the warning to the user; await confirmation before writing
   - If ALLOW → proceed with write

8. **Write** to `content/docs.aspose.org/en/{family}/{platform}/{section}/{slug}.md`

8b. **Backlink injection**: After writing, inject the reciprocal aspose.com backlink as a
    `## See Also` section (idempotent — skips if already present):
    ```bash
    .venv/Scripts/python scripts/pipeline/commands/ops/backlink_backfill.py \n      --family {family} --platform {platform} --subdomain docs.aspose.org --write
    ```
    If BLOCKED_TARGET: log WARN and continue.
    **Anchor policy v2**: platform targets → `Aspose.{Family} for {Platform} Enterprise Product`; family targets → `Aspose.{Family} Enterprise Product Family` (governed by `docs/governance/positioning-policy.md`).

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-56 --status completed
> ```

## Knowledge Post-conditions

After generating the page:

1. **Attach evidence**: Run `python scripts/pipeline/commands/healing/attach_evidence.py --files content/docs.aspose.org/en/{family}/{platform}/{section}/{slug}.md`
   — this writes the `evidence:` YAML frontmatter block (`model_sha`, `claims`, `apis`).
2. **Run content check**: Execute `/content-check content/docs.aspose.org/en/{family}/{platform}/{section}/{slug}.md` to validate structure and knowledge alignment
3. **Run change guard**: Execute `/change-guard {family} {platform}` with any new claims to verify they don't contradict known facts
4. **Run audit**: `python scripts/pipeline/commands/content/audit.py --files content/docs.aspose.org/en/{family}/{platform}/{section}/{slug}.md`
   — must exit with 0 FAIL before committing.

8. **Confirm** with the output path and a list of the H2 sections written.

## Error Handling

| Error | Cause | Fix |
|-------|-------|-----|
| `Knowledge unavailable` | Knowledge not bootstrapped | Run `/knowledge-bootstrap {family} {platform}` |
| `api_surface.json not found` | Scout extraction not run | Run `/repo-scout {family} {platform}` |
| `change_guard BLOCK` | Content violates change guard rules | Check blocking reason; may need override token or content revision |
| `audit.py FAIL: unknown token` | Fabricated API name in code block | Correct token to match `api_surface.json` entries |
| Page already exists at target path | Duplicate page generation | Use `/page-update` to modify existing pages instead |
| Grade D/F after generation | Content failed critical evaluators | Run `/heal-page {path}` to auto-repair |

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
