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
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/skill_context.py begin --skill S-58 --scope "*"
> ```


1. **Parse** `$ARGUMENTS` into: `family`, `platform`, `slug` (slug becomes the filename and title source).

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
     - `python` → ` ```python `, install via `pip install {package-name}`
     - `net` → ` ```csharp `, install via `dotnet add package {package-name}`
     - `java` → ` ```java `, install via Maven `<dependency>`
     - `cpp` → ` ```cpp `, install via CMake FetchContent or vcpkg (see install.md)
     - `typescript` → ` ```typescript `, install via `npm install {package-name}`
   - Shell/terminal commands always use ` ```bash `
   - Use `---` horizontal divider between each step inside `{{% steps %}}`
   - **Package name** always comes from `knowledge/{family}/{platform}/scout/model.yaml` → `canonical_import`. Never use the commercial Aspose package name.
   - Class names, method names, and import paths must exactly match what appears in the reference content you read — do not invent new API names
   - All cross-subdomain links must be absolute `https://` URLs without `/en/` (e.g. `https://docs.aspose.org/{family}/{platform}/...`)
   - All claims must be backed by entries in `knowledge/{family}/{platform}/merged/claims.json`

6. **Pre-write quality check**: Invoke `no-downgrade-guard` before writing:
   - Target path: `content/kb.aspose.org/en/{family}/{platform}/{slug}.md`
   - If BLOCK → do not write; report the blocking reason to the user
   - If WARN → present the warning to the user; await confirmation before writing
   - If ALLOW → proceed with write

7. **Write** the file to `content/kb.aspose.org/en/{family}/{platform}/{slug}.md`

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/skill_context.py end --skill S-58 --status completed
> ```

## Knowledge Post-conditions

After generating the article:

1. **Attach evidence**: Run `python scripts/pipeline/attach_evidence.py --files content/kb.aspose.org/en/{family}/{platform}/{slug}.md`
   — this writes the `evidence:` YAML frontmatter block (`model_sha`, `claims`, `apis`).
2. **Run content check**: Execute `/content-check content/kb.aspose.org/en/{family}/{platform}/{slug}.md` to validate structure and knowledge alignment
3. **Run change guard**: Execute `/change-guard {family} {platform}` with any new claims to verify they don't contradict known facts
4. **Run audit**: `python scripts/pipeline/audit.py --files content/kb.aspose.org/en/{family}/{platform}/{slug}.md`
   — must exit with 0 FAIL before committing.
5. **Run format eval**: `python -m scripts.pipeline.content_eval.cli evaluate {family} {platform} --evaluators format_truth,format_completeness --files content/kb.aspose.org/en/{family}/{platform}/{slug}.md --strict`
   — must exit 0 (no FAIL findings) before committing.

7. **Confirm** by printing the output file path and a short summary of steps covered.
