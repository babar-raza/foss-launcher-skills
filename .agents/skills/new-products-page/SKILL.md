---
name: new-products-page
description: >
  Generate products.aspose.org landing page for a FOSS product
argument-hint: "{family} [platform] [--layout family|plugin]"
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# New Products Page — Generate products.aspose.org Landing Page

**Arguments**: $ARGUMENTS
**Expected format**: `{family} [platform] [--layout family|plugin]` — e.g. `3d python` or `3d python --layout plugin` or `3d --layout family`

## Purpose

Generate or update a products.aspose.org landing page for a FOSS product. Two layout modes are
supported:

- **family** (`--layout family`): generates the family-level `_index.md` at
  `content/products.aspose.org/en/{family}/_index.md`
- **plugin** (`--layout plugin`): generates the platform-level `_index.md` at
  `content/products.aspose.org/en/{family}/{platform}/_index.md`

Products pages are YAML-heavy and serve as the primary developer discovery entry point.

## Step 1: Determine Layout Mode

Parse $ARGUMENTS to determine which layout mode to use:

- If only `{family}` is provided, or `--layout family` is explicit → **family mode**
  - Target path: `content/products.aspose.org/en/{family}/_index.md`
  - No `{platform}` required
- If `{family} {platform}` is provided, or `--layout plugin` is explicit → **plugin mode**
  - Target path: `content/products.aspose.org/en/{family}/{platform}/_index.md`
  - `{platform}` is required; halt with an error if missing

**Default**: if both `{family}` and `{platform}` are given without an explicit `--layout` flag,
default to **plugin mode**.

## Step 2: Plan-Check Gate

Run the code-enforced plan gate:
```bash
python scripts/pipeline/plan_check.py {family} {platform} products {slug} [--bypass]
```
Where `{slug}` is `_index` for family mode or `{platform}/_index` for plugin mode.
- Exit 0 → proceed normally.
- Exit 1 → print warning and continue (products plan check is advisory, not blocking).

## Knowledge Pre-conditions

1. **Bootstrap knowledge**: Run `/knowledge-bootstrap {family} {platform}` (plugin mode) or
   `/knowledge-bootstrap {family}` (family mode) and check status:
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
     - `github_url` or `repo_url` (used as `github_url` frontmatter field)
   - Read `knowledge/{family}/{platform}/merged/snippets/` for verified code examples
     (ALL code in `single.block` MUST come from snippets/ — do NOT generate code from scratch)

3. **Read FAQ source** (if available):
   - Read `content/kb.aspose.org/en/{family}/{platform}/faq.md` for `faq.list[]` pairs
   - Do not invent FAQ questions — use only questions from the KB file

## Steps (Family Mode)

### F-1. Resolve product metadata from `scout/model.yaml`

- `plugin_name` = "{ProductName} FOSS"
- `install_command` from model.yaml (never from LLM knowledge)
- `canonical_import` for package name in code blocks

### F-2. Build `plugin_description`

1-sentence summary from claims with `kind: "identity"` and highest confidence. Must not exceed
160 characters.

### F-3. Build `overview` section

- `title`: "{ProductName} FOSS — Open Source Library"
- `content`: 2-3 paragraphs from high-confidence claims (confidence >= 0.8)
  - Paragraph 1: what the library family is and who it is for
  - Paragraph 2: platforms and key capabilities (only claims that appear in api_surface.md)
  - Paragraph 3: licensing (MIT), install method, zero-dependency nature

### F-4. Build `content.block[]` — 4-6 feature blocks, each with

- `title_left`: Feature name (from claims with `kind: "capability"`)
- `content_left`: 3-5 bullet points — every class/method name MUST exist in api_surface.md
- `title_right`: Use cases / who uses this feature
- `content_right`: 3-4 bullet points (practical real-world scenarios)
- **Hard constraint**: Never reference capabilities in `limitations.md` as working

### F-5. Build `single.block[]` — 3-4 code example blocks, each with

- `title`: Short description (e.g. "Load and Save 3D Scene")
- `content`: Brief prose intro (1 sentence) + fenced code block
- **Code must come from `knowledge/{family}/{platform}/merged/snippets/`** — do NOT generate
  code from scratch. If no matching snippet exists, omit that block rather than fabricating.

### F-6. Build `faq.list[]` — 4-6 Q&A pairs

- Source from `content/kb.aspose.org/en/{family}/{platform}/faq.md`
- Do not invent questions — omit `faq` block entirely if KB FAQ does not exist

### F-7. Invoke no-downgrade-guard

Before writing, check if existing page has a higher quality grade. If BLOCK → do not write;
report to user.

### F-8. Write to `content/products.aspose.org/en/{family}/_index.md`

Use this frontmatter structure:

```yaml
---
title: "{ProductName} FOSS"
description: >
  {plugin_description}
layout: family
plugin_name: "{plugin_name}"
plugin_description: "{plugin_description}"
evidence:
  model_sha: ""
  model_version: ""
  claims: []
  apis: []
---
```

Followed by the overview, content.block, single.block, and faq.list YAML sections in the body.

### F-9. Attach evidence

`python scripts/pipeline/attach_evidence.py --files content/products.aspose.org/en/{family}/_index.md`

### F-10. Run audit

`python scripts/pipeline/audit.py --files content/products.aspose.org/en/{family}/_index.md`
— must exit with 0 FAIL before committing.

---

## Steps (Plugin Mode)

Plugin mode generates a platform-level page at
`content/products.aspose.org/en/{family}/{platform}/_index.md`.

### P-1. Resolve product metadata from `scout/model.yaml`

- `plugin_name` = "{ProductName} FOSS" (without platform suffix in the field itself)
- `plugin_platform` = display name for `{platform}` (e.g. `python` → `Python`, `net` → `.NET`,
  `java` → `Java`, `cpp` → `C++`, `typescript` → `TypeScript`)
- `install_command` from model.yaml (never from LLM knowledge)
- `canonical_import` for package name in code blocks
- `github_url`: use `github_url` field from model.yaml; fall back to `repo_url` from
  `knowledge/{family}/{platform}/merged/index.json` if not present in model.yaml

### P-2. Build `plugin_description`

1-sentence summary from claims with `kind: "identity"` and highest confidence. Must not exceed
160 characters. Pull from the first identity claim in `claims.json` sorted by confidence
descending.

### P-3. Build `overview` section

- `title`: "Open-Source {plugin_platform} Library for {ProductName} Processing"
- `content`: 2-3 paragraphs from high-confidence claims (confidence >= 0.8)
  - Paragraph 1: what the library is and who it is for
  - Paragraph 2: key capabilities (only claims that appear in api_surface.md); include format
    names from formats.json where relevant
  - Paragraph 3: licensing (MIT), install method, zero-dependency / runtime requirement

### P-4. Build `content.block[]` — 4-6 feature blocks, each with

- `title_left`: Feature name (from claims with `kind: "capability"`)
- `content_left`: 3-5 bullet points — every class/method name MUST exist in api_surface.md
- `title_right`: Use cases / who uses this feature
- `content_right`: 3-4 bullet points (practical real-world scenarios)
- **Hard constraint**: Never reference capabilities in `limitations.md` as working

### P-5. Build `single.block[]` — 3-4 code example blocks, each with

- `title`: Short description (e.g. "Load and Save 3D Scene")
- `content`: Brief prose intro (1 sentence) + fenced code block. Include an install snippet
  (e.g. `pip install …`) before the first code block when the platform supports it.
- **Code must come from `knowledge/{family}/{platform}/merged/snippets/`** — do NOT generate
  code from scratch. If no matching snippet exists, omit that block rather than fabricating.
- Code fence language resolved from `{platform}`:
  - `python` → `python`, `net` → `csharp`, `java` → `java`, `cpp` → `cpp`, `typescript` → `typescript`

### P-6. Build `faq.list[]` — 4-6 Q&A pairs

- Source from `content/kb.aspose.org/en/{family}/{platform}/faq.md`
- Do not invent questions — omit `faq` block entirely if KB FAQ does not exist

### P-7. Invoke no-downgrade-guard

Before writing, check if existing page has a higher quality grade. If BLOCK → do not write;
report to user.

### P-8. Write to `content/products.aspose.org/en/{family}/{platform}/_index.md`

Use this frontmatter structure (based on real platform-level pages):

```yaml
---
layout: plugin
plugin_name: "{ProductName} FOSS"
plugin_description: "{plugin_description}"
plugin_platform: "{plugin_platform display name}"
head_title: "{ProductName} FOSS for {plugin_platform} | Open-Source {domain} Library"
head_description: "{plugin_description} Install with {install_command_short}."
title: "{ProductName} FOSS for {plugin_platform}"
description: >
  {one-line action summary — what you can do, free and open-source}
submenu:
  enable: true
github_url: "{github_url from model.yaml or index.json}"
overview:
  enable: true
  title: "Open-Source {plugin_platform} Library for {domain} Processing"
  content: |
    {3 paragraphs from P-3}
content:
  enable: true
  block:
  - title_left: "{feature name}"
    content_left: |
      {bullet list — only api_surface.md members}
    title_right: "{use-case heading}"
    content_right: |
      {bullet list or prose — real-world scenarios}
  # repeat for each feature block (4–6 total)
single:
  enable: true
  block:
  - title: "{short example title}"
    content: |
      {1-sentence prose intro}

      ```{lang}
      {snippet from snippets/}
      ```
  # repeat for each code block (3–4 total)
faq:
  enable: true
  list:
  - question: "{question from KB faq.md}"
    answer: "{answer from KB faq.md}"
  # repeat (4–6 total); omit entire faq block if KB faq.md does not exist
limitations:
  enable: true
  title: "Not Included in This Library"
  content: |
    {bullet list of known limitations from limitations.md — e.g. unsupported formats,
     missing protocol support, platform restrictions. If limitations.md is empty, include
     at minimum the runtime requirement from model.yaml (e.g. "Requires .NET 8.0+").}
supportandlearning:
  enable: true
more_formats:
  enable: true
back_to_top:
  enable: true
evidence:
  model_sha: ""
  model_version: ""
  claims: []
  apis: []
---
```

### P-9. Attach evidence

`python scripts/pipeline/attach_evidence.py --files content/products.aspose.org/en/{family}/{platform}/_index.md`

### P-10. Run audit

`python scripts/pipeline/audit.py --files content/products.aspose.org/en/{family}/{platform}/_index.md`
— must exit with 0 FAIL before committing.

---

## Hard Constraints (Both Modes)

- Every class/method name in feature bullets must exist in `api_surface.md`
- No format claims unless they appear in `formats.json` with confirmed support
- No limitation denials — if `limitations.md` lists a method as unimplemented, do not claim it works
- **Limitations disclosure required** (R-F): the `limitations` block MUST be present in the output.
  If `limitations.md` exists and is non-empty, populate from it. If empty, include at minimum the
  runtime/platform requirement from `model.yaml`. A products page without a limitations section is
  incomplete and will fail the completeness gate.
- `install_command` comes from `scout/model.yaml`, NOT from LLM knowledge
- `canonical_import` must not contain the commercial Aspose package name
- All code in `single.block` comes from verified `snippets/` — no fabrication
- `github_url` must come from model.yaml or index.json — do not guess or construct from pattern

## Post-conditions

**Family mode:**
- Page exists at `content/products.aspose.org/en/{family}/_index.md`
- `layout: family` present in frontmatter
- `evidence:` frontmatter block populated by `attach_evidence.py`
- `audit.py` exits with 0 FAIL
- No forbidden claims present

**Plugin mode:**
- Page exists at `content/products.aspose.org/en/{family}/{platform}/_index.md`
- `layout: plugin` present in frontmatter
- `plugin_platform` field present and correctly capitalised
- `github_url` present and sourced from model.yaml or index.json
- `submenu.enable: true` present
- `supportandlearning`, `more_formats`, `back_to_top` blocks all present with `enable: true`
- `evidence:` frontmatter block populated by `attach_evidence.py`
- `audit.py` exits with 0 FAIL
- No forbidden claims present
