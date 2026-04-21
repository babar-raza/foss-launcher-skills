---
name: no-downgrade-guard
id: S-56
description: >
  Pre-write quality comparison guard. Prevents generated content from silently
  overwriting a higher-quality existing page. Returns ALLOW, WARN, or BLOCK.
args: "{target-path} {proposed-content | --proposed-file | --stdin}"
---

# S-56: No-Downgrade Guard — Pre-Write Quality Comparison

**This is a sub-routine, not a user-facing command.**

**Calling convention**: Invoked by generation skills before any file write.
**Protocol**: Returns `ALLOW | WARN | BLOCK`

## Purpose

Prevent a newly generated page from silently overwriting a higher-quality existing page.
Uses content_eval grade as a quality proxy for both the existing and proposed content.

## Invocation

```bash
# Inline proposed content:
python scripts/pipeline/no_downgrade_guard.py {target-path} "{proposed-markdown}"

# From a file:
python scripts/pipeline/no_downgrade_guard.py {target-path} --proposed-file /tmp/draft.md

# From stdin:
cat /tmp/draft.md | python scripts/pipeline/no_downgrade_guard.py {target-path} --stdin

# JSON output:
python scripts/pipeline/no_downgrade_guard.py {target-path} --proposed-file /tmp/draft.md --json

# Operator override (bypass guard):
python scripts/pipeline/no_downgrade_guard.py {target-path} --proposed-file /tmp/draft.md --force-regenerate
```

## Decision Matrix

| Existing Grade | Proposed Grade | Decision |
|---|---|---|
| A or B | D or F | **BLOCK** |
| A or B | C | **WARN** |
| A or B | A or B | ALLOW |
| C | D or F | **BLOCK** |
| C | C or better | ALLOW (lateral or improvement) |
| D or F | any | ALLOW (anything is better or equal) |
| new file | any | ALLOW |

## Structural Regression Checks (run before grade comparison)

Independent of grade, the guard also blocks on:
- Word count drops below 30% of existing (catastrophic content destruction)
- Heading count drops below 50% when ≥3 headings existed
- All code blocks removed when ≥2 existed (WARN)
- Plugin-page enabled sections removed

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | ALLOW — write is safe |
| 1 | WARN — degradation possible, user should review |
| 2 | BLOCK — write would regress quality |

## Integration

Add a call to this sub-routine **before the write step** in generation skills:
`new-blog-post`, `new-docs-page`, `new-kb-faq`, `new-kb-howto`, `new-reference-page`,
`page-draft`, `page-update`

Pattern:
```
Before writing: invoke no-downgrade-guard {target-path} {proposed-content}
- If BLOCK → do not write; report blocking reason to user
- If WARN → present warning to user; await confirmation before writing
- If ALLOW → proceed with write
```

## Notes

- If `content_eval` is unavailable, falls back to audit.py FAIL count for grading
- `--force-regenerate` bypasses all guards (operator override, for batch refresh operations)
- Source: ported from aspose.org S-55; assigned foss-launcher ID S-56
