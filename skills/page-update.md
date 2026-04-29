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

> **Skill context gate** — run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-20 --scope "*"
> ```


1. **Parse arguments**: Determine scope — either all pages for `{family}/{platform}` or a single file.

2. **Auto-refresh knowledge**: Before loading any knowledge artifacts, ensure they are current:
   ```bash
   .venv/Scripts/python scripts/pipeline/commands/knowledge/refresh_knowledge.py {family} {platform}
   ```
   - If it prints "refreshed": knowledge was stale and has been rebuilt from the clone cache.
   - If it prints "current": no action needed.
   - If clone cache is missing: warn but continue with existing knowledge artifacts.

3. **Load knowledge diff**: Read `knowledge/{family}/{platform}/merged/knowledge_delta.json`.
   This file is written by `refresh_knowledge.py` after each successful refresh. Identify:
   - **Added claims**: `new_claims` — new claim IDs not in previous version
   - **Removed claims**: `removed_claims` — claim IDs that no longer exist
   - **Modified claims**: `modified_claims` — same ID but changed text, confidence, or provenance
   - **API changes**: `new_apis`, `removed_apis`, `modified_apis` — added/removed/changed classes

   **If `knowledge_delta.json` is absent** (first run after launch, or no refresh has occurred):
   fall back to stale_detect scan — scan all pages for evidence.model_sha mismatch to find affected pages.
   Log: `WARN: knowledge_delta.json not found; falling back to stale_detect scan for affected pages.`

4. **Find affected pages** (dual-path logic: citation-match + PIA-match):
   - For product-wide scope: scan all `.md` files under the product's content paths (docs, kb, blog, reference)
   - Read each page's `evidence:` frontmatter
   - **Citation-match path**: A page is affected if its `claims` or `apis` arrays reference any changed/removed item
   - **PIA-match path**: Load `reports/refresh_review/{family}/{platform}/page_impact.json` if present.
     Add any page with `pia_score` of `HIGH_IMPACT` or `MEDIUM_IMPACT` to the affected-pages list,
     even if its `evidence.claims`/`evidence.apis` have no delta overlap.
     - For `MEDIUM_IMPACT` pages: perform LLM-assisted semantic review against current `claims.json`;
       body updated only if review confirms change is warranted.
     - If `LLM_API_KEY` absent and page is `MEDIUM_IMPACT` only (not citation-matched):
       flag as `NEEDS_HUMAN_REVIEW` in page_decisions.json; do not silently skip.
     - If `page_impact.json` absent: skip PIA-match path with a WARN; citation-match still runs.
   - De-duplicate: pages found by both paths are processed once

5. **For each affected page**, produce an update plan:
   - Map each removed/modified claim to the paragraph(s) that reference it
   - For removed claims: mark paragraph for rewrite or removal
   - For modified claims: identify specific sentences that need updating
   - For API changes (renamed/removed methods): find code blocks and prose mentioning old names
   - For added claims: identify if any existing section should incorporate new information

   **Blog post strategy** (pages under `content/blog.aspose.org/`):
   Blog posts are narrative content — surgical paragraph patching destroys coherence.
   Apply these rules instead:
   - If `removed_claims` or `removed_apis` includes any ID cited by this blog page
     → full regeneration via `/new-blog-post {family} {platform} {slug}`. Do not patch.
   - If only `modified_claims` (text changes, no removals) → update only the specific
     claim-citing sentences (not whole paragraphs).
   - If only `new_claims` are present → no update needed; new content goes in new pages
     via delta dispatch (S-84 Step 5).

6. **Pre-write quality check**: For each affected page, invoke `no-downgrade-guard` before writing:
   - Target path: the affected page's file path
   - If BLOCK → do not write; report the blocking reason to the user.
     **If the guard BLOCKS a known-accurate update**: do not silently skip. Use S-73 (manual-edit)
     with explicit justification. Document the reason in the commit message.
   - If WARN → present the warning to the user; await confirmation before writing
   - If ALLOW → proceed with write

7. **Apply updates**:
   - Rewrite affected paragraphs using current claims from `claims.json`
   - Update code blocks if API surface changed (use snippets from `knowledge/{family}/{platform}/snippets/`)
   - Update `evidence:` frontmatter: remove orphaned claim IDs, add new ones
   - Update `model_sha` in evidence frontmatter to current value
   - **Record decision after each page**:
     ```bash
     .venv/Scripts/python scripts/pipeline/commands/ops/refresh_review.py {family} {platform} \
         --record-decision --path {relative_file_path} \
         --decision {BODY_UPDATED|EVIDENCE_ONLY} \
         --reason "{delta_signal_description}" \
         [--body-changed]   # only when body prose was modified
     ```
     Decision rules:
     - Pages with body prose changes → `BODY_UPDATED` (pass `--body-changed`)
     - Pages with only `evidence.model_sha` updated → `EVIDENCE_ONLY`
     - Pages assessed as NOT_AFFECTED by PIA but still scanned → `NOT_AFFECTED`
     - Blog posts set to `draft: true` → `RETIRED`
   - Also call `record_pages` for tracking:
     ```bash
     .venv/Scripts/python scripts/pipeline/commands/ops/post_refresh_verify.py {family} {platform} \
         --step page_update --updated {space_separated_updated_paths}
     ```

8. **Run ground-check** on each updated page:
   ```bash
   .venv/Scripts/python scripts/pipeline/commands/content/audit.py --files {updated-file-path}
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

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-20 --status completed
> ```

## Body-change requirement rules

Not all delta signals require body prose changes. Use this table to determine
whether a metadata-only update is acceptable or whether body content MUST change:

| Delta signal | Body change REQUIRED? | Rationale |
|---|---|---|
| `removed_claims` citing specific paragraphs | YES | Remove stale sentences referencing removed APIs/features |
| `modified_claims` | YES | Update sentences to reflect changed behavior |
| `removed_apis` with no page citations | NO | Only evidence cleanup needed |
| `new_claims` for existing pages | NO | New content goes in new pages or dedicated sections |

## Frontmatter write rule

ALWAYS use `attach_evidence.py` to update evidence blocks:
```bash
.venv/Scripts/python scripts/pipeline/commands/healing/attach_evidence.py --files {updated-file-path}
```
NEVER construct evidence YAML manually or via `yaml.dump`. The `evidence/writer.py`
performs surgical regex-based replacement that preserves non-evidence frontmatter
fields and avoids duplicate keys.

## Post-conditions
- All affected pages have been updated to reflect current knowledge
- No pages reference removed or orphaned claim IDs
- Evidence frontmatter is current (model_sha matches latest)
- Ground-check passes on all updated pages
- Unaffected content is unchanged

## Error handling
- If `knowledge_delta.json` not found: fall back to stale_detect scan (Step 3); log warning
- If a page references a removed claim but the paragraph cannot be safely rewritten, flag for human review
- If audit.py fails after update, list specific issues and attempt one correction pass
- If no-downgrade-guard BLOCKS a known-accurate update: escalate to S-73 (manual-edit); do not skip
