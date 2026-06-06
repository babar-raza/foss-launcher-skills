# MIGRATION_LOG — Bulk Grade Migration Approvals
Source: C:\Users\prora\.claude\plans\curried-pondering-music.md §17.8
Created: 2026-04-21 by WS-A

## Required commit annotation (per DEC-06)
```
BULK-GRADE-MIGRATION: approved by [name] on [date], reason: [policy trigger]
```

## Policy triggers that justify a bulk migration
1. First grading of previously ungraded pages
2. Healing batch: body content changed AND grade letter changed
3. Grade letter crossed a band boundary under human-approved cause
4. MIG-01: Phase 5 one-time operational field removal — explicit approval required
5. Content pipeline output defect corrected (generation template fix applied to body)

## Guardrail
GUARD-01 (pre-commit hook) and GUARD-02 (CI check) block commits with ≥20 .md files
changed in grade frontmatter only, unless this log has an entry and the commit carries
the annotation string above.

## Log
| ID | Date | Approved by | Commit | Files | Trigger | Status |
|---|---|---|---|---|---|---|
| MIG-01 | 2026-04-24 | owner | 69c6ca2b31 | 9,902 | MIG-01 Phase 5 operational field removal: strip graded_at, graded_logic_version, graded_evaluators, graded_model_sha, graded_evaluator_versions, graded_enrichment_status; preserve grade, graded_content_hash, grade_reasons; manifest safety net at reports/grade_manifest.json (9,213 entries); 92 files with pre-existing audit failures deferred | DONE |
| MIG-02 | 2026-05-24 | sprint-PRODUCT-LAUNCH-REFRESH-PLANNING-MEGA-TRAIN-1 | bc7c0b669d | 148 | S-90 content_eval re-run for words/python after refresh to SHA d051a96a (v26.5.0); graded_content_hash updated to reflect current content hash under new model SHA; 25 additional files had body+grade changes (not grade-only); trigger: policy 1 (first S-90 grading sweep) + policy 3 (re-grade under refreshed knowledge model) | DONE |
| MIG-03 | 2026-06-09 | unified-honking-key TC-CTA-GRADUATION | — | 0 | DEFAULT graduation of cta_wording evaluator: moved from EXPERIMENTAL_EVALUATORS to DEFAULT_EVALUATORS in config.py. No grade changes expected (0 new FAILs confirmed by corpus-wide eval of 4303 pages on 2026-06-06). No GRADE_CONTRACT version bump (cta_wording not added to CANONICAL_EVALUATORS — grade impact unchanged). 13 unit tests in test_cta_wording.py pass. | DONE |
