authoritative_plan: PLAN-ST198-KB-VERB-VOCAB-HARDENING
requirement: REQ-KBV-006, REQ-KBV-007
taskcard: TC-ST198-01-05

# Red-state verification (2026-09-23)

Expected red set (15 tests) vs actual: MATCH.

test_site_planner.py -k "TestKbVerbVocabulary or TestKbSlugValidator": 13 failed, 17 passed, 106 deselected
  - TestKbVerbVocabulary: 9 failed (AttributeError: split_kb_slug_verb_noun / _KB_VERB_SYNONYMS /
    _KB_CATEGORY_VERB_HINTS / _KB_REVERSE_VERB_VOCAB do not exist yet -- correct, function not written).
    test_detect_kb_verb_forward_path_golden PASSED (green pin, as required).
  - TestKbSlugValidator: 4 new failed, all pre-existing tests still pass:
    - test_synonym_led_discovered_slug_logs_no_duplication_warning: fails because the CURRENT
      unguarded Check 2 fires a spurious "verb='' appears in noun='read-msg-files'" warning.
    - test_unknown_verb_discovered_slug_logs_no_duplication_warning: same shape.
    - test_unknown_verb_derived_slug_does_not_raise_duplication: currently RAISES (should not) --
      ValueError "verb='' appears in noun='get-started-email'".
    - test_real_duplication_still_raises_for_derived_synonym_verb: raises, but with verb=''
      instead of verb='read' -- this is literally ST-198's core defect (a raw synonym "read" is
      not recognised as a verb by the current parser).

test_topic_grounding.py -k "TestExtractTopicNoun": 2 failed, 3 passed, 21 deselected
  - test_strips_raw_verb_synonym: fails, current output "read-msg-files" != expected "msg-files".
  - test_evaluator_uses_shared_parser_with_no_local_vocabulary: fails, tg._KNOWN_VERBS still exists.

Total: 15 red, all for the documented reason; no test failed for an unexpected reason; no test
that should stay green failed. Baseline scoped-test count preserved (237 unaffected by these
new/only-additive test files besides the 15 new red + 1 new green).
