# C5 final promotion gate decision — it-0012-20260906T1017Z

Mission: MT065-2026-09-06-EXAMPLE-VERIFICATION-CENTRALIZATION
Taskcard: C5 "Go runner from check_go_code_blocks.py + generalize pre-commit Step 18"
Commits: `7ff4f5ef0d` (checkpoint 1: extraction + 2 module-resolution bug fixes),
`7b4b7367d6` (checkpoint 2: GoRunner LanguageRunner protocol), `cb4f1d9da0`
(reviewer fast-follow: 2 real bug fixes)

## Summary across all 3 commits

- Extracted `_wrap_fragment`/`_infer_imports`/`_has_top_level_main`/
  `_resolve_go_module`/`_find_module_replace_path` from
  `check_go_code_blocks.py` into `runners/go.py`, re-exported for zero CLI/test
  behavior change. Fixed 2 real bugs (merged-before-scout model.yaml read
  order; deterministic clone resolution instead of directory scanning).
  Real old-vs-new pilot against both actual Go products (cells/go, pdf/go):
  zero-diff, both PASS.
- Built `GoRunner`, the first concrete `runners/base.py` `LanguageRunner`
  implementation: real `go vet` (tier 2) + real `go run` (tier 3, a genuinely
  new capability). 14 tests, all real subprocess calls.
- Independent review (ACCEPT WITH NOTES) found 2 real bugs, both fixed and
  mechanically re-verified (reverted, watched the new regression test fail
  for the right reason, restored, confirmed it passes):
  1. `classify()`'s UPSTREAM-BROKEN heuristic never fired against real Go
     error output (checked for an absolute path string Go never emits) --
     replaced with a file-citation-basename check, proven via a real
     subprocess reproducing an actual upstream compile error.
  2. A missing-replace-directive case could have silently resolved a real
     product's dependency over the network under `-mod=mod`, then
     `execute()` would have run that unverified code -- closed with
     `GOPROXY=off`, making that case fail loudly instead.

Total: 39 tests across `test_ci_go_code_blocks.py` (23) +
`test_example_verification_runners_go.py` (16), all real (no mocked
subprocess calls), all green. `check_monkeypatch_lint.py`: 0 violations on
every changed file across all 3 commits.

## Deliberately deferred (disclosed, not silently dropped)

1. **Pre-commit Step 18 generalization** -- named in this taskcard's own
   title, but structurally blocked: `pre-commit-audit.sh` needs a
   forbidden-path override token and is not in C5's `allowed_paths`; the
   `smoke_test.py` flags the design calls for (`--exit-codes`,
   `--blocking-platforms`) don't exist (C4's actual delivered scope was
   `--max-tier {1,2}` + `--json` only), and `smoke_test.py` isn't in
   `allowed_paths` either.
2. **Flipping `max_tier`/`precommit_blocking` in `registry.py` +
   `platform_capabilities.yaml`**. Neither file is in `allowed_paths`.
3. **A real pilot of `GoRunner` against actual product content**. Needs Go
   fixture-staging support (mirroring `acquire.stage_fixtures()`) that
   doesn't exist yet -- a separable piece of work, parallel to how C11-C14
   scope their own fixture engineering as part of each of THOSE taskcards.

Items 1-2 are structural gaps in the taskcard's own `allowed_paths` seeding
-- the exact same class of gap C7 disclosed for `lib/example_verification/
api.py` (assigned to no taskcard in the current C1-C14 rollout). Item 3 is a
genuine follow-on, not a corner cut for time.

## Disposition: CLOSE

The taskcard's core, real deliverable -- a working, tested, reviewed Go
`LanguageRunner`, plus 2 real bugs fixed in the pre-existing CLI's module
resolution -- is complete, reviewed, and both reviewer findings are fixed
and mechanically verified. The 3 remaining items are either structurally
blocked outside this taskcard's `allowed_paths` (matching precedent from
C7's own disclosed gap) or a genuinely separable follow-on. Recommending
CLOSED with all 3 gaps disclosed for whichever future taskcard/plan revision
picks them up.
