---
name: new-kb-howto
description: >
  Generate a new KB how-to article
args: "{family} {platform} {slug}"
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

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

## Steps

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
   ---
   ```

4. **Generate body** using this exact section order:
   - Opening paragraph: what the library does for this task; state no install prerequisites beyond pip
   - `## Step-by-Step Guide`
   - `{{% steps %}}`
   - `### Step 1: Install the Package` — pip install command + version check snippet
   - `### Step 2: Import Required Classes` — exact import statements matching the package used in existing content
   - `### Step 3–N:` — one step per logical task action, each with a prose explanation followed by a working Python code block
   - `{{% /steps %}}`
   - `## Common Issues and Fixes` — 3–5 bold-question + answer-paragraph pairs for likely errors
   - `## Frequently Asked Questions` — 3–5 `### Question?` + answer-paragraph pairs
   - `## See Also` — 3–5 links using pattern `[Article Title](/kb.aspose.org/en/{family}/{platform}/slug/)`

5. **Constraints** (hard rules — never violate):
   - Every code block must open with ` ```python ` or ` ```bash ` (language identifier required)
   - Use `---` horizontal divider between each step inside `{{% steps %}}`
   - Class names, method names, and import paths must exactly match what appears in the reference content you read — do not invent new API names
   - All internal links must begin with `/kb.aspose.org/`, `/docs.aspose.org/`, or `/reference.aspose.org/`
   - All claims must be backed by entries in `knowledge/{family}/{platform}/merged/claims.json`

6. **Pre-write quality check**: Invoke `no-downgrade-guard` before writing:
   - Target path: `content/kb.aspose.org/en/{family}/{platform}/{slug}.md`
   - If BLOCK → do not write; report the blocking reason to the user
   - If WARN → present the warning to the user; await confirmation before writing
   - If ALLOW → proceed with write

7. **Write** the file to `content/kb.aspose.org/en/{family}/{platform}/{slug}.md`

## Knowledge Post-conditions

After generating the article:

1. **Attach evidence**: Run `python scripts/pipeline/attach_evidence.py --files content/kb.aspose.org/en/{family}/{platform}/{slug}.md`
   — this writes the `evidence:` YAML frontmatter block (`model_sha`, `claims`, `apis`).
2. **Run content check**: Execute `/content-check content/kb.aspose.org/en/{family}/{platform}/{slug}.md` to validate structure and knowledge alignment
3. **Run change guard**: Execute `/change-guard {family} {platform}` with any new claims to verify they don't contradict known facts
4. **Run audit**: `python scripts/pipeline/audit.py --files content/kb.aspose.org/en/{family}/{platform}/{slug}.md`
   — must exit with 0 FAIL before committing.

7. **Confirm** by printing the output file path and a short summary of steps covered.
