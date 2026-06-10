Generate a new KB how-to article.

**Arguments:** `$ARGUMENTS`
**Expected format:** `{family} {platform} {slug}` — e.g. `3d python how-to-convert-fbx-to-gltf`

## Knowledge Pre-conditions

Before generating any content, you MUST:

0. **Validate setup**: Run `python scripts/check_setup.py --family {family} --platform {platform}`
   - If exit code 2 (ERROR): STOP and report the error to the user before proceeding.
   - If exit code 1 (WARN): proceed but surface all warnings.

1. **Read knowledge model**: Load `knowledge/{family}/{platform}/merged/index.json`
   - If it does not exist, STOP and instruct the user to run `/repo-scout` and `/truth-merge` first
   - If `stale: true`, STOP and instruct the user to run `/knowledge-diff` first
   - If `has_conflicts: true`, WARN and list unresolved conflicts from `merge_conflicts.md`
2. **Load verified facts**: Read `knowledge/{family}/{platform}/merged/claims.json` and `api_surface.json`
2b. **Read API surface summary**: Read `knowledge/{family}/{platform}/merged/api_surface.md`
    - This is the concise, human-readable API reference
    - Every class name, method, property, and enum value in your generated content MUST appear in this file
    - If a name is not in api_surface.md, do not use it
3. **Load forbidden claims**: Read `forbidden_claims` from `index.json` — never include these in content
4. **Load format matrix**: Read `formats.json` — only reference formats confirmed here
5. **Load snippets**: Check `knowledge/{family}/{platform}/merged/snippets/` for verified code examples

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

1. **Run evidence citation**: Execute `/evidence-cite content/kb.aspose.org/en/{family}/{platform}/{slug}.md` to write the YAML `evidence:` frontmatter block
2. **Run content check**: Execute `/content-check content/kb.aspose.org/en/{family}/{platform}/{slug}.md` to validate structure and knowledge alignment
3. **Run change guard**: Execute `/change-guard {family} {platform}` with any new claims to verify they don't contradict known facts
4. **Pre-write gate**: Run `python scripts/pre_write.py {output-file}` before committing
   - Exit 0 (PASS/WARN): proceed
   - Exit 1 (FAIL): do NOT commit — report findings to user and offer to fix

7. **Confirm** by printing the output file path and a short summary of steps covered.
