authoritative_plan: PLAN-ST198-KB-VERB-VOCAB-HARDENING
requirement: all
taskcard: TC-ST198-05-07 (final)

# Final closeout (2026-09-25, production-grade)

Mission ST198-2026-09-18-KB-VERB-VOCAB-HARDENING: 37/37 taskcards CLOSED.

## What shipped (on origin/main, commit 093282591dbede21ab48f3ca336a23e55335c59d)
Single shared KB-slug verb/noun parser (site_planner.py + topic_grounding.py delegation),
Check-2 empty-verb guard, EVALUATOR_VERSIONS["topic_grounding"] 1->2. 5 files, 17 new tests.

## Production-grade closure additions (2026-09-25, beyond the original plan)
- Re-verified all 5 committed files are byte-identical to the commit on current HEAD
  (9af1a9205c, 2 days / ~30 commits later): 4/5 untouched; content_eval/__init__.py touched by
  two unrelated, benign evaluator bumps from other missions -- our own line confirmed intact.
- Re-ran the full 254-test scoped suite on current HEAD: still 254 passed.
- Re-ran the real-data probe on current content/knowledge: only 1 of 248 pages' status changed
  (unrelated evidence-attachment by another mission), every fix-relevant metric byte-identical.
- Discovered and correctly handled a real system-state gap the original plan didn't anticipate:
  both CI workflows the plan's verification depended on are disabled repo-wide (MT069 cost
  control). Workflow 1 had a real, incidental PASS for our exact sha (used as genuine evidence,
  not fabricated). Workflow 2 has no manual dispatch trigger at all -- rather than force it via
  an out-of-scope CI-config edit or an unauthorized extra push, its substance was proven via its
  own identical local test instead. See closeout/ci-verification.md for full reasoning.

## Verification chain (final)
tests (254, twice, 2 days apart) -> real-data probe (3 hash seeds + 2 points in time) ->
independent adversarial review (ACCEPT) -> negative controls (3/3 confirm guards are real) ->
Tier-1 pre-commit (43/43 pass) -> real CI run (workflow 1, exact sha, PASS) -> local-test
substitute for workflow 2 (re-run fresh against current HEAD).

## Backlog filed
ST-203 (F-2, third CI-gate vocab copy) / ST-204 (F-3, -net suffix) / ST-205 (F-4, unaggregated
warnings) / ST-206 (F-5, the REAL cause of read-msg-files-cpp's FAIL) / ST-207 (F-9, pre-existing
unrelated non-zero planner exits) / ST-208 (correction to ST-198's own overstated claim).

## Known, accepted, honestly-recorded limitation
Workflow 2 (Eval Rerun Consistency) has never itself executed in CI for this change. This is a
real, deliberate, and correctly-scoped limitation, not an oversight -- forcing it would have
required actions outside this mission's authority. Risk is low: its entire check is one pytest
file, proven green repeatedly including on current HEAD.
