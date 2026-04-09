# S-55: No-Downgrade Guard — Pre-Write Quality Comparison

**This is a sub-routine, not a user-facing command.**

**Calling convention**: Invoked by generation skills before any file write.
**Protocol**: `no-downgrade-guard {target_path} {proposed_content}` → `ALLOW | WARN | BLOCK`

## Purpose

Prevent a newly generated page from silently overwriting a higher-quality existing page.
Uses `audit.py` FAIL count as a quality proxy for proposed content.

## Steps

1. **Check if target file exists**:
   - If `{target_path}` does NOT exist → return `ALLOW:new-file`
   - Print: "NEW FILE: no prior grade to protect — proceeding."

2. **Grade existing file**:
   ```bash
   .venv/Scripts/python -m scripts.pipeline.content_eval evaluate --files {target_path} --format json
   ```
   - Parse: `existing_grade` = output `grade` field (A/B/C/D/F)
   - If eval fails (module unavailable): fallback — run `python scripts/pipeline/audit.py --files {target_path}`; grade by FAIL count: 0→B, 1-2→C, 3-5→D, 6+→F

3. **Pre-check proposed content** (write to temp location first):
   - Write proposed content to: `/tmp/aspose-proposed-{basename}` (or OS temp dir)
   - Run: `python scripts/pipeline/audit.py --files /tmp/aspose-proposed-{basename}`
   - Count FAIL lines from output → `proposed_fail_count`
   - Assign `predicted_grade`:
     - 0 FAIL → predicted B
     - 1-2 FAIL → predicted C
     - 3-5 FAIL → predicted D
     - 6+ FAIL → predicted F
   - Delete temp file

4. **Decision matrix**:

   | Existing Grade | Predicted Grade | Decision |
   |---|---|---|
   | A | D or F | **BLOCK** |
   | A | C | **WARN** |
   | A | A or B | ALLOW |
   | B | D or F | **BLOCK** |
   | B | C | **WARN** |
   | B | A or B | ALLOW |
   | C | D or F | **BLOCK** |
   | C | C | ALLOW (lateral — no regression) |
   | C | A or B | ALLOW |
   | D or F | any | ALLOW (anything is better or equal) |
   | new file | any | ALLOW |

5. **Output**:
   - **BLOCK**: Print "BLOCK: Proposed content predicted {grade} vs existing {grade}. Fix API issues first." + list the audit FAIL lines. **Do NOT write the file.**
   - **WARN**: Print "WARN: Proposed content predicted {grade} vs existing {grade}. Review before writing." Generation skill must confirm with user before proceeding.
   - **ALLOW**: Print "ALLOW: {reason}." Generation skill proceeds with write.

## Limitations

- Cannot fully eval proposed content without writing it first; uses `audit.py` FAIL count as a proxy.
- This catches API accuracy regressions (D/F overwriting A/B) but may not catch prose quality regressions that do not involve API token errors.
- If `content_eval` module is unavailable, the fallback grading by FAIL count is used; it is less precise.

## Integration

Add a call to this sub-routine **before the write step** in these generation skills:
`new-blog-post`, `new-docs-page`, `new-kb-faq`, `new-kb-howto`, `new-reference-page`,
`page-draft`, `page-update`

**Pattern to add before each write step:**
```
Before writing: invoke no-downgrade-guard {target_path} {proposed_content}
- If BLOCK → do not write; report the blocking reason to the user
- If WARN → present the warning to the user; await confirmation before writing
- If ALLOW → proceed with write
```
