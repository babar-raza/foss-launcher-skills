# Rollback / Recovery Log

No rollback or recovery action was invoked during this mission's execution
(2026-08-31 course-correction pass through Phase 9 close-out).

One deliberate, disclosed **revert-and-redo** did occur, distinct from a
rollback in the plan's own sense (no run was killed, no destructive action was
undone) — recorded here for completeness:

- **tex/python (TC-27a)**: the first `verify-examples` call on run
  `rr-20260831T173122Z-18ee1cd8264e` was made without `--python-runner`,
  producing a dishonest blanket `TOOLCHAIN-UNAVAILABLE` stub result for a
  Python product. Caught before `approve`. The run was formally
  `abandon()`-ed with the mistake recorded in its own `failure_reason`, and a
  fresh run (`rr-20260831T173823Z-9fc92f92f68f`) was started clean and carried
  through to `APPROVED`. This is a normal, sanctioned use of `abandon` (the
  Rollback & Recovery table's own first row), not an emergency recovery.
- **font/python (TC-27b)**: the first `plan` call on run
  `rr-20260831T174029Z-3ffc1e1470b5` executed against the pre-fix
  `git_reachable()` code (before TC-36 landed). Once TC-36 was fixed, that run
  was `abandon()`-ed for evidentiary cleanliness (so the canary's own
  freshness-state evidence reflects the fixed code, not the buggy one) and
  restarted as `rr-20260831T175608Z-fbf49af87de5`.

No `git reset`, no force-push, no destructive git operation of any kind was
used anywhere in this mission's execution. All commits went through
`git_plumb_commit.py`.
