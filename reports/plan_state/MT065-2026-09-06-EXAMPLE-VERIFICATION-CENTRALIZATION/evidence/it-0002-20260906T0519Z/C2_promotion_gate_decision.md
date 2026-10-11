# C2 promotion-gate decision

Stage matrix row (governing plan): focused tests (schema round-trip;
legacy-adapter equality vs. fixture dicts; cache hit/miss/stale matrix;
`code_syntax_check` corpus WARN/FAIL counts before/after the loader fix) /
pilot scope "none yet (library-only)" / promotion gate "corpus delta
recorded and explicitly accepted, not silently absorbed" / rollback
trigger "new FAIL count exceeds the accepted delta → keep old loader
behind a flag."

## What shipped (within C2's allowed_paths)

- `lib/example_verification/registry.py` (new): `PLATFORM_CONTRACT`,
  `RUNNABLE_LANGS_BY_PLATFORM`, `NON_EXECUTABLE_LANGS`.
- `lib/example_verification/syntax.py` (new): the ONE shared tree-sitter
  loader (wheel-then-language-pack fallback for java/csharp/typescript/
  javascript/cpp/rust/go/python) + `check_syntax()` (PASS tier 1 |
  SYNTAX-ERROR | loud GRAMMAR-UNAVAILABLE).
- `lib/example_verification/result.py` (new): `BlockIdentity`,
  `BlockResult`, `VerificationReport`, `to_legacy_s120()` (matches
  `test_readme_refresh_run.py`'s asserted dict shapes exactly), `to_smoke()`.
- `lib/example_verification/policy.py` (new): `Policy`, `Timeouts`,
  `ProductContext` (`from_factpack`/`from_knowledge`).
- `lib/example_verification/cache.py` (new): `ResultCache`, `CacheEntry`,
  `cache_key()`, `stale_reason()` — never-cache list enforced
  (TOOLCHAIN-UNAVAILABLE, TIMEOUT, BUDGET-EXHAUSTED confirmed un-cacheable
  by test).
- `commands/diagnostics/smoke_test.py`: loader now delegates to the shared
  `syntax.py` module (its own ~90-line duplicate loader deleted); the
  silent-PASS-on-missing-grammar bug (`:424-434`, pre-fix) is fixed to a
  loud WARN with a `GRAMMAR-UNAVAILABLE` message. Public function names
  (`_ts_parser_for`, `_run_ts_parse`, `_first_error_node`, `_TS_LANG_MAP`)
  kept intact for `test_smoke_test.py`'s existing imports (that file is
  outside C2's `allowed_paths`) — C4's full CLI rebuild is the point where
  this file's remaining internals move onto the package properly.
- 6 new test files (109 tests total in this iteration, all green):
  `test_example_verification_{registry,syntax,result,cache,policy,
  smoke_test_integration}.py`. Scoped regression also re-run:
  `test_smoke_test.py` (34), `test_rust_platform_maps.py`,
  `test_platform_capability_matrix.py` (268) — all green, no regression.

## The corpus measurement (per the stage's explicit instruction)

Ran a real portfolio-wide, read-only comparison of `code_syntax_check.py`'s
current live loader vs. the new shared loader across every java/typescript/
cpp content page (59,180 files, 31,555 blocks reaching real classification
logic). Full writeup: `C2_code_syntax_check_corpus_finding.md` in this
directory. Headline: **code_syntax_check.py currently performs ZERO real
tree-sitter parses for these three languages, portfolio-wide** (100%
WARN-only bracket-heuristic fallback); wiring the shared loader would
newly surface 30,341 real PASSes and 533 real FAILs.

## Decision: do NOT wire `code_syntax_check.py` to the shared loader this iteration

Two independent reasons, either one sufficient on its own:

1. **Scope**: wiring it live requires bumping `EVALUATOR_LOGIC_VERSION` /
   `EVALUATOR_FREEZE_VERSION` in `content_eval/__init__.py` (this repo's
   frozen-canonical-evaluator discipline) — that file is not in C2's
   `allowed_paths` (it is only in **C8**'s, per the taskcard seed rows).
2. **The delta itself isn't a clean "these are all real bugs" set**:
   direct reads of 2 sampled "new FAIL" blocks found two distinct
   false-positive root causes (an intentional `...` ellipsis-placeholder
   documentation convention in Java; a CMake build script mislabeled with
   a `cpp` fence tag) mixed in with what are presumably some genuine
   syntax defects — exactly the kind of undifferentiated batch the
   promotion gate's own wording ("recorded and explicitly accepted, not
   silently absorbed") warns against switching live sight-unseen.

`code_syntax_check.py` is therefore untouched in this commit; `syntax.py`
ships tested and ready for whoever takes on the follow-up (C8, or a new
card if the mission wants the ELV bump + delta-triage split out
separately) to wire it, using the ready-made `check_syntax()` API.

## Explicitly deferred to later taskcards (not a gap in C2)

- `code_syntax_check.py` wiring + `EVALUATOR_LOGIC_VERSION`/
  `EVALUATOR_FREEZE_VERSION` bump — needs `content_eval/__init__.py`,
  which is C8's allowed_paths, not C2's.
- Triaging the 533-block FAIL delta by root cause (genuine defect vs.
  ellipsis-placeholder vs. mislabeled-fence-tag vs. others unsampled)
  before or immediately after that switch.
- A backlog entry for the mislabeled-fence-tag and ellipsis-placeholder
  findings — `backlog/inbox.md` is outside every C-taskcard's
  `allowed_paths` seen so far; drafted narrative is preserved in
  `C2_code_syntax_check_corpus_finding.md` for whoever files it.
