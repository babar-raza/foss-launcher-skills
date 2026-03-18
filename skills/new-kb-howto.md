---
name: new-kb-howto
description: >
  Generate a new KB how-to article with step-by-step guide, common issues,
  FAQ, and post-condition skill chain.
args: "{family} {platform} {slug}"
---
Generate a new KB how-to article.

> **Configuration**: Output paths below are defaults for the aspose.org repo. See `config.yaml` `sites.kb` for your project's KB content path.

**Arguments:** `$ARGUMENTS`
**Expected format:** `{family} {platform} {slug}` — e.g. `3d python how-to-convert-fbx-to-gltf`

## Knowledge Pre-conditions

Before generating any content, you MUST:

1. **Read knowledge model**: Load `knowledge/{family}/{platform}/merged/index.json`
   - If it does not exist, STOP and instruct the user to run `/repo-scout` and `/truth-merge` first
   - If `stale: true`, STOP and instruct the user to run `/knowledge-diff` first
   - If `has_conflicts: true`, WARN and list unresolved conflicts from `merge_conflicts.md`
2. **Load verified facts**: Read `knowledge/{family}/{platform}/merged/claims.json` and `api_surface.json`
3. **Load forbidden claims**: Read `forbidden_claims` from `index.json` — never include these in content
4. **Load format matrix**: Read `formats.json` — only reference formats confirmed here
5. **Load snippets**: Check `knowledge/{family}/{platform}/merged/snippets/` for verified code examples
6. **Load constants**: Read `knowledge/{family}/{platform}/merged/constants.json` for module-level constants available for code examples

## Golden Corpus Pre-conditions

1. **Load corpus profile**: Read `knowledge/{family}/{platform}/_corpus/kb_profile.json`
   - If not found → WARN and suggest running `/corpus-scan {family} {platform} kb`; proceed with default template

2. **Load golden index**: Read `golden/_index.json`
   - If not found → WARN and suggest running `python scripts/golden_index.py`; proceed with default template

3. **Determine variant**: Read `selected_variant` from the corpus profile
   - If `richness_tier: C` → use "minimal" variant (shortened steps, skip Common Issues and FAQ)
   - If `richness_tier: A` or `B` → use "standard" variant (full template below)
   - "steps" variant: use when the article needs tutorial format with `{{% steps %}}` shortcode and detailed per-step breakdowns

4. **Select golden page**: From `golden/_index.json`, find the page where `page_role` is `howto_article` and `variant` matches the selected variant
   - If no match → fall back to "standard" variant → fall back to any variant for `howto_article`

5. **Read the golden file**: Read the actual golden `.md` file at the `source_path` from the index entry

6. **Apply STRUCTURAL CONTRACTS**: For EACH section you generate, find the matching section in the golden page (by heading) and follow its structural contract:
   - Required block types (paragraph, code, list, table) at minimum counts
   - Target prose word count and code block count
   - These are minimum requirements — expand further to fully cover the topic

7. **Apply STYLE ANCHOR**: Use the first 600 chars of the matching golden section as a style reference — match its voice, sentence structure, and depth. Do NOT copy its actual content.

8. **Apply STYLE RUBRIC** from the golden page's `style_rubric`:
   - If `prose_before_code: true` → every code block must be preceded by a prose paragraph
   - If `use_case_required: true` → include use-case bullet lists after major code examples
   - If `code_completeness_required: true` → code must show import + usage + verification pattern
   - Target `avg_sentence_length` words per sentence
   - Include at least `min_code_variety` distinct code examples

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

6. **Write** the file to `content/kb.aspose.org/en/{family}/{platform}/{slug}.md`

## Knowledge Post-conditions

After generating the article:

1. **Run evidence citation**: Execute `/evidence-cite content/kb.aspose.org/en/{family}/{platform}/{slug}.md` to attach `<!-- evidence: ... -->` comments
2. **Run content check**: Execute `/content-check content/kb.aspose.org/en/{family}/{platform}/{slug}.md` to validate structure and knowledge alignment
3. **Run change guard**: Execute `/change-guard {family} {platform}` with any new claims to verify they don't contradict known facts

7. **Confirm** by printing the output file path and a short summary of steps covered.
