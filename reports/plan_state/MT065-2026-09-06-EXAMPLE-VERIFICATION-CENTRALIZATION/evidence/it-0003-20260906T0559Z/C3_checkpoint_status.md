# C3 checkpoint status (iteration it-0003)

Card remains **IN_PROGRESS** (not advanced to IMPLEMENTED/CLOSED) -- per
the loop protocol's step 8 sanctioned pattern ("over budget with real
progress -> checkpoint what's done, leave the card IN_PROGRESS").

## Why checkpointed rather than completed this iteration

C3's full scope (extract toolchain/acquire/runners-base/python/typescript
from S-120 behind parity) covers ~340+ lines of security-sensitive,
real-subprocess/pip/venv logic for Python alone
(`_acquire_python_environment`, `_classify_python_failure`,
`_run_single_python_block`, `_stage_readme_fixtures`,
`_product_console_scripts`, `_run_bash_block`,
`python_verification_runner` -- readme_refresh_run.py:4725-5143), plus a
comparable-or-larger TypeScript chunk (`_acquire_typescript_environment`,
`typescript_verification_runner` -- :5144-5429). A faithful,
zero-regression port of this scale deserves its own careful pass(es), not
a rushed same-iteration completion alongside everything else already done
today (C1, C2 + fast-follow). `readme_refresh_run.py` and
`test_readme_refresh_run.py` are completely untouched this iteration --
the existing S-120 runners remain the live, active code path with zero
risk introduced.

## What shipped this iteration (commit `21c1281ead`)

`lib/example_verification/toolchain.py` -- the self-contained, lower-risk
piece of C3's scope per Phase 0 item 7's spec: `find()`/`version_of()`,
`maven_java_version()`, `msvc_env()`, `exec_env()`, `fingerprint()`. 14
tests, all real/local/no-network, all green.

A first commit attempt was correctly BLOCKED by Tier 1 Step 38
(subprocess-encoding-parity): 4 `subprocess.run(text=True, ...)` calls
lacked explicit `encoding="utf-8", errors="replace"` (this repo's house
style, ST-096 class). Fixed and re-verified before the successful commit.

## Real finding while building this: the plan's own toolchain inventory was wrong

`msvc_env()` correctly returned `None` on this machine. Direct inspection
found the actual cause: `VC\Auxiliary\Build\vcvarsall.bat` and `cl.exe` do
not exist anywhere under this machine's Visual Studio 2022 Community
install (only `VC\Auxiliary` + `VC\Redist` exist) -- the "Desktop
development with C++" workload was never installed, contradicting the
governing plan's "Verified toolchain inventory" table, which had called
this "Installed" with only a "cl.exe not on PATH by default" caveat.
Corrected directly in the plan file (outside this git repo's tracking, so
not subject to this taskcard's `allowed_paths`) -- see the commit message
and the plan's own corrected table row for full detail. Phase 6 (the C++
runner, C14) now needs the same kind of disclosed real-environment
prerequisite already established for Rust, not just "the repo has no code
that invokes it yet."

## What the next iteration resuming C3 should do

1. Re-claim C3 (still `IN_PROGRESS`, `dependencies: ["C2"]` already
   satisfied) -- eligibility step 6 handles "own IN_PROGRESS resume."
2. Read `readme_refresh_run.py:4725-5429` in full (already read once this
   iteration -- see this evidence run's transcript) before porting.
3. Build `acquire.py` (Workspace fixture staging ported from
   `_stage_readme_fixtures`; `classify_failure()`; `with_retry()`;
   freeze_lock/reuse_lock), `runners/base.py` (LanguageRunner protocol +
   BaseRunner tier ladder), `runners/python.py`, `runners/typescript.py`.
4. Add the byte-identical-rerun test (same run twice, report equal minus
   timings) the stage's own focused-tests column names.
5. Do NOT touch `readme_refresh_run.py`'s actual runtime dispatch yet --
   per rollout step C3's own text ("then delete the inline helpers" is
   explicitly a later step) and the rollback trigger ("keep both old and
   new runners, dispatch behind a flag, do not delete :4725-5343 yet").
   Wiring the real dispatch is C7's job ("Wire S-120 dispatch/gate/report
   to the package"), not C3's.
6. Only once `runners/python.py`/`runners/typescript.py` exist, tested,
   and proven at parity against the real functions above, advance C3
   through IMPLEMENTED -> FOCUSED_VERIFIED -> pilot (pdf/python) ->
   INDEPENDENTLY_REVIEWED -> CLOSED.
