---
name: ground-check
id: S-23
description: >
  Pre-write safety gate that verifies every factual claim in a content page
  is traceable to the knowledge model. Blocks fabricated or contradicted content.
args: "{content-file-path}"
depends_on: [path-guard]
---

# S-23: Ground Check — Pre-Write Evidence Verification

**Arguments**: $ARGUMENTS
Expected format: `{content-file-path}` — e.g. `content/docs.aspose.org/en/3d/python/getting-started/installation.md`

## Purpose
Verify that every factual claim in a content page is grounded in the knowledge model before allowing a write. This is the truth gate — distinct from content-check which validates structure/formatting. Ground-check validates evidence: is every assertion traceable to verified knowledge?

> **This skill is mandatory before every content write.** No content may be committed without a PASS or WARN from this skill. A FAIL after 2 retries triggers a hard stop and human escalation.

## Pre-conditions
1. Content file must exist (or be staged for write)
2. Knowledge model must exist: `knowledge/{family}/{platform}/merged/index.json`
3. Knowledge must not be stale (`stale: false` in index.json)

## Steps

1. **Read the content file** at the path given in $ARGUMENTS

2. **Identify product**: Extract `{family}` and `{platform}` from the file path

3. **Load knowledge artifacts**:
   - `knowledge/{family}/{platform}/merged/index.json` — master index
   - `knowledge/{family}/{platform}/merged/claims.json` — verified claims
   - `knowledge/{family}/{platform}/merged/api_surface.json` — verified API
   - `knowledge/{family}/{platform}/merged/formats.json` — verified formats
   - `knowledge/{family}/{platform}/merged/constants.json` — verified constants
   - Extract `forbidden_claims` from index.json

4. **Claim traceability check**: For each factual paragraph in the content (skip frontmatter, headings, code blocks, link-only lines):
   - Search claims.json for a matching claim (semantic similarity)
   - If match found:
     - Check `confidence >= 0.5` — if below, flag as LOW_CONFIDENCE
     - Check `provenance != "llm_fallback"` — if llm_fallback, flag for HUMAN_REVIEW
   - If no match found: flag as UNGROUNDED
   - Count: GROUNDED, UNGROUNDED, LOW_CONFIDENCE, HUMAN_REVIEW

5. **Forbidden claim check**: For each paragraph, check against `forbidden_claims` list:
   - If any paragraph asserts a forbidden claim → immediate FAIL
   - Forbidden claims include: unsupported features, removed API, incorrect format support

6. **API grounding check**: For each code block and inline code reference:
   - Extract class names and method calls
   - Verify each exists in `api_surface.json`
   - Flag UNVERIFIED_API for any class/method not in the API surface

7. **Constant grounding check**: For any reference to module-level constants (UPPER_CASE identifiers) in code blocks:
   - Verify the constant name exists in `constants.json`
   - Flag UNVERIFIED_CONSTANT if not found

8. **Format grounding check**: For any format claims (e.g., "supports FBX export", "can read GLTF"):
   - Verify against `formats.json`
   - Check direction (import/export/both) matches the claim
   - Flag CONTRADICTED_FORMAT if formats.json disagrees

9. **Snippet provenance check**: For code examples longer than 3 lines:
   - Check if the code appears in `knowledge/{family}/{platform}/merged/snippets/`
   - If not from snippets, check that all API used is verified (step 6)
   - Flag UNVERIFIED_CODE if neither condition met

10. **Compute result**:
   - Count total factual assertions checked
   - Calculate grounded percentage = GROUNDED / total
   - **PASS**: No forbidden claims, no contradictions, grounded >= 80%, no UNVERIFIED_API
   - **WARN**: No forbidden claims, no contradictions, grounded >= 60%, minor unverified API (count and list)
   - **FAIL**: Any forbidden claim detected, OR any format contradiction, OR grounded < 60%, OR critical UNVERIFIED_API in code blocks

11. **Write report** to `reports/ground-check/{family}-{platform}-{slug}-{timestamp}.md`

## Output

```
GROUND CHECK — {content-file-path}
Knowledge: {family}/{platform} (sha: {repo_sha})
Timestamp: {ISO-8601}

Claims checked: {total}
  GROUNDED:       {n} ({pct}%)
  UNGROUNDED:     {n} ({pct}%)
  LOW_CONFIDENCE:  {n}
  HUMAN_REVIEW:    {n}

Forbidden claims: {n}
  {list if any}

API references: {total}
  VERIFIED:       {n}
  UNVERIFIED:     {n}
  {list unverified if any}

Format claims: {total}
  CONFIRMED:      {n}
  CONTRADICTED:   {n}
  {list contradicted if any}

Code blocks: {total}
  FROM_SNIPPETS:  {n}
  VERIFIED_API:   {n}
  UNVERIFIED:     {n}

RESULT: {PASS | WARN | FAIL}
Report: reports/ground-check/{report-filename}
```

## Error handling
- If knowledge model not found → FAIL with "Knowledge model missing — run /truth-merge first"
- If knowledge is stale → FAIL with "Knowledge is stale — run /knowledge-update first"
- If content file not found → FAIL with "Content file not found"
- On any FAIL: the calling chain should attempt to fix issues and re-run (max 2 retries)
- After 2 consecutive FAILs → hard stop, escalate to human review

## Relationship to content-check
- **content-check** validates structure: frontmatter fields, heading format, file naming, shortcode usage, template compliance
- **ground-check (this skill)** validates truth: every factual claim is backed by evidence, no fabrication, no contradiction
- Both should run before committing. They are complementary gates, not alternatives.
