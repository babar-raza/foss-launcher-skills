# Intentionally Omitted Features Plan (Fixture: should PASS with omissions in exclusions)

## Scope Constraints (Operator Guidance)

The following features are explicitly out of scope and must not be built:
- Real-time collaboration editing: deferred indefinitely; no current requirement
- PDF export from reference pages: blocked by licensing; do not implement
- Auto-translation of blog posts: operator decision to keep blog EN-only

## Open Work

1. Add missing evidence blocks to 12 reference pages in the slides family
   - Files: `content/reference.aspose.org/en/slides/net/*.md` (pages with empty `evidence:`)
   - Validation: run `audit.py --files content/reference.aspose.org/en/slides/net/`; expect 0 evidence-missing findings
   - Status: ready

2. Update the knowledge model for the words family (SHA changed)
   - Command: `/knowledge-update words net`
   - Validation: `knowledge/words/net/merged/model.yaml` has `stale_since: null`
   - Status: ready

## Recommended Next Item

Fix the evidence blocks first (item 1) because it unblocks the content-check gate
for the reference pages, which is on the critical path before the next publish cycle.
