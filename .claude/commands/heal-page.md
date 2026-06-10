# S-26: Heal Page — Fix Low-Quality Content

**Arguments**: $ARGUMENTS
Expected format: `{content-file-path}`

## Purpose
Systematically fix a content page that received a grade of D or below from S-25 (eval-page). Applies fixes in priority order to maximize quality improvement.

## Pre-conditions
1. S-25 eval report must exist for this page in `reports/eval/`
2. Content file must exist
3. Knowledge model must exist: `knowledge/{family}/{platform}/merged/index.json`
4. Knowledge must not be stale (if stale, run S-14 knowledge-update first)

## Steps

1. **Read the eval report** from S-25 (most recent for this file in `reports/eval/`)

2. **Read the content file**

3. **Load knowledge**: `index.json`, `claims.json`, `api_surface.json`, `formats.json`, `forbidden_claims`, `snippets/`

4. **Apply fixes in priority order**:

   a. **CONTRADICTED claims** (highest priority):
      - Find paragraphs that match forbidden_claims
      - Remove or rewrite using correct information from claims.json
      - If no correct claim exists, remove the paragraph entirely

   b. **Unverified API references**:
      - Find class/method names not in api_surface.json
      - Replace with correct verified names from api_surface.json
      - If no match exists, remove the code block and note the gap

   c. **Contradicted format claims**:
      - Find format assertions that disagree with formats.json
      - Correct direction (import/export/both) or remove if format is unsupported

   d. **Missing evidence citations**:
      - Identify factual sections not represented in the YAML `evidence:` frontmatter block
      - Match each to the closest claim in claims.json
      - Mark for S-24 (evidence-cite) to attach proper citations

   e. **Structural issues**:
      - Fix invalid frontmatter fields
      - Add missing section dividers
      - Correct heading hierarchy
      - Add missing template sections (per page type)

   f. **Golden conformance issues** (if conformance score < 0.55):
      - Load `golden/_index.json` and find the matching golden page for this page's role/variant
      - Read the golden file at `source_path`
      - If section_coverage low → add missing golden sections with appropriate content
      - If section_order low → reorder sections to match golden sequence
      - If depth_proportionality low → expand thin sections or trim bloated ones toward golden proportions
      - If block_type_coverage low → add missing block types (code, list, table) per golden structural contract
      - If code_density_alignment low → adjust code-to-prose ratio toward golden target

   g. **Missing content** (lowest priority):
      - Identify claims from knowledge model not covered by the page
      - Add new sections for high-confidence claims (confidence >= 0.8)
      - Use verified snippets for code examples where available

5. **Update frontmatter**: Set `lastmod` to today's date

6. **Write healed content** back to the file

7. **Log changes** to `reports/heal/{family}-{platform}-{slug}-{timestamp}.md`

## Output

```
HEAL PAGE — {content-file-path}
Previous grade: {grade from S-25}

Fixes applied:
  Contradictions removed:  {n}
  API references fixed:    {n}
  Format claims corrected: {n}
  Citations prepared:      {n}
  Structural fixes:        {n}
  Golden conformance:      {n} sections aligned to golden template
  Sections added:          {n}

Estimated new grade: {grade}
Report: reports/heal/{report-filename}
```

## Post-conditions
- After healing, the calling chain MUST run:
  1. S-23 (ground-check) — verify the healed content passes truth gate
  2. S-25 (eval-page) — re-evaluate to confirm grade improvement
- If re-eval still shows D or F after healing → escalate to human review
- Maximum 2 healing attempts per page before escalation (AGENTS.md Section 8)

## Error handling
- If eval report not found → run S-25 first, then proceed
- If knowledge is stale → abort with message to run S-14 first
- If content file is empty → cannot heal, escalate to human
- Track healing attempt count — if this is attempt 3+, refuse and escalate
