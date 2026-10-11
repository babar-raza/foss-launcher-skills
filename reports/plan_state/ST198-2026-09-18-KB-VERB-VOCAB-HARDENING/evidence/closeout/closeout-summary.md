authoritative_plan: PLAN-ST198-KB-VERB-VOCAB-HARDENING
requirement: all
taskcard: TC-ST198-05 (interim -- mission not yet fully closed, see status below)

# Closeout summary (2026-09-23, interim -- pending user push decision)

## What changed (committed locally, commit 093282591dbede21ab48f3ca336a23e55335c59d, NOT pushed)
- scripts/pipeline/commands/launch/site_planner.py: split _VERB_KEYWORDS into
  _KB_VERB_SYNONYMS + _KB_CATEGORY_VERB_HINTS (exact alias preserved); added
  _KB_REVERSE_VERB_VOCAB + split_kb_slug_verb_noun(); _validate_kb_slugs() now calls it;
  Check 2 guarded with `if verb:`.
- scripts/pipeline/content_eval/evaluators/topic_grounding.py: deleted its own duplicated
  vocabulary/loop, delegates to the shared function, same-signature ImportError fallback.
- scripts/pipeline/content_eval/__init__.py: EVALUATOR_VERSIONS["topic_grounding"] 1 -> 2.
- scripts/pipeline/tests/test_site_planner.py +
  scripts/pipeline/tests/content_eval/test_topic_grounding.py: 17 new tests (1 green pin,
  16 new coverage), all passing.

## What did NOT change (proven, not asserted)
- detect_kb_verb() forward-path results: unchanged (golden pin + fingerprint-equal).
- Every generated site plan: byte-identical stdout for all 33 KB family/platform pairs
  (excluding the generated_at timestamp line), including the 3 pairs that already exit
  non-zero for unrelated pre-existing reasons (cells/java stale knowledge; pdf/java, pdf/net
  CamelCase ValueError -- filed as ST-207).
- topic_grounding portfolio FAIL set: byte-identical, 7 files, before and after (9125 pages).
- how-to-read-msg-files-cpp.md: STILL FAILS topic_grounding (only its reported noun text
  changed, read-msg-files -> msg-files) -- real root cause filed as ST-206, NOT fixed here.

## Real-data deltas (measured, not estimated)
- Parsed noun changes: exactly 16 of 248 en KB pages (Appendix D oracle, confirmed 16/16).
- Spurious empty-verb "duplication" warnings: 48 -> 0 (function-level census over all 248
  pages); 7 -> 0 in the real planner CLI across all 33 pairs (5 platforms).
- Genuine duplication warning (words/python): 1 -> 1, preserved.
- 12 previously-masked, genuine C1/C4 slug-quality warnings now correctly surfaced (F-6,
  documented, not a regression -- these defects existed before, they were just hidden by the
  bug this fix removes).

## Verification performed
- Tests: 254 scoped tests (9 files) pass, run 3 times across this session with identical counts.
- Real-data probe: byte-identical output across 3 different PYTHONHASHSEED values.
- Independent adversarial review: ACCEPT (fresh-context subagent, re-ran tests itself,
  1 cheap finding fixed inline, 2 nits recorded, 0 blocking issues).
- Negative/mutation controls: 3/3 confirm the new guard tests would catch real regressions.
- Local CI battery + Tier-1 pre-commit (43 checks): all pass, 0 failed.

## Findings recorded (backlog)
ST-203 (F-2, third CI-gate vocab copy) / ST-204 (F-3, -net suffix) / ST-205 (F-4, unaggregated
warnings) / ST-206 (F-5, CE-02 lexical gap -- the REAL cause of read-msg-files-cpp's FAIL) /
ST-207 (F-9, pre-existing non-zero planner exits) / ST-208 (F-8 correction to ST-198's own
overstated causal claim).

## Status: STOPPED AT INTERNAL GATE, BY DESIGN (not a failure)

Taskcards TC-ST198-00 through TC-ST198-05-05 are CLOSED (30 of 37 rows). TC-ST198-05-06 (push +
CI verification) is BLOCKED_EXTERNAL: this session's standing instruction
(feedback_no_push_before_user_review, 2026-09-19 -- "do not push anything upstream unless I have
reviewed your results") overrides the plan's Appendix F single-go push authorization. The commit
is complete, verified, and sitting locally, ready to push the moment the user authorizes it.
TC-ST198-05-07 and the mission-level closeout remain open pending that decision.
