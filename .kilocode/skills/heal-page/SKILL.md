---
name: heal-page
description: >
  Heal a low-quality page by fixing audit failures and improving grade
args: "{family} {platform} {section} {slug}"
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# S-26: Heal Page — Heal Low-Quality Page

**Arguments**: $ARGUMENTS
Expected format: `{relative-file-path}` — e.g. `content/docs.aspose.org/en/3d/python/developer-guide/rendering.md`

## Purpose
Heal a page that received grade D or below from S-25 (eval-page). Applies targeted fixes for each FAIL finding, then re-evaluates. Escalates to human if grade does not improve after 2 attempts.

## Pre-conditions
1. S-25 (eval-page) has been run and the page received grade D or F
2. The file at `{relative-file-path}` exists under `content/`
3. Detect `{family}` and `{platform}` from the file path
4. `knowledge/{family}/{platform}/merged/` exists with `claims.json`, `api_surface.json`
5. Knowledge freshness is auto-checked via `refresh_knowledge.py` in Step 2

## Steps

1. **Parse arguments**: Extract file path from $ARGUMENTS.

2. **Auto-refresh knowledge**: Before loading any knowledge artifacts, ensure they are current.
   Invoke S-14 (knowledge-update) via its underlying script:
   ```bash
   .venv/Scripts/python scripts/pipeline/refresh_knowledge.py {family} {platform}
   ```
   - If it prints "refreshed": knowledge was stale and has been rebuilt from the clone cache.
   - If it prints "current": no action needed.
   - If clone cache is missing: warn but continue with existing knowledge artifacts.

3. **Load evaluation report**: Retrieve S-25 output for this page. If not available, run S-25 first:
   ```bash
   .venv/Scripts/python -m scripts.pipeline.content_eval evaluate --files {relative-file-path} --format json --remediation
   ```
   If grade is C or above, report that healing is not needed and exit.

4. **Load knowledge artifacts**:
   - Read `knowledge/{family}/{platform}/merged/claims.json`
   - Read `knowledge/{family}/{platform}/merged/api_surface.json`
   - Read `knowledge/{family}/{platform}/merged/formats.json`
   - Read `knowledge/{family}/{platform}/merged/limitations.md`
   - Read `knowledge/{family}/{platform}/snippets/` for code replacements

5. **Read the current page content**.

6. **Healing pass 1** — apply targeted fixes for each FAIL finding:

   | Finding type | Fix strategy |
   |-------------|-------------|
   | API accuracy FAIL | Replace wrong API token with correct one from `api_surface.json` |
   | Forbidden claim | Remove the sentence/paragraph containing it |
   | Wrong platform code | Replace code block with correct-platform snippet from `snippets/` |
   | Broken structure | Rebuild section following page-type template |
   | Missing frontmatter | Add required fields |
   | Placeholder text | Replace with knowledge-grounded content or remove |
   | Risk language | Rewrite with factual, evidence-backed phrasing |

7. **Update evidence frontmatter**: Refresh `claims`, `apis`, and `model_sha`.

8. **Run ground-check after pass 1**:
   ```bash
   .venv/Scripts/python scripts/pipeline/audit.py --files {relative-file-path}
   ```

9. **Re-evaluate after pass 1**:
   ```bash
   .venv/Scripts/python -m scripts.pipeline.content_eval evaluate --files {relative-file-path} --format json
   ```

10. **Check improvement**: If grade is now C or above, report success and exit.

11. **Healing pass 2** (if still D or F): Apply more aggressive fixes:
    - Rewrite entire failing sections from scratch using claims and snippets
    - Remove sections that cannot be fixed (better to be incomplete than wrong)
    - Simplify code examples to only verified API calls

12. **Re-evaluate after pass 2**:
    ```bash
    .venv/Scripts/python -m scripts.pipeline.content_eval evaluate --files {relative-file-path} --format json
    ```

13. **Update provenance**: After each pass that modifies body content, update the provenance mechanism:
    ```python
    from provenance import update_mechanism
    from pathlib import Path
    update_mechanism(Path("{relative-file-path}"), "heal-page")
    ```
    The `content_hash` will be normalized automatically by the pre-commit hook — do not compute or pass it here.

14. **Final decision**:
    - If grade C or above: report success
    - If still D or F: **escalate to human** — do not attempt further automatic fixes.
      For each escalated item, the operator should invoke **S-73 (manual-edit)** with the
      specific change they want to apply. S-73 is the only sanctioned path for
      operator-directed targeted edits.

15. **Report**:
    ```
    HEAL PAGE — {file-path}
    Initial grade: {letter}

    Pass 1:
      Fixes applied: {count}
      - [{finding}]: {fix description}
      Grade after pass 1: {letter}

    Pass 2 (if needed):
      Fixes applied: {count}
      Grade after pass 2: {letter}

    RESULT: {HEALED | ESCALATED}
    Final grade: {letter}
    ```

## Post-conditions
- If HEALED: page grade is C or above, ground-check passes
- If ESCALATED: page is flagged for human review, no further automatic changes
- All fixes are grounded in knowledge (no fabrication)
- Evidence frontmatter is current

## Error handling
- If knowledge model is missing or stale, abort — healing without knowledge would introduce errors
- If audit.py fails persistently, escalate immediately
- Never apply more than 2 healing passes — escalate after that per AGENTS.md Section 8
