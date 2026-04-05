# S-59: New KB FAQ — Generate FAQ Page for Product Platform

Generate or update the FAQ page for a product platform.

**Arguments:** `$ARGUMENTS`
**Expected format:** `{family} {platform}` — e.g. `cells python`

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
   - Read `knowledge/{family}/{platform}/merged/limitations.md` (if the file exists — skip this step
     if absent) for known unimplemented items — **limitations cross-check**: for every format or
     capability claim in the FAQ (e.g., "can write to X", "supports Y format"), verify it does not
     contradict a known limitation. Correct contradictions before generating content.

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

7. **Pre-write quality check**: Invoke `no-downgrade-guard` before writing:
   - Target path: `content/kb.aspose.org/en/{family}/{platform}/faq.md`
   - If BLOCK → do not write; report the blocking reason to the user
   - If WARN → present the warning to the user; await confirmation before writing
   - If ALLOW → proceed with write

8. **Write** to `content/kb.aspose.org/en/{family}/{platform}/faq.md`

## Knowledge Post-conditions

After generating or updating the FAQ:

1. **Attach evidence**: Run `python scripts/pipeline/attach_evidence.py --files content/kb.aspose.org/en/{family}/{platform}/faq.md`
   — this writes the `evidence:` YAML frontmatter block (`model_sha`, `claims`, `apis`).
2. **Run content check**: Execute `/content-check content/kb.aspose.org/en/{family}/{platform}/faq.md` to validate structure and knowledge alignment
3. **Run change guard**: Execute `/change-guard {family} {platform}` with any new claims to verify they don't contradict known facts
4. **Run audit**: `python scripts/pipeline/audit.py --files content/kb.aspose.org/en/{family}/{platform}/faq.md`
   — must exit with 0 FAIL before committing.
5. **Run format eval**: `python -m scripts.pipeline.content_eval.cli evaluate {family} {platform} --evaluators format_truth,format_completeness --files content/kb.aspose.org/en/{family}/{platform}/faq.md --strict`
   — must exit 0 (no FAIL findings) before committing.

8. **Confirm** by printing the output path and a count of FAQ items written or added.
