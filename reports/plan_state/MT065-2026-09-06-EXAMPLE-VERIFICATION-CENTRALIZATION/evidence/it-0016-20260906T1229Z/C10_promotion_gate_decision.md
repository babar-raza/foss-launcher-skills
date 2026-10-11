# C10 promotion gate decision — it-0016-20260906T1229Z

Mission: MT065-2026-09-06-EXAMPLE-VERIFICATION-CENTRALIZATION
Taskcard: C10 "body_refresh verified-snippet selection fix"

## What shipped this iteration

`scripts/pipeline/commands/content/body_refresh.py`'s `_example_regeneration`
(the `EXAMPLE_REGENERATION` update strategy's snippet-substitution logic),
per the plan's own consumer-wiring row, rewritten with two real bugs fixed
(RC21, both explicitly named in that row):

1. **Hardcoded `*.cs` glob + unverified, filesystem-order-dependent
   selection.** Candidate snippets were selected via `snippets_dir.glob
   ("*.cs")` regardless of the page's actual platform, in raw (OS-
   dependent) glob order, with the only check being "doesn't mention the
   old symbol" -- zero proof the "replacement" was ever real, promoted,
   upstream code. Now: a real per-platform extension map
   (`_PLATFORM_SNIPPET_EXT`, verified against every platform with real
   snippet data on disk today: net→.cs, python→.py, java→.java, cpp→.cpp,
   typescript→.ts, go→.go; rust→.rs by pattern, unverified, since no real
   rust product exists on this machine), `sorted()` iteration (never raw
   glob order), and a hard requirement that the candidate have a
   `code_sha256` entry in `snippets_index` (C6's real "verify at the
   source" content-hash proof) -- see the honest-limit note below for why
   `execution_proof.tier` is a ranking signal, not a hard filter.
2. **Replaced the FIRST fence in the section, not the one containing the
   symbol.** `re.sub(r"```[^\n]*\n.*?```", ..., count=1)` blindly
   overwrote whichever code block came first in the whole section --
   proven, via the mechanical-revert check below, to be a REAL, live bug
   against this repo's actual `knowledge/pdf/net/merged/snippets/` data,
   not just a theoretical one: the old code substituted a real, unrelated
   test snippet in place of the removal marker the fixture expected. Now
   uses `lib.example_verification.code_fences.enumerate_code_blocks` (the
   canonical tokenizer) to find the SPECIFIC block whose own content
   contains `symbol`, and replaces only that block, via a new helper
   `_replace_symbol_block`.

New keyword-only parameters `platform` and `snippets_index` (matching the
plan's own proposed signature); the one real call site
(`_apply_section_update`'s `UT_EXAMPLE` branch) now also loads
`snippets_dir / "snippets_index.json"` when one exists and threads both
through.

## Honest limit, disclosed (matching C5's L-15 precedent exactly)

The plan's own consumer-wiring row asks for `execution_proof.tier >= 2`
as a selection FILTER. No product's snippet index has `execution_proof`
populated anywhere in this portfolio yet (the post-promote proof sweep
that would populate it was deferred at C6's own closure and still doesn't
exist). Hard-requiring it today would make this function ALWAYS fall
through to the removal-marker branch for the entire portfolio -- a real
regression relative to even the buggy old behavior on an LLM-driven
content-refresh path. `code_sha256` (real, populated by every `promote()`
run since C6) is used as the baseline "verified at the source" bar
instead; `execution_proof.tier` is read as an ADDITIONAL ranking signal
when present (prefer the highest tier), exactly as the plan describes,
never as a hard gate.

## Tests

8 new focused tests directly against `_example_regeneration` (not just
through the full pipeline): replaces only the symbol-referencing block in
a multi-block section; never substitutes a snippet without a verified
`code_sha256`; a generic removal marker for any change_type when no
verified candidate exists (the old code had NO fallback at all for a
non-`API_REMOVED` change_type -- it silently returned the section
unchanged, leaving stale code in place); prefers the highest
`execution_proof.tier` when present; deterministic filename tie-break
(not filesystem/glob order); platform-specific extension selection (not
hardcoded `.cs`); the pre-existing `API_REMOVED`-specific marker text is
preserved; and a full end-to-end regression guard reusing the existing
`test_api_removed_code_block_regenerated` fixture. Full suite: 82
pre-existing + 8 new = 90 passed.

**Mechanically verified, and a striking real-world confirmation of bug
#2**: reverted `body_refresh.py`'s change via `git stash`, re-ran the
full suite -- all 8 new tests failed as expected, and critically, the
END-TO-END regression test (`test_api_removed_code_block_regenerated_end_
to_end_still_works`, which runs through the REAL pipeline against this
repo's REAL `knowledge/pdf/net/merged/snippets/` data, not a synthetic
fixture) showed the OLD code silently substituting a real, unrelated C#
test snippet ("CreateUri_ProducesValidActionDict") in place of the
expected removal marker -- proving bug #2 is a REAL, live defect against
real repository data today, not a theoretical one. Restored the fix,
confirmed all 90 tests pass again.

`check_monkeypatch_lint.py`: 1 pre-existing T2 violation reported at
`test_body_refresh.py:412` (`monkeypatch.setattr(regrounding_check,
"RegroundingCache", ...)`) -- a DIFFERENT, pre-existing test this
taskcard never touched; not a new violation introduced by this change.

## Deliberately not touched (disclosed)

`_fenced_code_blocks`/`_code_block_structure_shifted` (the OTHER fence
parser in this same file, cited separately by RC19 for the SAME "~40
duplicate fence parsers" migration) is left unchanged -- out of C10's own
stated scope ("body_refresh verified-snippet selection fix," not "body_
refresh tokenizer migration"), and changing an unrelated, already-tested
function risks an unrelated regression. `_example_regeneration` uses the
canonical tokenizer directly for its OWN new logic instead.

## Disposition

Recommending CLOSE, pending independent review: the two real, disclosed
bugs (one proven live against real repository data) are fixed, tested
with 8 new focused tests plus a full-suite regression guard, and the one
deferred item (`execution_proof.tier` as a hard filter) is a deliberate,
disclosed, non-regressive deviation matching established precedent.
