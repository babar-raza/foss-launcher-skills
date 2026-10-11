# TC-21: ST-215 locale content-drift categorization

**Date**: 2026-09-24
**Source**: `locale_code_block_equivalence.py` live re-run, 2026-09-24 (post TC-20's
sweep-denominator fix; that fix doesn't change this tool's own numbers, since it's an
English-only sweep concern — re-run anyway to confirm no residual drift, confirmed
identical: 12,513 findings).
**Purpose**: categorize the 12,513 findings by root cause BEFORE any fix is attempted,
per this taskcard's own required work and ST-215's own filing. No fixes applied in this
pass — this is the categorization deliverable itself.

## Method

Findings were grouped by `(english_page, block_index, finding_kind)`. Each group's
**locale fan-out** — how many of a page's real, existing locale variants share that
exact drift — is the primary categorization signal: a block that differs from *nearly
every* locale a page has almost certainly means the ENGLISH page changed after the
whole translation batch ran (drift running in the "English moved" direction, not
"one locale got corrupted"). A block that differs from only 1–3 locales is the
opposite signal — a real, page-specific, per-locale anomaly.

597 distinct `(page, block, kind)` groups produce the 12,513 findings (average fan-out
~21 locales/group) — 3 buckets by locale-count:

| Bucket | Locale fan-out | Groups | Findings | % of total |
|---|---|---|---|---|
| **Near-universal** | ≥30 locales | 212 | 7,398 | 59.1% |
| **Mid-range** | 4–29 locales | 301 | 4,941 | 39.5% |
| **Isolated** | 1–3 locales | 84 | 174 | 1.4% |

## Bucket 1 — Near-universal drift (7,398 findings, 59.1%): English moved, locale didn't

212 groups across **105 distinct English pages**, spanning **6 families** (3d, slides,
cells, words, note, email) and **4 sites** (docs/blog/kb/reference — not an isolated
family or site issue) and **all 3 finding kinds** (CONTENT_DRIFT 6,053 / COUNT_MISMATCH
752 / LANG_MISMATCH 593).

**Root cause, confirmed on 2 concrete instances (both already found this session,
before this categorization pass)**:
- `content/blog.aspose.org/3d/java/3d-java-obj-stl-gltf-library/index.md` block 6:
  English is MISSING `opts.setFlipCoordinateSystem(true);` — 36 of its own locale
  siblings (near the full 38-locale set) still carry it. English was edited down
  (or the line was a later addition never back-ported), and none of the 36 already-
  translated locale pages were resynced.
- The `3d-java-obj-stl-gltf-library`/`3d-java-scene-graph-materials`/`3d-key-features`
  pages (and others) share the SAME block-6/block-7 drift signature — consistent with
  these blog posts being generated from a shared template/snippet that was edited once,
  centrally, after the locale batch ran, not edited independently 36+ times.

**Disposition recommendation** (not applied — a content decision, not a mechanical
one): for each affected page, the fix direction is very likely "**resync locale pages
to the current English**", not "revert English" — English drift in this bucket looks
like legitimate content improvement (the FlipCoordinateSystem addition is a real,
useful API call, not garbage) that simply never propagated. This should be verified
per-family (not assumed globally) before any bulk resync, since a family-wide
regeneration event is exactly the kind of change TC-10's own precedent required
real content skills and per-page evidence for, not a blanket script.

## Bucket 2 — Mid-range drift (4,941 findings, 39.5%): same mechanism, partial locale coverage

301 groups, same 3 finding kinds, same likely root cause as Bucket 1 — the only
difference is these pages don't have the full ~36-38 locale set translated yet, so the
same "English moved, locale didn't" drift shows up on fewer locales. **Not a
different root cause; folded into the same disposition as Bucket 1** once verified.

## Bucket 3 — Isolated drift (174 findings, 1.4%): the real per-locale-anomaly candidates

84 groups across 45 distinct English pages, where a block differs from only 1-3 of a
page's locale siblings. This is the bucket most likely to contain genuine translator-
introduced corruption (matching ST-211's own already-diagnosed `Aspose.3D.Converter`
mistranslation shape, and this session's own earlier-found `tex/python`
`introducing-tex-foss-python` th/tr fence-info-string-loss case) rather than a stale-
English artifact — small locale counts mean a shared "central edit" explanation is
much less likely.

**Checked and ruled out**: a hypothesis that specific locales (tr/vi appeared
repeatedly together in early sampling) have their own systemic translator bug.
Locale-frequency counts across ALL findings show tr/vi are simply the two most
completely-translated locales in this portfolio (highest raw frequency in both
COUNT_MISMATCH and LANG_MISMATCH), not disproportionately over-represented relative to
their overall translation coverage — **this is a disclosed non-finding**, not a
confirmed pattern, to avoid the same "carried-forward, unverified claim" mistake this
session's own standing rule (`feedback_reverify_before_acting`) exists to prevent.

## Overlap check with ST-211/ST-212

- **ST-211** (locale SYNTAX-ERROR, ~2,290 files) is a DIFFERENT signal — genuinely
  broken code, found independently by tier-1 syntax checking, not by comparison to
  English. A locale page can pass ST-215's equivalence check (byte-identical to
  English) while still being ST-211-broken if English itself has the same syntax bug,
  or fail ST-215 while being syntactically valid Java/C#/etc (most of this
  categorization's Bucket 1/2 drift is exactly that: different-but-still-valid code).
  The two defect classes are not redundant and neither subsumes the other.
- **ST-212** (sweep classifier blind spot) is now CLOSED (TC-20) — its own fix doesn't
  change this tool's methodology at all (`locale_code_block_equivalence.py` doesn't use
  `example_verification_sweep.py`'s classifier), so no re-categorization was needed on
  that account.

## Recommendation

- **Do not attempt a blanket fix.** Bucket 1+2 (98.6% of findings) need a per-family
  decision on whether English is the correct target to resync TO, verified against
  real upstream source per TC-10's own established discipline — this is squarely
  "needs its own scoped triage mission" per ST-215's own filing, not a continuation of
  this taskcard.
- **Bucket 3 (174 findings, 45 pages) is the highest-value, lowest-risk starting point**
  for a follow-on mission: small enough to review page-by-page, most likely to contain
  real, isolated translator defects rather than a systemic resync job.
- This categorization itself is the taskcard's deliverable; TC-21 closes on this report,
  not on any content fix (matching TC-14's own precedent of deferring execution to a
  follow-on mission when a finding's real scope exceeds a single taskcard).
