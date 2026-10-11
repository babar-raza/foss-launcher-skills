# PAGE-MAP-001: Include new_claims and new_apis in PIA Scoring

**Status**: Accepted
**Date**: 2026-06-01
**Backlog**: PAGE-MAP-001

## Problem

When upstream FOSS repositories add new APIs or capabilities, the knowledge model
generates `new_claims` and `new_apis` entries in `knowledge_delta.json`. However,
`page_impact_assess.py` only scored pages against `modified_claims`, `removed_claims`,
`modified_apis`, and `removed_apis` — ignoring new entries entirely.

Existing pages that logically discuss the same topic as a new claim or API were
silently assigned EVIDENCE_ONLY decisions (model_sha updated, body untouched).
Users saw outdated content that omitted new capabilities.

## Decision

Extend PIA's two extraction functions to include new delta keys:

- `_extract_api_names()`: add `"new_apis"` to the iteration tuple
- `_extract_claim_keywords()`: add `"new_claims"` to the iteration tuple

No changes to scoring thresholds, decision engine, or semantic guard logic.

## Rationale

- The existing 2-keyword threshold for MEDIUM_IMPACT already prevents false positives
  from single-word matches on generic new_claims text.
- HIGH_IMPACT requires exact API class/method name match, which is inherently precise.
- The ENRICHMENT_CANDIDATE detection already handled new_apis for cluster-based
  matching; this fix makes the primary scoring consistent.
- Option A (minimal code change) was preferred over full redesign because the
  existing PIA architecture is sound — only the input filtering was incomplete.

## Consequences

- Pages discussing topics related to new upstream capabilities will now be flagged
  HIGH_IMPACT (API name match) or MEDIUM_IMPACT (keyword match).
- The semantic body update planner will propose updates for these pages.
- The semantic refresh guard's EVIDENCE_ONLY count may decrease for products with
  active upstream development, as more pages receive body updates.
- False positive risk is bounded by the 2-keyword threshold and exact-match API scoring.
