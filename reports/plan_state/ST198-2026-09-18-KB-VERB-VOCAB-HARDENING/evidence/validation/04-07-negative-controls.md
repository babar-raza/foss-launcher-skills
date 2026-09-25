authoritative_plan: PLAN-ST198-KB-VERB-VOCAB-HARDENING
requirement: REQ-KBV-001, REQ-KBV-003, REQ-KBV-006
taskcard: TC-ST198-04-07

# Negative and mutation controls (2026-09-23)

NC-1: a naive "flatten every raw keyword into the reverse vocab" mutation would wrongly recognise
52 category-hint keywords (animation, annotations-form, cfb, comment, compound-file, ...) as
strippable verbs -- confirmed nonempty intersection with _KB_CATEGORY_VERB_HINTS raw keywords.
This proves test_category_hint_keywords_are_never_verbs / test_format_hint_is_not_stripped are
real regression guards, not tautologies.

NC-2: ''.startswith('') == True -- confirmed. This is exactly why an UNGUARDED Check 2 fires on
every empty-parsed-verb slug (the pre-fix bug); the `if verb:` guard is not optional decoration.

NC-3: a shuffled copy of _KB_REVERSE_VERB_VOCAB does NOT satisfy the (-len, alpha) sort predicate
(confirmed False) -- proves test_reverse_vocab_is_deterministic_longest_first would catch a
future accidental unsorted/non-deterministic vocabulary construction.

All 3 controls confirm the guard tests would actually catch the regressions they exist to prevent.
