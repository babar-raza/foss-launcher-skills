# C4 promotion-gate decision

Stage matrix row: focused tests "test_smoke_test.py; zero-network
assertion at default tier; check_platform_capabilities.py" / pilot scope
"font/python via a real /eval-page step-2b dry run" / promotion gate
"step-2b latency unchanged at default tier; exit codes 0/1/2 preserved" /
rollback trigger "latency regression or exit-code change → keep old CLI
flags as aliases."

## What shipped across this taskcard's 4 commits

1. `acd165e07e` -- registry.yaml registration for the whole
   `lib/example_verification/` package (11 files); platform_capabilities.yaml
   gains the `example_verification` site for all 7 platforms +
   `check_platform_capabilities.py::check_example_verification()`; RC20 fix
   (Go code blocks were silently smoke-tested as Python).
2. `45deb20747` -- `--max-tier {1,2}` and `--json` CLI flags; RC22 fix
   (a bare `--files` invocation -- the exact shape `/eval-page`'s step 2b
   and this skill's own doc use -- auto-detects languages from file
   content instead of hardcoding Python).
3. `bfb51f5576` -- skills/code-smoke.md + 3 provider mirrors updated to
   document all of the above honestly (including what's *not* built yet).

## Evidence for the promotion gate

- **test_smoke_test.py**: 48/48 pass (12 new: TestMaxTier, TestJsonReport,
  TestDetectLangsInFiles), including explicit tests that max_tier=2 (the
  default) is byte-identical to calling `check_file()` with no max_tier
  argument at all.
- **zero-network assertion at default tier**: confirmed by inspection --
  no new subprocess/network call was added to the max_tier=2 code path
  (mypy/py_compile/tree-sitter are the same local calls as before).
- **check_platform_capabilities.py**: PASS, 0 findings; verified the new
  `check_example_verification()` genuinely detects a deliberately
  introduced mismatch (not vacuously passing).
- **Real /eval-page step-2b pilot against font/python**: loaded the pre-C4
  module (commit `b76392b9f3`) side-by-side with the current one and ran
  both against the exact documented step-2b command. `old_result ==
  new_result` → **True** (byte-identical `SmokeResult`). 5 separate
  latency measurements, all in the same ~1.4-1.75s band. Full writeup:
  `C4_eval_page_pilot.md` in this directory.
- **Exit codes 0/1/2 preserved**: confirmed directly (pilot run returned
  0; `_exit_code_for()` is the one shared function both `print_report()`
  and the new `print_json_report()` call, so they can never disagree).

## Deliberately NOT built in this taskcard (disclosed, not silently dropped)

- **Tier 3 (real execution) dispatch**: `--max-tier` today only
  distinguishes syntax-only (1) from syntax+mypy (2, the original
  default). A real execution tier exists in
  `lib/example_verification/runners/{python,typescript}.py` (built in
  C3) but isn't dispatched from this CLI -- it needs a stable `api.py`
  entrypoint (the Central module design's own `verify_blocks`/
  `verify_markdown`), which no taskcard has built yet. Wiring a
  `--acquire`/tier-3 flag ahead of that entrypoint existing would mean
  either duplicating dispatch logic here or coupling this CLI directly to
  the runners package's internals -- both premature.
- **`--exit-codes gate`, `--snippets`, `--stamp-index`, `--census`,
  `--blocking-platforms`**: each depends on infrastructure a *different*,
  not-yet-closed taskcard owns (refresh_run wiring is C9's job; the
  snippet index is C6's; a real consumer for `gate`-mode exit codes
  doesn't exist until C9 wires it either). Building speculative CLI
  surface for callers that don't exist yet risks guessing the wrong
  shape -- the same reasoning C3's `runners/base.py` deferral used,
  applied here to CLI flags instead of a base class.
- **`docs/registries/skills.md`**: checked, left unchanged -- its existing
  one-line description ("Syntax and type-check code blocks") is still
  accurate and not overclaiming; no edit was needed.

## Decision: PROMOTE

Every measurable criterion in the stage's own promotion gate is met, with
real, direct evidence (a real old-vs-new pilot run, not just unit tests).
Advancing C4 to CLOSED.
