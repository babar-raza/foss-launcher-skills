authoritative_plan: PLAN-ST198-KB-VERB-VOCAB-HARDENING
requirement: REQ-KBV-003, REQ-KBV-007
taskcard: TC-ST198-04-03

# Warning census delta (function-level, 248 en pages, 2026-09-23)

Before: C1-camel 9, C2-dup-emptyverb 48, C2-dup-real 1, C3-generic 1, C4-family 8
After:  C1-camel 13, C2-dup-real 1, C3-generic 1, C4-family 16

- C2-dup-emptyverb: 48 -> 0 (fully removed, as required). Confirmed by absence of the key entirely
  in after's WARNING_TOTALS (Counter has no zero entries).
- C2-dup-real: 1 -> 1, same slug (words/python how-to-convert-converters-python), unchanged.
- RAISED: 0 in both baseline and after (no derived-slug regression).

F-6 (previously masked, now correctly detected): 12 new warnings, all `slides` family, all
explained by the SAME mechanism -- the old unguarded Check 2 fired a spurious empty-verb
"duplication" warning and `continue`d BEFORE Checks 1/3/4 could run on these slugs; the new
`if verb:` guard lets execution reach the real checks, which then correctly fire on real,
pre-existing defects:
  - 4x C4-family: 'apply-3d-effects' / 'format-text' nouns contain no 'slides' family keyword
    (slides cpp/java/net/python x apply-3d-effects, x2 slides cpp/java/net/python x format-text
    -- 8 C4 lines) -- pre-existing slug-quality gaps, unrelated to this fix, now visible.
  - 4x C1-camel: 'save-presentations' now correctly parses verb='save' (a real synonym), so
    noun='presentations' (13 chars, no hyphen) trips the >12-char CamelCase-leak heuristic --
    previously the noun stayed 'save-presentations' (hyphenated, escaping Check 1) because
    'save' wasn't recognised as a verb at all under the old vocabulary.
None of these 12 are RAISED (all source=discovered -> warn-only); no derived-slug behavior changed.
