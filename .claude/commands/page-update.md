# S-20: Page Update — Update Page After Knowledge Change

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}` or `{relative-file-path}`

## Purpose
After a knowledge refresh (S-14), identify which content pages reference changed claims and produce targeted updates. Only modifies paragraphs affected by knowledge changes — preserves accurate content untouched.

## Pre-conditions
1. Knowledge freshness is auto-checked via `refresh_knowledge.py` in Step 2 (replaces manual S-14 prerequisite)
2. If targeting a specific file, it must exist under `content/`
3. `knowledge/{family}/{platform}/merged/claims.json` exists (current)
4. Content pages have `evidence:` frontmatter with `claims` and `apis` arrays

## Steps

1. **Parse arguments**: Determine scope — either all pages for `{family}/{platform}` or a single file.

2. **Auto-refresh knowledge**: Before loading any knowledge artifacts, ensure they are current:
   ```bash
   python scripts/pipeline/refresh_knowledge.py {family} {platform}
   ```
   - If it prints "refreshed": knowledge was stale and has been rebuilt from the clone cache.
   - If it prints "current": no action needed.
   - If clone cache is missing: warn but continue with existing knowledge artifacts.

3. **Load knowledge diff**: Compare current `knowledge/{family}/{platform}/merged/claims.json` with the previous version. Identify:
   - **Added claims**: New claim IDs not in previous version
   - **Removed claims**: Claim IDs that no longer exist
   - **Modified claims**: Same ID but changed text, confidence, or provenance
   - **API changes**: Diff `api_surface.json` for added/removed/renamed members

4. **Find affected pages**: Scan content files for the product:
   - For product-wide scope: scan all `.md` files under the product's content paths (docs, kb, blog, reference)
   - Read each page's `evidence:` frontmatter
   - A page is affected if its `claims` or `apis` arrays reference any changed/removed item

5. **For each affected page**, produce an update plan:
   - Map each removed/modified claim to the paragraph(s) that reference it
   - For removed claims: mark paragraph for rewrite or removal
   - For modified claims: identify specific sentences that need updating
   - For API changes (renamed/removed methods): find code blocks and prose mentioning old names
   - For added claims: identify if any existing section should incorporate new information

6. **Pre-write quality check**: For each affected page, invoke `no-downgrade-guard` before writing:
   - Target path: the affected page's file path
   - If BLOCK → do not write; report the blocking reason to the user
   - If WARN → present the warning to the user; await confirmation before writing
   - If ALLOW → proceed with write

7. **Apply updates**:
   - Rewrite affected paragraphs using current claims from `claims.json`
   - Update code blocks if API surface changed (use snippets from `knowledge/{family}/{platform}/snippets/`)
   - Update `evidence:` frontmatter: remove orphaned claim IDs, add new ones
   - Update `model_sha` in evidence frontmatter to current value

8. **Run ground-check** on each updated page:
   ```bash
   python scripts/pipeline/audit.py --files {updated-file-path}
   ```

9. **Update provenance**: For each file where body content was modified, update the provenance mechanism:
   ```python
   from provenance import update_mechanism
   from pathlib import Path
   update_mechanism(Path("{updated-file-path}"), "page-update")
   ```
   The `content_hash` will be normalized automatically by the pre-commit hook — do not compute or pass it here.

10. **Report**: For each updated page, print:
   ```
   PAGE UPDATE — {file-path}
   Changes applied:
     - [claim CLM-xxx]: paragraph N rewritten (claim modified)
     - [claim CLM-yyy]: removed (claim no longer exists)
     - [api OldClass.method → NewClass.method]: code block updated
   Audit result: PASS/FAIL
   ```

## Post-conditions
- All affected pages have been updated to reflect current knowledge
- No pages reference removed or orphaned claim IDs
- Evidence frontmatter is current (model_sha matches latest)
- Ground-check passes on all updated pages
- Unaffected content is unchanged

## Error handling
- If no knowledge diff is available (S-14 not run), abort with instruction to run S-14 first
- If a page references a removed claim but the paragraph cannot be safely rewritten, flag for human review
- If audit.py fails after update, list specific issues and attempt one correction pass
