authoritative_plan: PLAN-ST198-KB-VERB-VOCAB-HARDENING
requirement: REQ-KBV-004, REQ-KBV-007
taskcard: TC-ST198-04-04

# Real entry point dry-run, every KB pair (2026-09-23)

33 pairs re-run after the change. Compared against after-siteplan-table.txt vs
baseline-siteplan-table.txt (both captured THIS session -- baseline in 00-03, after here, per
D14/S1 drift handling; the plan's stale review-time numbers are not used for comparison):

- exit codes: IDENTICAL for all 33 pairs (including the 3 pre-existing non-zero exits:
  cells/java STALE knowledge, pdf/java + pdf/net derived-slug CamelCase ValueError).
- stdout_sha (generated plan YAML, generated_at line excluded): IDENTICAL for all 33 pairs.
  This directly proves the official production entry point (site_planner.py) emits byte-identical
  plans before and after this change.
- emptyverb (Check-2 spurious warning) count: slides cpp/java/net/python 1->0 each, tex/python
  3->0 -- all 7 planner-CLI-visible empty-verb warnings gone, matching AC-3b.
- realc2 (genuine duplication): words/python stays 1, unchanged.
- kbwarn total for slides pairs stayed 1 (not 0) after the emptyverb warning disappeared --
  investigated: the real plan_kb() pipeline feeds a narrower "existing" page set to
  _validate_kb_slugs than the function-level probe (which validates every on-disk how-to-*.md
  stem regardless of current cluster match); the one remaining kbwarn per slides pair is a
  genuine, real C4-family finding ('apply-3d-effects' lacks a slides keyword) -- confirmed live
  by direct inspection, same F-6 class already documented in 04-03. No unexplained warning.
