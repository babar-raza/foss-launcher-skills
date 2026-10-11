# C9 promotion gate decision — it-0015-20260906T1214Z

Mission: MT065-2026-09-06-EXAMPLE-VERIFICATION-CENTRALIZATION
Taskcard: C9 "refresh_run advisory validation field"

## What shipped this iteration

`scripts/pipeline/commands/ops/refresh_run.py`:

1. Added `"example_execution"` to `ADVISORY_VALIDATION_FIELDS` (alongside
   the existing `"truth_audit"`), with an explanatory comment following
   that field's own established rationale style: no portfolio-wide
   measurement of how many real pages would newly WARN/FAIL under this
   check exists yet, matching the governing plan's own "advisory first,
   then hard -- per consumer, each in its own commit, after one recorded
   portfolio measurement" posture (Round 4 Decision 5).
2. Added an `"example_execution"` entry to `scoped_commands` (not the
   separate, single-shot `commands` dict `truth_audit` uses -- this field
   needs to run PER FILE over the run's own scope, matching
   `content_audit`/`link_validation`'s existing shape, so it correctly
   gets the same 40-per-chunk Windows-argv-length protection those two
   already have). The command: `smoke_test.py --files <chunk...> --json`
   -- bare `--files` with no explicit family/platform, so each file's own
   languages are auto-detected from its real fence tags (the RC22 fix C4
   already shipped), correct for a scope that can span more than one
   platform's pages. Deliberately omits `--max-tier`, letting the CLI's
   own default (2: syntax + Python mypy type-check) apply -- `--max-tier
   3` isn't even a valid `argparse` choice yet (confirmed by reading
   `smoke_test.py`'s own `choices=("1", "2")`), since no taskcard has
   wired real per-block execution into this CLI's dispatch.

## Real-CLI-shape verification (before writing any code)

Read `smoke_test.py`'s own current `argparse` definition and exit-code
logic directly rather than trusting the plan's own literal prefix list
(`[python, smoke_test.py, family, platform, "--json", "--exit-codes",
"gate", "--max-tier", "2", "--files"]`), since C4's own actual delivered
scope (per `C4_promotion_gate_decision.md`) never built `--exit-codes`/
`--blocking-platforms` at all. Confirmed: `--max-tier` only accepts `"1"`/
`"2"`; exit codes are a fixed 0(PASS)/1(WARN)/2(FAIL), not the plan's
0/1/3 "gate" scheme. Designed the real, working invocation around what
actually exists today, following the SAME `(prefix, suffix)` shape
`content_audit`/`link_validation` already use (prefix ending in
`--files`, chunk of paths inserted by the existing loop, `--json` as
suffix) rather than the plan's literal, partially-unbuildable list.

## Tests

New `test_verify_records_example_execution_as_advisory_not_blocking`
(mirrors the existing `test_verify_records_truth_audit_as_advisory_not_
blocking`, adapted for the scoped/chunked mechanism this field actually
uses, since `example_execution`+scoped-chunking is a combination no
existing field has -- `truth_audit` is advisory-but-unscoped, `content_
audit`/`link_validation` are scoped-but-blocking). Real command-runner
stub matches on `smoke_test.py`'s own script name, returns a real FAIL
exit code, and the test proves the FAIL is recorded in
`manifest["validation"]` but never blocks `READY_TO_COMMIT`.

Also updated the existing load-bearing chunking regression test,
`test_verify_run_chunks_every_scoped_validator_for_a_large_scope`
(proves NO scoped validator ever receives more than 40 paths in one
call), adding `"smoke_test.py"` to its `scoped_scripts` tuple -- this
test's own stated purpose is proving chunking for EVERY scoped validator,
so leaving the new field out of it would have left the exact regression
class it exists to catch unverified for the one field added this
iteration.

Both new/changed tests mechanically verified: reverted `refresh_run.py`'s
change via `git stash`, confirmed both tests fail for the right reason
(the new advisory test errors because `example_execution` is never
recorded at all; the chunking test's own `set(...) == set(...)` assertion
fails because `smoke_test.py` was never called), restored the fix,
confirmed all 117 tests (116 pre-existing + 1 new) pass again.
`check_monkeypatch_lint.py`: 0 violations.

## Deliberately not built (disclosed)

The plan's own consumer-wiring table describes this as ADVISORY ONLY for
now ("advisory → later differential-blocking, the truth_audit posture") --
no hard-gate/blocking version is built here, matching that explicit,
intended design, not a scope cut.

## Disposition

Recommending CLOSE: this is a small, self-contained, low-risk addition
(2 lines of real logic plus one explanatory comment) that reuses an
already-proven mechanism (`scoped_commands`' chunking loop,
`ADVISORY_VALIDATION_FIELDS`' exclusion) rather than inventing anything
new, verified against the CLI's REAL current shape (not the plan's
partially-aspirational one), and both new/changed tests are mechanically
proven to catch a real regression if this were ever reverted.
