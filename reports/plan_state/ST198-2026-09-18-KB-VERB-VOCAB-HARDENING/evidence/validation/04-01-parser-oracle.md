authoritative_plan: PLAN-ST198-KB-VERB-VOCAB-HARDENING
requirement: REQ-KBV-001, REQ-KBV-007
taskcard: TC-ST198-04-01

# Parser oracle diff (2026-09-23)

after-probe.txt sha256: d08bc23879336f3b260e80ab97f49fa385391150c22cda07c0271404077e1e4d

NOUNS diff vs baseline-probe.txt: exactly 16 lines changed, matching Appendix D's oracle rows
1-for-1 (family/platform/stem/old-noun -> new-noun/new-verb). No other of the 248 en pages changed.

NOVERB: 48 -> 32 (apply 4, configure 1, connect 4, fix 2, format 4, get 13, style 1, use 3);
read/save/parse/inspect entries (16 total) are gone, as expected.

WARNING_TOTALS: C1-camel 9->13, C3-generic 1->1, C4-family 8->16, C2-dup-emptyverb 48->0 (gone),
C2-dup-real 1->1 (unchanged). The C1/C4 increases are the F-6 "previously masked by the spurious
Check-2 continue" effect -- expected and tracked, see 04-03.

Cross-check: for all 248 en pages, tg._extract_topic_noun(stem, plat) ==
sp.split_kb_slug_verb_noun(stem, plat)[1] -- 248/248 match (single shared implementation).
