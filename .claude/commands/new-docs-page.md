Generate a new documentation page for docs.aspose.org.

**Arguments:** `$ARGUMENTS`
**Expected format:** `{family} {platform} {section} {slug}` — e.g. `3d python developer-guide mesh-operations`
Valid sections: `getting-started` | `developer-guide`

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

1. **Run evidence citation**: Execute `/evidence-cite content/docs.aspose.org/en/{family}/{platform}/{section}/{slug}.md` to write the YAML `evidence:` frontmatter block
2. **Run content check**: Execute `/content-check content/docs.aspose.org/en/{family}/{platform}/{section}/{slug}.md` to validate structure and knowledge alignment
3. **Run change guard**: Execute `/change-guard {family} {platform}` with any new claims to verify they don't contradict known facts
4. **Pre-write gate**: Run `python scripts/pre_write.py {output-file}` before committing
   - Exit 0 (PASS/WARN): proceed
   - Exit 1 (FAIL): do NOT commit — report findings to user and offer to fix

8. **Confirm** with the output path and a list of the H2 sections written.
