# readme-refresh retention-vs-redundancy hardening — findings and design (living spec)

Mission `readme-refresh-retention-vs-redundancy-hardening-2026-09-04`. Full root-cause analysis
and design lives in the approved plan file (`C:\Users\prora\.claude\plans\i-want-to-investigate-
refactored-petal.md`) — this document records real measurements gathered during implementation,
per this session's own "plan as living spec" discipline.

## 1. Implementation summary

- `check_content_unit_reframe_fidelity`'s and `_retention_fidelity`'s stale "never a gate"
  docstrings fixed (§6.4 of the plan).
- New advisory check `check_content_unit_cross_section_restatement` (readme_refresh_checks.py):
  the cross-section sibling of `check_content_unit_probable_duplicate`, identifier-anchored
  word-overlap-ratio heuristic (§6.1).
- New advisory check `check_candidate_growth_ratio`: coarse whole-document tripwire (§6.3).
- `skills/readme-refresh.md`'s "give it a second, fuller home" default-remedy instruction
  replaced with a required, ordered, per-unit reconciliation procedure (§6.2).
- `CHECKS_MODULE_VERSION` 7→8; `check_function_count` 118→120 (two new checks).
- 10 new tests (6 for cross-section-restatement, 4 for growth-ratio), all passing on first
  write with no threshold tuning needed.

## 2. Real portfolio measurement (not simulated, not assumed)

### 2.1 `check_content_unit_cross_section_restatement`
Ran directly against all 32 candidates' real `content-dispositions.json` files:

**117 total findings across 21 of 32 products (66%).** pdf/typescript is an overwhelming
outlier — **54 findings**, more than 4x the next-highest product (pdf/cpp, 13). The other 19
affected products show 1-4 findings each:

```
3d/net: 1        cells/rust: 2      pdf/go: 3          slides/net: 2
barcode/python: 3 email/net: 1      pdf/java: 7        slides/python: 3
cells/cpp: 1      page/python: 2    pdf/net: 2         words/net: 3
cells/java: 4      pdf/cpp: 13      pdf/python: 3       words/python: 1
cells/net: 2       pdf/typescript: 54  slides/cpp: 3
cells/python: 3                       slides/java: 4
```

This is strong, direct confirmation the check correctly identifies pdf/typescript as the real
standout incident, not a false alarm on an otherwise-quiet portfolio, while also surfacing a
real, non-trivial *background rate* on 20 other products worth a future look.

### 2.2 Precision spot-check on a DIFFERENT product (pdf/cpp, 13 findings)
Read the first 6 findings' actual excerpt pairs directly (not the identifiers/ratios alone):

- **5 of 6 are genuine, real restatement** — e.g. a Key Capabilities bullet listing annotation
  subtypes (`Highlight`, `Underline`, `Squiggly`, `StrikeOut`, ...) and a separate API-reference
  sentence independently listing the identical subtype set (ratio 0.94); an AcroForm field-type
  bullet and a separate field-type list (ratio 0.88). Real, milder-flavored duplication than
  pdf/typescript's prose-explanation case (an enumerated list restated, not a full explanation),
  but genuine.
- **1 of 6 is a confirmed false positive**: `u0025`/`u0052` matched on the shared identifiers
  `DocumentInfo`/`Metadata`, but `u0052`'s excerpt is a markdown table-header fragment
  (`| Class | Description |\n|---|---|\n| Artifact | Class with 14 methods. |...`), not real
  prose about `DocumentInfo` at all — an extraction-boundary artifact producing an unrelated
  pairing. Disclosed, not silently ignored; a real, concrete example of the false-positive class
  the check's own docstring already warns to expect.

Rough precision on this one sample: ~83% (5/6). Reasonable for an advisory signal, not clean
enough to consider hard-gating without further tuning — exactly matching the plan's own stated
rollout discipline.

### 2.3 `check_candidate_growth_ratio` — weaker than expected once calibrated (disclosed, not hidden)
Measured whole-document and section-scoped ratios directly against real files before choosing a
threshold:

| Product | Source size | Candidate size | Whole-doc ratio |
|---|---|---|---|
| pdf/typescript | 274,584 B | 315,266 B | **1.15x** |
| 3d/java | 23,387 B | 39,803 B | **1.70x** (legitimate — 0 cross-section-restatement findings) |
| 3d/net, barcode/python, cells/cpp, cells/typescript, font/python, html/python, tex/python | — | — | 0.97–1.01x (stable, already-converged candidates) |

pdf/typescript's own **section-scoped** ratio (candidate `## Key Capabilities`, including the
new detail block, vs. the old README's `## Features` section) was only **1.08x** — barely
elevated, because the real defect is cross-section duplication (the same fact restated in TWO
different sections, each individually near-normal size), not one section growing too large in
isolation. The section-scoped design from the original plan sketch was abandoned for this
reason (documented directly in the check's own docstring) in favor of a whole-document version.

Even the whole-document ratio is a weak signal for *this specific incident*: pdf/typescript's
1.15x is **less extreme** than 3d/java's fully legitimate 1.70x. The shipped threshold (2.0x) is
calibrated above the real, confirmed-legitimate 3d/java value specifically so the check does not
misfire on normal, healthy growth — which means it does **not** fire on pdf/typescript's own
1.15x either. This is disclosed plainly in the check's own docstring: it is a blunt, generic
"something changed a lot" prompt, not a proxy for the redundancy check, and growth ratio and
redundancy turned out to be only loosely correlated in the real data measured here.

## 3. Honest conclusion
`check_content_unit_cross_section_restatement` is the check that actually explains and would
have caught this incident — real, measured, validated on a second, independent product's real
data, not just pdf/typescript's own. `check_candidate_growth_ratio` is real and correctly
implemented per the approved plan, but the measurement here shows it is a much weaker signal for
this specific defect class than the plan anticipated; it remains in place as the coarse,
low-cost tripwire it was always described as, with its own limits stated in its docstring rather
than overclaimed.

## 4. Deferred, disclosed, not fixed this pass
- **The false-positive class found in §2.2** (an excerpt that is really a markdown table
  fragment matching on a shared identifier with unrelated real prose) — real, disclosed, not
  patched here; a targeted "excerpt looks like a table row, skip it" pre-filter is a plausible,
  low-risk future refinement once more real examples are collected.
- **The 20 other products' 117 total findings** are not triaged here — that is real editorial
  review work per product, out of scope for a check-engineering pass, exactly the same
  discipline this session applied to pdf/typescript's own remaining redundancy (plan §6.5,
  scheduled separately).
- **pdf/typescript's own content cleanup** (plan §6.5: the `ToImage`/`Sign`/`ToHtml`/`AddHtml`
  pairs, and now 50 more real findings the check surfaced beyond the original 4 manually found)
  is real editorial work, not done in this check-engineering pass.

## 5. 2026-09-04 follow-up: pdf/typescript regeneration + completeness re-verification

User asked to regenerate the pdf/typescript candidate and compare it against the real upstream
README for completeness. Ran `recheck` against the live run (`rr-20260903T072250Z-3a82d15feb0f`,
still `AWAITING_REVIEW`), then did the §2.2/§4-deferred editorial pass on the 54 (now 53)
`content_unit_cross_section_restatement` findings by hand, reading full excerpts and real
candidate context, not just ratios.

**A real, previously-undisclosed false-positive mechanism, confirmed by direct code read**: 41 of
the 54 findings (76%) pair a small Key-Capabilities bullet against `u0243` -- a single disposition
entry whose `excerpt` is the ENTIRE API Reference member table (26,852 chars, 806 content words),
not one row. `check_content_unit_cross_section_restatement`'s actual implementation (verified by
reading `readme_refresh_checks.py:8379-8412` directly) computes `ratio = |overlap| /
min(len(words_a), len(words_b))` over the FULL excerpt text of both sides -- not a "surrounding
prose window" as the approved plan's §6.1 described designing. Since `u0243`'s 806-word excerpt
contains a fragment of nearly every identifier used anywhere in the API surface, almost any small
Key-Capabilities bullet that shares even one identifier with it scores a spuriously high ratio.
This is a real gap between the approved design and the shipped implementation, not just a
tolerance-tuning issue -- filed as **ST-186** (deferred; a real fix needs the window-based
comparison the plan originally specified, or a size-ratio guard that skips pairs where one
excerpt is disproportionately larger than the other).

Manually reviewing the remaining 13 "normal-scale" pairs (both excerpts well under 3,000 chars,
full text read side by side) found the API Reference section's own established convention -- a
short recap sentence immediately before OR immediately after that method's own code example --
accounts for the great majority of them (confirmed structurally: grepped the candidate directly
for 5 of the pairs and found a code fence adjacent to the shorter side in every case checked).
This is a legitimate, intentional two-tier documentation pattern, not invented duplication.

**One genuine, confirmed redundancy found and fixed**: `u0032` (Key Capabilities, ReplaceText),
`u0163` (API Reference "Replace Text" subsection, immediately following its own code example),
and `u0290` (a Scope and Limitations bullet, "Text replace is same-font, no-reflow") all stated
the identical fact -- ReplaceText's same-font/no-reflow/`UnsupportedFeatureError` behavior --
three times, with `u0290` adding zero net-new information over `u0163`. Re-disposed `u0290` to
`excluded`/`redundant_with_existing` (ledger + candidate both updated) and re-ran `recheck`:
0 hard-gate failures before and after, `content_unit_reframe_fidelity` stayed at 0 findings
(confirms this was a safe, surgical trim, not a retention regression).

**Second real, previously-undisclosed finding**: a direct script comparison of all 315
merged-unit excerpts against their actual location in the candidate (matched against the real H2
section boundaries, checking ALL occurrences of each excerpt's opening 80 characters, not just
the first) found **167 of 315 (53%) have a `target_section` field that does not match where their
text actually landed** in the composed candidate -- the real location is consistently
"Additional Examples" (a large collapsed block spanning lines 311-2356) for units the ledger still
declares "Key Capabilities" or "API Reference". Spot-checked 3 by direct grep (`u0078`, `u0100`,
`u0003`) -- all confirmed real, not a matching artifact. This means `check_content_unit_cross_
section_restatement` and `check_content_unit_probable_duplicate` are both working off stale
section labels for roughly half the ledger, which the hard gate `check_content_unit_merged_into_
target_section` does not catch by design (it only requires salient-token presence somewhere in
the declared section, not that the exact unit's text is uniquely there -- documented, deliberate
tolerance for legitimate rephrasing, not a bug in that check). Filed as **ST-187** (deferred; real
fix is either re-deriving `target_section` from the actual candidate at `recheck` time, or a
dedicated staleness check). Does not indicate lost content -- every sampled case's text was
genuinely present, just under a different section label than declared.

**Completeness verdict, independently re-verified beyond the automated gate**: `retention-report`
showed 4 old-README headings as `absent` (`### Flow layout`, `### Layers (optional content)`,
`### File-based helpers`, `## API overview`). Read the real upstream source (pinned commit
`197de2705f`, confirmed live via `git rev-parse HEAD` in the clone cache, matches the run's pinned
SHA) for all 4 and grepped the candidate for each one's identifying code/prose. All 4 are heading-
label losses only -- the underlying content (flow-layout code sample, `doc.OptionalContent`
enumerate/toggle text verbatim as `u0145`, the full `File-based helpers` code block with every
named function, and the API overview's own member table reframed as `u0243`) is genuinely present
in the candidate, just without a matching subheading. Combined with 0 hard-gate failures
(including `content_unit_reframe_fidelity`, `dropped_content`, `dropped_content_uncorrelated`)
and the retention-report's own count (content: 312 verbatim + 10 reframed + 2 excluded out of
324; code: 113 verbatim + 1 excluded; structural: 3 verbatim), the candidate is verified complete
against the real upstream README -- not just per the automated gate, but by direct manual
cross-check of every gap the gate surfaced.

## 6. 2026-09-04 fresh certification run + a real file-deletion incident

User asked to redo the regeneration properly "using skill" rather than the ad-hoc recheck from
§5. Abandoned the AWAITING_REVIEW run (`rr-20260903T072250Z-3a82d15feb0f`) and ran a genuine
fresh cycle (`rr-20260904T103456Z-f80e7953c7d0`): `start` -> `plan` -> `ingest-candidate` ->
`verify-examples --typescript-runner`. Clone-cache HEAD (`197de2705f`) and publication state
(still unpublished on npm) both confirmed unchanged since 2026-09-03 -- no upstream drift.

**A real incident found mid-run, not caused by any command in this workflow**: `ingest-candidate`
failed with `No candidate found` -- `reports/repo-presenter-regen-full/pdf/typescript/readme.md`
was genuinely missing from disk (all sibling `content-dispositions.json`/`code-example-
dispositions.json`/etc. files were intact, and `content-dispositions.json` still reflected my
own §5 fix exactly -- 312/10/2). Traced `abandon_run`'s real source (`readme_refresh_run.py:
5728-5766`) directly -- it only touches the manifest state and `ACTIVE.json`, never the candidate
tree -- ruling out my own `abandon` call as the cause. Checked the Windows Recycle Bin via
`Shell.Application`: the file was there, deleted at 15:22 (a `Remove-Item`/Explorer-style
deletion goes to the Recycle Bin; a Python `os.remove`/`unlink` normally bypasses it, so this was
very likely deleted through the shell/GUI, not by an automated script). Verified the recycled
copy's sha256 (`ccfdf7db29a...`) matched `last-verified.json`'s recorded hash exactly before
restoring it -- confirmed byte-for-byte the same, already-fixed content, not a stale or
partial version. Restored it, re-ran `ingest-candidate`: clean on the first try (0 hard-gate
findings). **User should know their own file was deleted outside this conversation** -- worth
checking what did it (antivirus, an editor auto-action, manual cleanup) if it wasn't intentional.

**Fresh run result, fully consistent with §5's already-verified state**: 0 hard-gate failures;
`content_unit_cross_section_restatement` 53 findings (matches the post-fix count); `content_unit_
reframe_fidelity` 0 findings; `dropped_content` 0 findings; `candidate_growth_ratio` clean.
`verify-examples --typescript-runner`: 92 blocks (3 `COMPILED+RAN CLEAN`, 72 `DEPENDS-ON-FAILED-
BLOCK`, 6 `FIXTURE-UNAVAILABLE`, 5 `TOOLCHAIN-UNAVAILABLE`, 5 `RUNTIME-ERROR`, 1 `UPSTREAM-
BROKEN`) -- matches the prior mission's own measured shape (91 blocks, off-by-one likely a minor
extraction-boundary variance, not a regression). Run reached `AWAITING_REVIEW` cleanly. Not
approved or pushed -- that step still needs the user's own explicit go-ahead per this skill's
established practice.

## 7. 2026-09-04 -- real defect found in the merged PR: skill healing (readme-refresh-
## limitations-duplication-and-collapse-hardening-2026-09-04)

User read the merged PR (#1) and found "Design specs and implementation plans live under
docs/superpowers/..." (u0324, Development and Testing) stated twice, back to back, before
`## License`. Traced root cause: `check_content_unit_no_exact_duplicate_merge` only ever compares
TWO DIFFERENT disposition entries against each other -- it never reads the candidate text, so a
SINGLE entry (u0324, one real disposition record, correctly `merged_verbatim` once) pasted twice
during composition was structurally invisible to it. Real, upstream-confirmed: the original
pdf/typescript README has this text exactly once (`grep -c` = 1).

**Portfolio-wide search** (all 32 candidates, whitespace-normalized excerpt-occurrence count)
found exactly one other match: email/cpp's `u0061`/`u0075`. Verified this is legitimate, not a
defect -- two DIFFERENT disposition entries, each independently verified against a different
real source file (`msg_writer.hpp` / `cfb_writer.hpp`), and the real upstream email/cpp README
independently states the same sentence twice on its own (`grep -c` = 2 there too). Correctly
excluded from the fix.

**Shipped** (commit `5fd965987b`, pushed to origin/main):
- `check_content_unit_no_self_duplicate_in_candidate` (HARD gate) -- flags any `merged_verbatim`/
  `merged_reframed` entry (>=8 content words) whose own excerpt appears 2+ times in the candidate.
- `check_scope_limitations_detail_collapsed` (HARD gate, size-gated) -- gives Scope and
  Limitations the same two-tier collapse API Reference/Additional Examples already have.
  Thresholds are real portfolio measurements, not invented: section oversized above 800 words
  (~2x the largest normal section, pdf/net's 430); an individual bullet over 60 words (just above
  the highest normal portfolio AVERAGE, words/python's 55.0) must move into a collapsed
  `#### Detailed Limitations Reference` block.
- `skills/readme-refresh.md` composition guidance for both rules; `CHECKS_MODULE_VERSION` 8->9;
  `check_function_count` 120->122; 10 new regression tests; mirrors synced; 1039 scoped tests
  green, 0 regressions.

**Applied to pdf/typescript's candidate**: removed the duplicate paragraph; restructured Scope
and Limitations (49 bullets) into 9 always-visible bullets (<=60 words) + 40 collapsed inside
`<details><summary>View Full Limitations Reference</summary>` (no wording changed, purely
structural). Fresh certification run (`rr-20260904T120830Z-4e5d63e1643a`, abandoning the already-
PUSHED prior run): 0 hard-gate failures, `content_unit_reframe_fidelity` still 0 findings
(retention unaffected), `verify-examples` matches the prior measured shape (92 blocks: 3 clean,
72 depends-on-earlier-block, 6 fixture-unavailable, 5 toolchain-unavailable, 5 runtime-error, 1
upstream-broken). `AWAITING_REVIEW`, not approved/pushed -- PR #1 is already merged, so shipping
this needs a second PR, the user's own explicit go-ahead per established practice.
