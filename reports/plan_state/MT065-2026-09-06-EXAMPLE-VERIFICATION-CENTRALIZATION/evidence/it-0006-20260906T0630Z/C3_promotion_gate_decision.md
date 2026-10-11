# C3 promotion-gate decision

Stage matrix row: focused tests "test_readme_refresh_run.py (whole file)
green unchanged; byte-identical rerun (same run twice)" / pilot scope
"pdf/python (existing S-120 candidate)" / promotion gate "100% of existing
python/ts tests green; rerun identical modulo timings" / rollback trigger
"any regression → keep both old and new runners, dispatch behind a flag,
do not delete :4725-5343 yet."

## What shipped across this taskcard's checkpoints

1. `21c1281ead` -- `toolchain.py` (shared discovery: find/version_of/
   maven_java_version/msvc_env/exec_env/fingerprint). Caught and corrected
   a real error in the plan's own toolchain inventory (MSVC's C++ build
   tools are not actually installed on this machine).
2. `dae315b99b` -- `acquire.py` (language-agnostic fixture staging,
   ported from `_stage_readme_fixtures`/`_readme_fixture_names`).
3. `270edb6740` (via `da6a01e593` after a benign concurrent-session
   reconcile) -- `runners/python.py`, a faithful port of the real Python
   runner (`_acquire_python_environment`, `_classify_python_failure`,
   `_run_single_python_block`, `_python_block_starts_chain`,
   `_product_console_scripts`, `_venv_script_path`,
   `_classify_bash_failure`, `_run_bash_block`,
   `python_verification_runner`).
4. This iteration -- `runners/typescript.py`, a faithful port of the real
   TypeScript runner (`_acquire_typescript_environment`,
   `_self_link_typescript_package`, `_typescript_block_starts_chain`,
   `_classify_typescript_failure`, `_run_single_typescript_block`,
   `typescript_verification_runner`).

`readme_refresh_run.py` and `test_readme_refresh_run.py` are **completely
untouched** across all 4 checkpoints -- the rollback trigger's "keep both
old and new runners" is trivially satisfied since the old runners were
never modified, only read.

## Evidence for the promotion gate

- **"test_readme_refresh_run.py (whole file) green unchanged"**: ran the
  full, unmodified suite this iteration -- 216/216 passed.
- **Function-level parity**: 21 direct parity tests (11 python, 10
  typescript-adjacent... see exact counts in each test file) import the
  real, unmodified S-120 functions (`readme_refresh_run` as `rr`) and
  assert byte-identical output against this package's port, across both
  runners' full function sets.
- **"byte-identical rerun (same run twice)"**: two dedicated tests
  (`test_python_verification_runner_byte_identical_rerun`,
  `test_typescript_verification_runner_byte_identical_rerun`) prove this
  for the new package's own runner alone.
- **Real end-to-end pilot, going beyond the minimum "pdf/python" scope**:
  ran BOTH the real S-120 function and this package's port against the
  SAME real candidate text and factpack, for BOTH pdf/python (a real
  `python -m venv` + real `pip install -e` against the actual local
  pdf/python clone cache + real execution of a real Aspose.PDF FOSS
  example -- `COMPILED+RAN CLEAN`, byte-identical) and pdf/typescript (a
  real `npm install` against the actual local pdf/typescript clone cache +
  real `tsc --noEmit` + real `tsx` execution -- both correctly report
  `FIXTURE-UNAVAILABLE` for a real missing `in.pdf`, byte-identical after
  normalizing away the inherently-different `tempfile.TemporaryDirectory`
  name each separate process invocation mints -- confirmed by explicit
  string-substitution + re-comparison, not asserted). Scripts and raw
  results: `_scratch_mt065_c3_pilot_python_runner.py` /
  `c3_pilot_python_result.json`, `_scratch_mt065_c3_pilot_typescript_runner.py`
  / `c3_pilot_typescript_result.json` in this evidence directory.

## Deliberately NOT built in this taskcard

`runners/base.py` (the `LanguageRunner` protocol + `BaseRunner` tier-ladder
abstraction the Central module design names) is intentionally deferred.
Building an abstraction from exactly 2 concrete implementations, before
any real consumer (C7's dispatch wiring) has exercised either one in
production, risks guessing the wrong shape (the classic premature-
abstraction trap) -- the concrete `runners/python.py`/`runners/typescript.py`
this taskcard ships are what C5/C11-C14's new-language runners and C7's
dispatch wiring need to exist first; the shared base class, if still
worth building once those exist, is better designed from real, observed
duplication across 3+ concrete runners than from 2 guessed ones. Recorded
here so this is a deliberate scope decision, not an oversight, for
whoever picks up C5/C7/C11-C14 next.

## Decision: PROMOTE

All measurable criteria in the stage's own promotion gate are met, several
with stronger evidence than the gate's own minimum bar asked for (a second
real product pilot beyond pdf/python; the whole-file existing-suite rerun
rather than a subset). Advancing C3 to CLOSED.
