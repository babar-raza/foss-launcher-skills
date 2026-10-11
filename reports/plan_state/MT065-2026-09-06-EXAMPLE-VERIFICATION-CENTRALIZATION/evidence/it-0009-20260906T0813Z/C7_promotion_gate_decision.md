# C7 promotion gate decision — it-0009-20260906T0813Z

Mission: MT065-2026-09-06-EXAMPLE-VERIFICATION-CENTRALIZATION
Taskcard: C7 "Wire S-120 dispatch/gate/report to the package"
Commit: `6dd66d0c109f5e0c97c34aaf9e259a2ec8ec17ed` (pushed to `origin/main`)

## What shipped this iteration

- `readme_refresh_run.py`: added `_LANGUAGE_RUNNERS = {"python": python_verification_runner,
  "typescript": typescript_verification_runner}` and changed `verify_examples()`'s dispatch
  line to `runner = _verification_runner or _LANGUAGE_RUNNERS.get(platform,
  _default_verification_runner)`.
- This closes a real bug (RC2, confirmed by direct code read): before this fix,
  `verify_examples()` always fell to `_default_verification_runner` (the honest all-stub --
  every block `TOOLCHAIN-UNAVAILABLE`) unless a caller explicitly passed
  `--python-runner`/`--typescript-runner`, even for a real python/typescript product. Since the
  stub's own `all_named` is trivially `True`, an omitted/wrong flag silently produced an
  all-stub, still-`approve()`-able result.
- `test_readme_refresh_run.py`: 6 new tests (dispatch-dict identity, per-platform selection,
  unknown-platform fallback, explicit-override precedence via the `configure()` seam, and one
  full state-machine run of the existing `testfam`/`testplat` fixture proving the stub path is
  unchanged). Full suite: 216 → 222, all passing (run 3 times total across the iteration for
  confidence, including once after fixing a monkeypatch-lint T2 violation the pre-commit gate
  caught in the first attempt).

## What was deliberately deferred (and why)

1. **Swapping the dispatched functions to the `lib.example_verification.runners` package
   copies** (extracted from these same functions in taskcard C3). Not done here: dispatch
   correctness and the runner-implementation swap are separable risks, and this module gates
   real PRs against real upstream FOSS repos. C3's parity tests + a real end-to-end pilot
   (real venv+pip install / real npm+tsc+tsx against the actual pdf/python and pdf/typescript
   clone caches) already proved the two copies byte-identical, but re-verifying that swap
   belongs to its own, later, narrowly-scoped commit.
2. **`report.json`/`VerificationReport` writing and the `approve()`/`last-executed.json`/
   audit-portfolio `proof_tier` reads** the governing plan's Consumer-wiring table describes.
   These need `lib/example_verification/api.py`, which appears in the plan's aspirational
   module tree but is **assigned to no taskcard in the current C1-C14 rollout** — a real,
   disclosed gap in the plan itself (independently flagged by C4's own reviewer too). Building
   `api.py` un-asked, inside C7's `allowed_paths` (which don't even include the package
   directory), would be scope creep on the highest-risk taskcard in the mission.
3. **A `--force-stub-runner` governance escape hatch.** Not mentioned anywhere in this
   iteration's evidence trail as built; not needed for the dispatch fix itself, and there's no
   taskcard scoping it.
4. **Deleting the old inline runner functions** (`readme_refresh_run.py:4725-5343`) or removing
   the `--python-runner`/`--typescript-runner` CLI flags. Left as-is per the stage's own
   rollback guidance ("keep both old and new runners... do not delete yet") — `configure()`
   still lets a caller override explicitly, so no existing behavior for callers who pass a flag
   changes.

## Live-pilot decision

Did **not** create a new live `verify_examples()` run against a real product to pilot this
specific commit. Existing real runs at
`reports/readme_refresh_runs/pdf/python/rr-20260905T065622Z-20ee0e681e4c` (`AWAITING_REVIEW`,
owned by a session independently confirmed stale in this same mission's C4 iteration) already
show `runner: python_verification_runner_v2` with real classifications, proving the dispatched
functions are already exercised in production via the manual flag — this fix only changes
*when* they fire (automatically, for known platforms), not *how* they behave. Creating new
mutating run state against a real, possibly-contended product for a change already covered by
222 passing tests plus C3's real parity/pilot evidence was judged unnecessary risk.

## Disposition

Checkpointing C7 as `IMPLEMENTED` → `FOCUSED_VERIFIED` this iteration (not closing) — an
independent reviewer must confirm the dispatch-only framing is sound and that nothing beyond
`allowed_paths` was touched, and a future iteration should pick up the deferred package-runner
swap / `api.py` gap as its own scoped work.
