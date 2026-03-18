---
name: new-kb-faq
description: >
  Generate or update the FAQ page for a product platform with licensing,
  installation, format support, API usage, and known limitations sections.
args: "{family} {platform}"
---
Generate or update the FAQ page for a product platform.

> **Configuration**: Output paths below are defaults for the aspose.org repo. See `config.yaml` `sites.kb` for your project's KB content path.

**Arguments:** `$ARGUMENTS`
**Expected format:** `{family} {platform}` — e.g. `cells python`

## Knowledge Pre-conditions

Before generating any content, you MUST:

1. **Read knowledge model**: Load `knowledge/{family}/{platform}/merged/index.json`
   - If it does not exist, STOP and instruct the user to run `/repo-scout` and `/truth-merge` first
   - If `stale: true`, STOP and instruct the user to run `/knowledge-diff` first
   - If `has_conflicts: true`, WARN and list unresolved conflicts from `merge_conflicts.md`
2. **Load verified facts**: Read `knowledge/{family}/{platform}/merged/claims.json` and `api_surface.json`
3. **Load forbidden claims**: Read `forbidden_claims` from `index.json` — never include these in content
4. **Load format matrix**: Read `formats.json` — only reference formats confirmed here
5. **Load limitations**: Read `limitations.md` for known NotImplementedError items
6. **Load constants**: Read `knowledge/{family}/{platform}/merged/constants.json` for module-level constants available for code examples

## Golden Corpus Pre-conditions

1. **Load corpus profile**: Read `knowledge/{family}/{platform}/_corpus/kb_profile.json`
   - If not found → WARN and suggest running `/corpus-scan {family} {platform} kb`; proceed with default template

2. **Load golden index**: Read `golden/_index.json`
   - If not found → WARN and suggest running `python scripts/golden_index.py`; proceed with default template

3. **Select golden page**: From `golden/_index.json`, find the page where `page_role` is `faq` and `variant` is `standard`

4. **Read the golden file**: Read the actual golden `.md` file at the `source_path` from the index entry

5. **Apply STRUCTURAL CONTRACTS**: For EACH FAQ category section, find the matching section in the golden page (by heading) and follow its structural contract:
   - Minimum question count per category
   - Required block types (paragraph, code, list) at minimum counts
   - These are minimum requirements — add more Q&A pairs based on the knowledge model

6. **Apply STYLE ANCHOR**: Use the first 600 chars of the matching golden section as a style reference — match its voice and answer depth. Do NOT copy its actual content.

7. **Apply STYLE RUBRIC** from the golden page's `style_rubric`:
   - If `prose_before_code: true` → every code block must be preceded by a prose paragraph
   - If `code_completeness_required: true` → code must show import + usage + verification pattern
   - Target `avg_sentence_length` words per sentence

## Steps

1. **Parse** `$ARGUMENTS` into `family` and `platform`.

2. **Check if an FAQ exists** at `content/kb.aspose.org/en/{family}/{platform}/faq.md`:
   - If it exists: read the full file, identify what questions are already covered, then add new questions at the end (do not duplicate)
   - If it does not exist: create from scratch following the full template below

3. **Read for context** (read only — do not copy):
   - Read `content/reference.aspose.org/en/{family}/{platform}/_index.md` to understand available classes, limitations, and format support
   - Read one existing how-to article from `content/kb.aspose.org/en/{family}/{platform}/` to see keyword style

4. **Frontmatter** (for new files — preserve existing frontmatter when updating):
   ```yaml
   ---
   title: Frequently Asked Questions
   description: >
     FAQ about Aspose.{Family} FOSS for {Platform} — licensing, known limitations,
     format support, and common usage questions.
   date: '{today as YYYY-MM-DD}'
   lastmod: '{today as YYYY-MM-DD}'
   weight: 1
   draft: false
   type: topic
   keywords:
   - {product name} python faq
   - {product name} python licensing
   - {product name} open source
   - {6–10 more question-oriented keywords}
   ---
   ```
   When updating an existing file: update only `lastmod` to today's date; leave all other frontmatter unchanged.

5. **Content structure** — write or append these FAQ categories (skip categories that are already fully covered):

   **Licensing & Open Source** (2–3 questions):
   - What is the licensing model?
   - Can I use it in commercial products?

   **Installation & Requirements** (2–3 questions):
   - How do I install? What Python versions are supported?
   - Are there any native dependencies?

   **Format Support** (2–4 questions):
   - Which formats can be read / written?
   - Known limitations per format (FBX exporter, animation stubs, etc. — based on what you read)

   **API Usage** (3–5 questions):
   - Typical pattern for the main entry-point class (e.g. `Scene`, `Workbook`, `Presentation`)
   - How to traverse/iterate the data model
   - Saving in different formats

   **Known Limitations** (2–3 questions):
   - Features that are stubbed or not yet implemented (base answers on what you observed in reference content)

   Each question uses `### Question text?` as the heading followed by one or more answer paragraphs.

6. **Constraints**:
   - All class names, method names, and package import paths must match what you read from the reference content — do not invent API surface
   - Code examples use ` ```python ` language identifier
   - `weight: 1` ensures FAQ appears first in the KB listing — never change this value

7. **Write** to `content/kb.aspose.org/en/{family}/{platform}/faq.md`

## Knowledge Post-conditions

After generating or updating the FAQ:

1. **Run evidence citation**: Execute `/evidence-cite content/kb.aspose.org/en/{family}/{platform}/faq.md` to attach `<!-- evidence: ... -->` comments
2. **Run content check**: Execute `/content-check content/kb.aspose.org/en/{family}/{platform}/faq.md` to validate structure and knowledge alignment
3. **Run change guard**: Execute `/change-guard {family} {platform}` with any new claims to verify they don't contradict known facts

8. **Confirm** by printing the output path and a count of FAQ items written or added.
