# C8 promotion gate decision — it-0017-20260906T1256Z

Mission: MT065-2026-09-06-EXAMPLE-VERIFICATION-CENTRALIZATION
Taskcard: C8 "example_execution content_eval evaluator (EXPERIMENTAL+DEFAULT)"

## What shipped this iteration

New `scripts/pipeline/content_eval/evaluators/example_execution.py` (category
`EX`), the first content_eval consumer of the centralized
`lib.example_verification` package (`api.py` does not exist yet -- a real,
disclosed gap noted in `readme_refresh_run.py:5477-5481` by an earlier
taskcard -- so this evaluator imports the concrete submodules directly:
`code_fences.enumerate_code_blocks`, `registry.NON_EXECUTABLE_LANGS`,
`syntax.check_syntax`).

Two independent, inherit-first signals per code block:

1. **`lookup_proof`**: an exact `sha256_norm` match against this product's
   `snippets_index.json`, the identical map-then-lookup shape
   `audit/snippets.py:verify_snippet_coverage` (C6) already uses. A match
   with a populated `execution_proof` is INFO "inherited" (WARN "stale_by"
   if its `clone_head`/`runner_version` no longer match this product's
   current state, checked via `core.clone_cache.clone_head_sha` and
   `lib.example_verification.RUNNERS_MODULE_VERSION`, never fabricated when
   the current value can't be determined); no match, or a match with no
   `execution_proof` yet, is WARN "novel-unverified". When the product's
   whole index has no `code_sha256` anywhere (today: 0 of ~32 real products,
   per C10's own live measurement) this degrades to ONE page-level INFO
   "SKIPPED" notice -- mirroring `audit/snippets.py`'s own established SKIP
   convention -- rather than a WARN per block, so this feature's real
   contribution today is silent-by-design until a product is (re)promoted
   past C6, at which point it activates automatically with no code change.
2. A live tier-1 syntax check via the centralized `syntax.check_syntax` --
   this evaluator never acquires, so it can never itself produce proof above
   tier 1 (only *inherited* proof can carry tier 2/3, hence "inherit-first").
   FAILs only when a real parse ran and found a genuine `SYNTAX-ERROR`; a
   missing grammar (`GRAMMAR-UNAVAILABLE`, proof_tier=0) is a WARN, never a
   FAIL and never silent, since no check actually ran.

`configure(max_tier=2, allow_acquire=False, budget=60.0)` test seam (the
`module_compilability.py` precedent). A real bug caught by my own tests
before being declared correct: an early draft treated `execution_proof.tier
> max_tier` as "reject inherited proof, report novel-unverified" -- backwards,
since a higher inherited tier is strictly *more* trustworthy, never less;
`max_tier` only ever ceilings this evaluator's own live checks (which never
exceed tier 1 regardless). Caught by `test_exact_match_with_execution_proof_
is_inherited_info` failing with a tier-3 fixture against the default
`max_tier=2`, fixed by removing the tier-ceiling rejection from
`_lookup_proof` entirely.

Registered in `evaluators/__init__.py` (`_ensure_loaded`), and in
`config.py`'s `ALL_EVALUATORS`, `EXPERIMENTAL_EVALUATORS`, and
`DEFAULT_EVALUATORS` (the `code_block_api` precedent) -- **deliberately
absent** from `CANONICAL_EVALUATORS`, so `models.py`'s grade computation
(confirmed by reading `models.py:304` and `:414` before writing this module)
structurally never sees its findings. Added `"example_execution": "1"` to
`content_eval/__init__.py`'s `EVALUATOR_VERSIONS` dict for future-bump
tracking (not required by precedent -- `module_compilability`,
`private_api_usage`, and several other existing evaluators have no entry
there -- added anyway for hygiene since the file was already in scope).

## Tests

16 new focused tests in `scripts/pipeline/tests/content_eval/
test_example_execution.py`, covering: registration (EXPERIMENTAL + DEFAULT,
never CANONICAL); the no-index-at-all degrade-to-one-INFO path (today's real
portfolio state); per-block lookup once an index exists (inherited / stale_by
/ novel-unverified, including the "matched but execution_proof not populated
yet" case that is the actual real-world shape today); the max_tier
non-downgrade fix above; live syntax FAIL/PASS for Python and Java, a
GRAMMAR-UNAVAILABLE WARN for an unknown language tag; budget exhaustion
(one WARN, no further per-block checks); and a missing/None `knowledge`
object producing no findings (never crash). All 16 pass.

Ran `pytest scripts/pipeline/tests/content_eval/ -k "registry or config or
evaluator_versions or manifest or grade"` (13 tests) as the scoped regression
subset for the shared registration files touched -- all pass.

## Pilot (real pages, read-only -- never writes without --write-grade)

Ran the real CLI (`commands/content/run_content_eval.py evaluate`) against
one real, currently-published page per platform named in this stage's own
matrix row ("a real java/ts/cpp page"):

- `content/docs.aspose.org/en/cells/java/developer-guide/working-with-cells-foss.md`
- `content/docs.aspose.org/en/pdf/typescript/developer-guide/annotations.md`
- `content/docs.aspose.org/en/cells/cpp/developer-guide/working-with-cells-foss-model.md`

Scoped to `--evaluators example_execution`: all three produced exactly one
INFO ("SKIPPED... no code_sha256 yet") and zero WARN/FAIL -- no crash, no
false positive, matching every real product's actual state today.

Ran the java page again with the FULL default evaluator set (no
`--evaluators` filter): `example_execution` appears in `evaluators_run`,
contributes exactly one `EX` finding, and every other evaluator's own
finding count/category is unchanged from what this evaluator's absence would
produce (categories present: `EG, FT, CG, IR, CPA, EX` -- no collision, no
crash). Confirms the corpus FAIL-count diff this stage's own promotion gate
asks for: **zero** new FAILs introduced on any of the three pilot pages.

## Promotion gate

"EXPERIMENTAL only; zero canonical-grade change confirmed" -- satisfied
structurally (absent from `CANONICAL_EVALUATORS`, verified by reading
`models.py`'s grade-computation filter before writing this module) and
empirically (the three-platform pilot above: zero FAIL on any real page,
and the evaluator's own category is invisible to grade computation by
construction).

## Deliberately not touched (disclosed)

- `code_syntax_check.py` still carries its own private, duplicated
  tree-sitter loader (not migrated to `lib.example_verification.syntax`) --
  that migration is a different, already-CLOSED taskcard's (C2's) stated
  scope, not C8's; out of C8's `allowed_paths` regardless.
- `registry.py`'s `PLATFORM_CONTRACT` still reports `max_tier=1,
  offline_tier=1, runner=None` for go/net/java/rust/cpp even though C5/C11/
  C12 (Go/.NET/Java runners) are CLOSED -- those taskcards did not flip
  `registry.py` in their own commits despite the plan's rollout-sequence text
  asking for it "in the same commit." Observed while reading `registry.py`
  for this taskcard's own `NON_EXECUTABLE_LANGS` import; out of C8's scope
  and `allowed_paths` to fix (registry.py is not listed there) -- noted here,
  not silently ignored, for a future taskcard/session to reconcile.

## Disposition

Recommending CLOSE, pending independent review: both signals work as
designed against real portfolio data, the evaluator is structurally and
empirically grade-neutral, one real bug in my own first draft (the
max_tier-downgrade logic error) was caught by my own tests and fixed before
being declared correct, and the two "not touched" items above are genuine
pre-existing gaps in other, already-closed taskcards -- disclosed, not
silently absorbed into this one.
