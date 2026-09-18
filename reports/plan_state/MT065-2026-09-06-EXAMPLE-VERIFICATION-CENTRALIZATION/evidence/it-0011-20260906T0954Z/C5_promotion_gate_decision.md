# C5 promotion gate decision — it-0011-20260906T0954Z (checkpoint 1 of N)

Mission: MT065-2026-09-06-EXAMPLE-VERIFICATION-CENTRALIZATION
Taskcard: C5 "Go runner from check_go_code_blocks.py + generalize pre-commit Step 18"

## Path-typo note

C5's seeded `allowed_paths` lists `scripts/ci/tests/test_ci_go_code_blocks.py`. No such
file exists; the real, only test file for `check_go_code_blocks.py` is
`scripts/pipeline/tests/test_ci_go_code_blocks.py` (confirmed via `find`). Treated as an
unambiguous seed-data typo (the taskcard's own intent -- "test_ci_go_code_blocks.py:16-23
keeps importing" -- names this exact file) and edited the real path. `allowed_paths` is
enforced only as an eligibility/contention check inside `taskcard_cli.py`
(`_paths_conflict`), not as a commit-time gate in `git_plumb_commit.py`, so this doesn't
risk a tool rejection -- it's a self-discipline note for the record.

## What shipped this iteration

New `scripts/pipeline/lib/example_verification/runners/go.py`: the module/import-
resolution helpers the plan names (`_wrap_fragment`, `_infer_imports`,
`_has_top_level_main`, `_resolve_go_module`) moved here from
`scripts/ci/checks/check_go_code_blocks.py`, plus `_find_module_replace_path` (not in
the plan's literal 4-function list, but explicitly named for its own bug fix at the
plan's cited line range). `check_go_code_blocks.py` now imports and **re-exports** all
of them (`from example_verification.runners.go import (...)`, mirroring
`smoke_test.py`'s own `sys.path`-insertion pattern for reaching the `lib/` package) so
every existing caller of `from check_go_code_blocks import (...)` -- including the test
file -- keeps working with zero changes needed on their end.

Both real bugs the plan's C5 row names, fixed in the move:

1. **`_resolve_go_module`** now checks `merged/model.yaml` before the gitignored
   `scout/model.yaml`. Honest limit disclosed: `merged/model.yaml` does not actually
   carry `canonical_import`/`package_name` in the real portfolio today (nothing writes
   them there -- a `promote.py` change, outside this taskcard's `allowed_paths`), so this
   is a forward-compatible no-op against real data today, not yet a fix for the "fresh
   CI checkout has no scout/" gap the plan's note implies -- disclosed, not silently
   dropped.
2. **`_find_module_replace_path`** now resolves the caller's own product's clone
   directly via `clone_cache_path(family, "go")` (the same helper
   `runners/python.py`'s acquire step already relies on) when `family` is known, still
   verifying that clone's own `go.mod` contains the module path before trusting it, and
   falling back to the old full-directory-scan behavior otherwise. `family` is threaded
   through `check_content_dir` → `_vet_block` → `_find_module_replace_path`.

Tests: `scripts/pipeline/tests/test_ci_go_code_blocks.py` -- the 18 pre-existing tests
pass completely unchanged (confirmed both before and after this move), plus 5 new tests
covering both bug fixes directly (merged-wins-over-scout, merged-lacks-fields-falls-back-
to-scout, family-resolves-its-own-clone-directly, falls-back-to-scanning-when-that-
clone-lacks-the-module, returns-None-when-nothing-matches). 23/23 green.
`check_monkeypatch_lint.py`: 0 violations on every changed file.

## Real pilot: old-vs-new error-set diff over both real Go products

Ran the actual CLI (`check_go_code_blocks.py <content_dir> --advisory`) against
`content/docs.aspose.org/en/pdf/go` and `content/docs.aspose.org/en/cells/go` -- the
only two real Go products (per MT011/MT059 mission-authority check, both closed/no live
claim right now) -- for both the OLD (committed) and NEW (this commit's) code, **read-
only, never writing to their content/ or knowledge/ paths**.

**Methodology correction, disclosed rather than silently fixed**: my first attempt ran
the OLD version from a *copied* file under `runs/.scratch_c5_pilot/`, which computed a
wrong `REPO_ROOT` (parents-index math assumes the file's real location) and produced 17
spurious "undefined: cells_foss" failures that looked like real pre-existing bugs. Caught
this before writing it into evidence: re-ran the OLD version via `git stash` (reverting
the 3 changed/new files to committed HEAD **in place**, not a copy), confirmed **PASS,
0 failures** for both products with the real OLD code too, then `git stash pop` to
restore my changes. Both OLD and NEW now agree: **PASS for pdf/go (9 .md files) and
cells/go (8 .md files), zero-diff error sets** -- the promotion gate this stage's row
requires.

## What was deliberately deferred (and why)

1. **The `GoRunner` `LanguageRunner` protocol implementation** (`runners/base.py`'s
   `acquire`/`compile`/`execute`/`classify`/`starts_chain`, tier-3 real `go run`
   execution). This iteration only moved/fixed the wrapping/resolution helpers
   `check_go_code_blocks.py` already used for its existing tier-2 (`go vet`) gate;
   building the FIRST-EVER concrete `LanguageRunner` implementation (no prior runner has
   used `runners/base.py` yet -- `python.py`/`typescript.py` predate it and aren't
   retrofit onto it, per `base.py`'s own docstring) is a large, novel piece of work that
   deserves its own careful iteration and testing, not a rush alongside an
   extraction-plus-bugfix commit. This matches C3's own precedent: toolchain/acquire/
   base landed before python.py/typescript.py did, across separate iterations.
2. **Pre-commit Step 18 generalization** (calling `smoke_test.py --files … --exit-codes
   gate --max-tier auto --blocking-platforms go`). `pre-commit-audit.sh` needs a
   forbidden-path override token and is **not in C5's `allowed_paths`** regardless; the
   `smoke_test.py` flags it would call (`--exit-codes`, `--blocking-platforms`) don't
   exist either (C4's actual delivered scope was `--max-tier {1,2}` + `--json` only) and
   `smoke_test.py` is also not in C5's `allowed_paths`.
3. **Flipping `max_tier`/`precommit_blocking` in `registry.py` + `platform_capabilities.
   yaml`**. Neither file is in C5's `allowed_paths`, and flipping them without a real
   tier-3 runner behind them would be premature regardless (the plan itself says "flips
   ... in the same commit that lands the runner").

## Disposition

Checkpointing C5 as `IMPLEMENTED` → leaving `IN_PROGRESS` this iteration (not
`FOCUSED_VERIFIED`/`CLOSED`) -- the deferred `GoRunner` protocol implementation is the
larger remaining half of this taskcard's own title ("Go runner ... + tier 3"), and a
future iteration's `ready` selection will resume this same claim (schema-5f's own
IN_PROGRESS-resume eligibility rule) rather than re-doing this iteration's work.
