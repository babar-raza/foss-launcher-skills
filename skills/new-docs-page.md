---
name: new-docs-page
description: >
  Generate a new documentation page for docs.aspose.org with knowledge
  pre-conditions, evidence grounding, and post-condition skill chain.
args: "{family} {platform} {section} {slug}"
---
Generate a new documentation page for docs.aspose.org.

> **Configuration**: Output paths below are defaults for the aspose.org repo. See `config.yaml` `sites.docs` for your project's docs content path.

**Arguments:** `$ARGUMENTS`
**Expected format:** `{family} {platform} {section} {slug}` — e.g. `3d python developer-guide mesh-operations`
Valid sections: `getting-started` | `developer-guide`

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

1. **Load corpus profile**: Read `knowledge/{family}/{platform}/_corpus/docs_profile.json`
   - If not found → WARN and suggest running `/corpus-scan {family} {platform} docs`; proceed with default template

2. **Load golden index**: Read `golden/_index.json`
   - If not found → WARN and suggest running `python scripts/golden_index.py`; proceed with default template

3. **Determine variant**: Read `selected_variant` from the corpus profile
   - If `richness_tier: C` → use "minimal" variant (Usage Examples + See Also only)
   - If `richness_tier: A` or `B` → use "standard" variant (full template below)
   - If product has fewer than 3 API classes in knowledge model → force "minimal"

4. **Select golden page**: From `golden/_index.json`, find the page where:
   - `page_role` is `workflow_page` (for developer-guide) or `installation` (for getting-started)
   - `variant` matches the selected variant
   - If no match → fall back to "standard" variant → fall back to any variant for this role

5. **Read the golden file**: Read the actual golden `.md` file at the `source_path` from the index entry

6. **Apply STRUCTURAL CONTRACTS**: For EACH section you generate, find the matching section in the golden page (by heading) and follow its structural contract:
   - Required block types (paragraph, code, list, table) at minimum counts
   - Target prose word count and code block count
   - These are minimum requirements — expand further to fully cover the topic

7. **Apply STYLE ANCHOR**: Use the first 600 chars of the matching golden section as a style reference — match its voice, sentence structure, and depth. Do NOT copy its actual content (it uses template variables).

8. **Apply STYLE RUBRIC** from the golden page's `style_rubric`:
   - If `prose_before_code: true` → every code block must be preceded by a prose paragraph
   - If `use_case_required: true` → include use-case bullet lists after major code examples
   - If `code_completeness_required: true` → code must show import + usage + verification pattern
   - Target `avg_sentence_length` words per sentence
   - Include at least `min_code_variety` distinct code examples

## Steps

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
   ---
   ```

5. **Generate body** — structure differs by section:

   ### For `getting-started` pages:
   - `## {Title}`
   - Opening paragraph: one-sentence purpose statement
   - `---`
   - `### Prerequisites` — markdown table: Requirement | Detail rows (Python version, OS, compiler, system packages)
   - `---`
   - Numbered steps for the task (install, configure, verify)
   - Each step: prose explanation + code block (bash or python)
   - `---`
   - `### Next Steps` — 3–5 links to related getting-started or developer-guide pages using `[Title](../slug/)`

   ### For `developer-guide` pages:
   - `## {Title}`
   - Opening paragraph: what feature/capability this covers and which class is the entry point
   - `---`
   - `### {Feature subsection}` blocks — one per major capability or concept, each with:
     - 1–2 prose sentences
     - Working Python code block
   - `---`
   - `### Tips and Best Practices` — 3–5 bullet points
   - `---`
   - `### Common Issues` — markdown table: Issue | Cause | Fix
   - `---`
   - `### FAQ` — 3–5 `#### Question?` + answer pairs
   - `---`
   - `### API Reference Summary` — markdown table: Class/Method | Description, limited to what you confirmed exists in reference content

6. **Constraints**:
   - Every code block uses ` ```python ` or ` ```bash ` language identifier
   - `---` divider between every major section
   - Class names, method names, package paths must exactly match what you read from reference content — no invented API
   - Internal links: relative paths within same section (`../slug/`) or absolute starting with `/docs.aspose.org/`
   - Do not add a `sidebar:` key unless the section `_index.md` uses it

7. **Write** to `content/docs.aspose.org/en/{family}/{platform}/{section}/{slug}.md`

## Knowledge Post-conditions

After generating the page:

1. **Run evidence citation**: Execute `/evidence-cite content/docs.aspose.org/en/{family}/{platform}/{section}/{slug}.md` to attach `<!-- evidence: ... -->` comments
2. **Run content check**: Execute `/content-check content/docs.aspose.org/en/{family}/{platform}/{section}/{slug}.md` to validate structure and knowledge alignment
3. **Run change guard**: Execute `/change-guard {family} {platform}` with any new claims to verify they don't contradict known facts

8. **Confirm** with the output path and a list of the H2 sections written.
