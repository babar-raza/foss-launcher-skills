---
name: page-enhance
description: >
  Enhance an existing page to meet quality bar
args: "{family} {platform} {section} {slug}"
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# S-21: Page Enhance — Enhance Page to Meet Quality Bar

**Arguments**: $ARGUMENTS
Expected format: `{relative-file-path}` — e.g. `content/docs.aspose.org/en/3d/python/developer-guide/rendering.md`

## Purpose
Enhance a page that scores below the quality bar (grade C or below from S-17/S-25). Consumes evaluation output, identifies weak dimensions, and improves content without changing already-accurate material.

## Pre-conditions
1. S-25 (eval-page) or S-17 (rubric-align) has been run for this page — evaluation results are available
2. The page exists at `{relative-file-path}`
3. Detect `{family}` and `{platform}` from the file path
4. `knowledge/{family}/{platform}/merged/` exists with `claims.json`, `api_surface.json`, `formats.json`
5. Knowledge freshness is auto-checked via `refresh_knowledge.py` in Step 2

## Steps

1. **Parse arguments**: Extract file path from $ARGUMENTS.

2. **Auto-refresh knowledge**: Before loading any knowledge artifacts, ensure they are current:
   ```bash
   .venv/Scripts/python scripts/pipeline/refresh_knowledge.py {family} {platform}
   ```
   - If it prints "refreshed": knowledge was stale and has been rebuilt from the clone cache.
   - If it prints "current": no action needed.
   - If clone cache is missing: warn but continue with existing knowledge artifacts.

3. **Load evaluation results**: Retrieve S-25 or S-17 output for this page. If not available, run S-25 first:
   ```bash
   .venv/Scripts/python -m scripts.pipeline.content_eval evaluate --files {relative-file-path} --format json
   ```

4. **Load knowledge artifacts**:
   - Read `knowledge/{family}/{platform}/merged/claims.json`
   - Read `knowledge/{family}/{platform}/merged/api_surface.json`
   - Read `knowledge/{family}/{platform}/merged/limitations.md`
   - Read `knowledge/{family}/{platform}/snippets/` for available code examples

5. **Read the current page content**.

6. **Identify weak areas** from evaluation findings, prioritized by impact:
   - **FAIL findings**: Must fix (API errors, forbidden claims, wrong platform code)
   - **WARN findings**: Should fix (missing evidence, weak structure, risk language)
   - **Low-scoring dimensions**: Improve (evidence depth, code quality, coverage)

7. **Apply enhancements** — for each weak area:

   **API Accuracy issues**:
   - Replace incorrect API tokens with correct ones from `api_surface.json`
   - Update code blocks using verified snippets from `snippets/`

   **Structure issues**:
   - Add missing sections required by page type
   - Fix heading hierarchy
   - Add code language identifiers to bare code fences

   **Evidence gaps**:
   - Add claims backing for unsupported statements
   - Remove statements that cannot be backed by any claim in `claims.json`

   **Prose truth issues**:
   - Correct format claims to match `formats.json`
   - Remove or reword forbidden claims (from `limitations.md`)

   **Risk language**:
   - Replace superlatives ("best", "fastest") with factual statements
   - Remove speculative claims not backed by evidence

   **Coverage gaps**:
   - Add sections for important API capabilities missing from the page
   - Use claims and snippets from knowledge to fill gaps

8. **Preserve accurate content**: Do NOT rewrite paragraphs that scored well. Only modify sections with findings.

9. **Update evidence frontmatter**: Add new claim IDs and API references for added content.

10. **Run ground-check**:
   ```bash
   .venv/Scripts/python scripts/pipeline/audit.py --files {relative-file-path}
   ```

11. **Re-evaluate** to confirm improvement:
    ```bash
    .venv/Scripts/python -m scripts.pipeline.content_eval evaluate --files {relative-file-path} --format json
    ```

12. **Update provenance**: After writing enhanced content, update the provenance mechanism:
    ```python
    from provenance import update_mechanism
    from pathlib import Path
    update_mechanism(Path("{relative-file-path}"), "page-enhance")
    ```
    The `content_hash` will be normalized automatically by the pre-commit hook — do not compute or pass it here.

13. **Report**:
    ```
    PAGE ENHANCE — {file-path}
    Before: Grade [X] ([score]/100)
    After:  Grade [Y] ([score]/100)

    Enhancements applied:
      - [dimension]: [what was changed]
      ...

    Audit result: PASS/FAIL
    ```

## Post-conditions
- Page grade has improved (target: at least one letter grade up)
- All FAIL findings from evaluation are resolved
- Ground-check (audit.py) passes
- Accurate content is preserved unchanged
- Evidence frontmatter is updated

## Error handling
- If no evaluation data exists, run S-25 first before enhancing
- If grade doesn't improve after enhancement, flag for human review. The operator may then
  invoke **S-73 (manual-edit)** to apply a specific targeted fix they can specify precisely.
- If knowledge is stale, abort and instruct to run S-14 first
