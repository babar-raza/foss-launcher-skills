# Report Section Header Conventions

This file standardizes the section headers and status markers used by
report-generating skills (S-87 system-heal, S-76 commit, and others) so that
the automatic harvest system (`report_extract.py`) can reliably detect
unresolved items across session reports, commit messages, and heal logs.
Skills MUST use the canonical headers listed here; free-form alternatives
will be silently missed by the harvester.

## Canonical Section Headers

| Pattern Group | Recommended Header | Item Type | Notes |
|---|---|---|---|
| NOT_COMPLETED | `## Not Completed` or `### Not Completed` | not_completed | Use a markdown table with columns: Item, Status, Reason |
| NEXT_STEPS | `## Next Steps Required` or `## Next Steps` | next_step | Use numbered list |
| DEFERRED | Status marker `⚠️ DEFERRED` in tables | deferred | Inline in status column |
| NOT_STARTED | Status marker `NOT STARTED` in tables | not_started | Inline in status column |
| HUMAN_ACTION | `## Required Human Actions` | human_action | Use numbered list |
| BLOCKERS | `### What still blocks` or `## Blockers` | blocker | Use numbered list |
| NOT_PROVEN | `### Not proven` | not_proven | Use numbered list |
| ESCALATED | `## Files Escalated` | escalated | Use bullet list |
| REMAINING | `## Remaining` or `### Remaining follow-ups` | next_step | Use numbered list |
| FUTURE_WORK | `## Future Work` or `## Known limitations` | deferred | Use numbered list |
| OPEN_WORK | `## Open work` or `### Open items` | next_step | Use bullet list |

When a pattern group offers multiple header variants (e.g. `## Remaining` vs
`### Remaining follow-ups`), prefer the shorter form. The longer form exists
for backward compatibility with older reports.

## Status Markers

### Completion markers (filtered OUT by the harvester)

Items bearing any of these markers are treated as resolved and will **not**
appear in the unresolved-item feed:

```
FIXED   DONE   RESOLVED   VERIFIED   APPROVED   PASS   [x]   ✅
```

### Open markers (retained by the harvester)

These markers explicitly flag an item as unresolved:

```
⚠️ DEFERRED   NOT STARTED   BLOCKED   PENDING   [ ]   ❌
```

When writing a status table, every row MUST carry exactly one marker from
either list so that the harvester can classify it unambiguously.

## Anti-Patterns

1. **Non-standard headers.** Do not invent headers like "Stuff we didn't
   finish" or "TODO maybe later". The harvester matches a fixed pattern
   registry; unrecognized headers cause silent data loss.

2. **Mixed completion states without markers.** If a section contains both
   completed and uncompleted items, every item must have an explicit status
   marker. A bare list with no markers is assumed unresolved for the entire
   section.

3. **Nesting unresolved items inside "Completed" sections.** The harvester
   skips sections whose header signals completion (e.g. `## Completed`). Any
   unresolved item buried inside will never surface.

4. **Using HTML comments to hide unresolved work.** The harvester operates on
   raw markdown; HTML comments are stripped before pattern matching, so
   hidden items are silently lost.

## Cross-Reference

See `scripts/pipeline/commands/ops/report_extract.py` for the authoritative pattern
registry. If a new pattern group is added there, update the table above to
keep them in sync.
