authoritative_plan: PLAN-ST198-KB-VERB-VOCAB-HARDENING
requirement: REQ-KBV-007
taskcard: TC-ST198-00-03

# Baseline headlines (2026-09-23, HEAD ac3672f7b8)

- Scoped tests (9 files): 237 passed in 28.58s -- matches plan review exactly.
- Real-data probe (Appendix A, en KB corpus): sha256 e58323de9c...8e0e -- BYTE IDENTICAL to the plan's recorded
  review baseline. The English KB slug corpus has not changed since 2026-09-18 authoring / 2026-09-19 review.
  248 pages; NOVERB 48; WARNING_TOTALS C1-camel 9, C2-dup-emptyverb 48, C2-dup-real 1, C3-generic 1, C4-family 8.
- Evaluator (topic_grounding, all products): 9125 pages, FAIL=7, WARN=0, INFO=0, 52s-class runtime -- matches review.
- Local CI battery (4 checks): all exit 0, matches review.
- gh CI baseline: last 4 runs each of content-governance-checks.yml and ci-eval-consistency.yml, all "success".
  Most recent run of either workflow: 2026-09-14 (9 days ago) -- expected, since these are push-triggered and
  scoped to paths this plan touches, which nobody has touched since.

## DRIFT NOTE (real, informational, does not block execution)

The real-planner-CLI table (site_planner.py <fam> <plat> --mode update --dry-run over all 33 KB pairs) differs from
the plan's review-time table, even though the EN KB corpus hash is unchanged (so this is knowledge/non-EN-content
drift from the 81 other commits landed since the plan's c47e56659a anchor, none of which touch our 5 files):
- pdf/python: exit 1 (CamelCase ValueError) at review -> exit 0 now (someone fixed the underlying page/knowledge).
- slides/cpp: exit 1 at review -> exit 0 now, but now carries 1 emptyverb warning (new, previously masked/absent).
- emptyverb total: 6 at review -> 7 now (slides cpp/java/net/python = 4, tex/python = 3).
This is exactly the kind of concurrent-repo drift the plan's D14/S1 anticipates. It does not affect AC-1/AC-4 (the
16-row noun-change oracle is scoped to the EN corpus, which is byte-identical). It DOES mean the "before" table for
AC-3b/04-04 is THIS run's freshly captured baseline-siteplan-table.txt, not the plan's stale review-time prose
numbers -- which is how the plan's own comparison mechanism (C-10 before/after diff) is designed to work.
