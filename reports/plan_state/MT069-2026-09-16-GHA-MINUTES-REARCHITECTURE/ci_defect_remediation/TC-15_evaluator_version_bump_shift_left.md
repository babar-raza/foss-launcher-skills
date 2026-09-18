# TC-15: Evaluator-Version-Bump Shift-Left + Docs Fix

**Mission:** MT069-2026-09-16-GHA-MINUTES-REARCHITECTURE
**Date:** 2026-09-17

## What was wrong

`scripts/ci/checks/check_evaluator_version_bump.py` (blocking, real logic —
correctly catching genuine policy violations) existed *only* inside
`content-governance-checks.yml`, a push-triggered CI workflow. It had zero
presence in `scripts/pre-commit-audit.sh` (the real pre-commit hook), zero
presence in `git_plumb_commit.py`'s manual pre-flight re-checks, and zero
presence in `scripts/ci/hooks/simulate_pr_checks.sh` (the local CI-mirror
script, which *does* include its advisory sibling `check_evaluator_freeze.py`).
Since this repo has no PR gate and cannot enable GitHub branch protection
(private repo, plan-tier limit), a CI-only check can only ever fire after a
non-compliant commit has already landed on `main` — this, not flakiness or a
broken check, produced `content-governance-checks.yml`'s 49% real failure
rate (`TC-05`).

**Correction to the plan's original design**: investigation during
implementation found `git_plumb_commit.py` already re-runs the *entire*
`scripts/pre-commit-audit.sh` (its "Tier 1" checks) against an isolated temp
index for every plumbed commit (`_run_tier1_checks()`, confirmed by reading
the code directly). This means adding the check to `pre-commit-audit.sh`
alone covers *both* commit paths automatically — a separate manual
re-implementation inside `git_plumb_commit.py` itself (as originally planned,
mirroring `stale_file_regression`'s treatment) is unnecessary. Not done, and
correctly so.

## What changed

- **`scripts/pre-commit-audit.sh`** (override token `20260917-102911-scripts-pre-commit-audit-sh`):
  new Step 44 — scoped to staged `scripts/pipeline/content_eval/evaluators/*.py`
  files only (same design as Steps 33/42/43), invokes
  `check_evaluator_version_bump.py --base HEAD --files <staged files>`, blocks
  the commit on a real violation.
- **`scripts/ci/hooks/simulate_pr_checks.sh`**: added the missing step
  alongside its sibling `check_evaluator_freeze.py`, marked `blocking` to
  match its real behavior in CI (unlike the advisory sibling).
- **`scripts/ci/tests/test_check_evaluator_version_bump.py`** (new file — this
  checker had zero test coverage before this taskcard): 8 tests (6 original +
  2 added same-day for the fail-open fix, see correction above) exercising
  `check()`'s injectable logic directly — unbumped-is-blocked,
  own-version-bumped-is-clean, cross-cutting `EVALUATOR_LOGIC_VERSION`-bump-is-
  clean, exemption-marker-is-clean, no-evaluator-files-changed-is-clean, the
  file-path regex matcher, and (new) staged-mode-reads-index-not-working-tree
  / non-staged-mode-still-reads-working-tree-disk-copy.
- **`docs/development/evaluator-changes.md`**: restored the version-bump rule
  as checklist item 5 (it was present in the pre-2026-05-30 doc this one
  replaced, then dropped), with a note on why it's there and pointing at the
  real enforcement mechanism.

## Correction (2026-09-17, same day, TC-11 independent review): a real fail-open gap, now fixed

The independent review of this mission's own work (`TC-11`) found that the
limitation documented below as "safe-direction (fails closed)" undersold the
actual risk — the underlying bug was fail-**open**, not fail-closed, and real,
not theoretical:

`check()` read `scripts/pipeline/content_eval/__init__.py`'s content via
`_INIT_PATH.read_text()` — the **working-tree disk copy** — regardless of
whether Step 44 was invoking it pre-commit. A developer who bumped
`EVALUATOR_VERSIONS[name]` on disk but forgot `git add
scripts/pipeline/content_eval/__init__.py` would have this new gate read the
disk copy, see the bump, and **PASS** — even though the commit about to be
created would not actually contain that bump. This is the opposite of "fails
closed": it is a silent false-negative on exactly the class of mistake this
taskcard exists to catch. Confirmed live in a throwaway scratch git repo (bump
staged for the evaluator file, bump present on disk but *not* staged for
`__init__.py`) before and after the fix, using the checker's real CLI —
pre-fix this scenario would have exited 0; see the two new regression tests
below for the equivalent proof at the unit level (the live scratch-repo
reproduction could not itself be preserved as a runnable artifact, since
`check_evaluator_version_bump.py`'s `_run_git` is intentionally hardcoded to
`cwd=_REPO_ROOT` — it is only ever meant to run inside its home repo — so an
external scratch repo cannot be used as an automated regression fixture).

**Fix applied**: `check()` gained a `staged: bool = False` parameter, and
`main()` a new `--staged` flag. When `--staged` is passed, `head_text` comes
from the git **index** instead (`git show :path` — the empty-ref pathspec
syntax for "the index," reusing the existing `_file_at_ref()` helper
unchanged), and the `EVALUATOR-VERSION-BUMP-EXEMPT` exemption diff switches
from `git diff {base}...HEAD` to `git diff --cached {base}` for the same
reason — this also closes the *separate*, smaller limitation originally
documented below (an exemption marker staged but not yet committed was
previously invisible to the check). `scripts/pre-commit-audit.sh`'s Step 44
now passes `--staged`; `scripts/ci/hooks/simulate_pr_checks.sh`'s invocation
(simulating the real push-triggered CI workflow, which legitimately diffs an
already-committed working tree against a base branch) is unchanged and
correctly still omits `--staged`.

The original "known, documented limitation" section below is preserved
as-written for the record, but its "safe-direction" framing should be read
in light of the correction above — it was accurate for the narrower
exemption-marker case it described, not for the broader read-path bug the
review found.

## Known, documented limitation (not silently assumed away) — superseded above

`check_evaluator_version_bump.py`'s `EVALUATOR-VERSION-BUMP-EXEMPT` escape
hatch is detected via `git diff {base}...HEAD`, which cannot see an exemption
marker that is staged but not yet committed. In the rare case someone
genuinely needs that escape hatch on a brand-new, uncommitted change, this
pre-commit gate may still block until the marker exists in a prior commit —
a safe-direction (fails closed, not open) limitation, documented inline in
Step 44's own comment. A future enhancement could add a `--staged` diff mode
to the checker itself to close this precisely; deliberately not done here to
keep this fix surgical.

## Explicitly not done — human action required

`AGENTS.md` §9a still links to the deleted `docs/workflows/evaluator-changes.md`
rather than the current `docs/development/evaluator-changes.md`. `AGENTS.md`
is human-maintainer-authored only per its own header (`Authority: Human
maintainer only`) — this fix was not attempted and should not be, by an
agent. Flagged to the user directly, not silently left unmentioned.

## Validation performed

- `bash -n` syntax check on both modified shell scripts — clean.
- Direct logic validation of `check_evaluator_version_bump.check()` via 4
  injected scenarios (unbumped/bumped/exempted/logic-version-bumped) before
  formalizing them as the permanent test file above — all 4 matched expected
  behavior.
- `pytest scripts/ci/tests/test_check_evaluator_version_bump.py -v` — 8/8 passed
  (6 original + 2 added for the fail-open fix above).
- **Correction (TC-11 review)**: this document originally claimed "the full
  1594-test governance suite" as the regression-check scope. That figure is
  wrong for this suite — `pytest scripts/ci/tests/ --collect-only -q` reports
  **1,114 tests collected** (1,112 pre-existing + the 2 new ones above); 1,594
  is a different, larger scope (`scripts/ci/tests/` plus the additional
  `scripts/pipeline` tests that `skill-governance.yml`'s own CI step runs
  separately) that got conflated with this one when originally written. The
  actual `scripts/ci/tests/` suite (1,114 tests) was run in full after this
  fix — see result below.
- `pytest scripts/ci/tests/` (full suite, 1,114 tests collected) — **confirmed
  complete**: 1,113 passed, 1 skipped (pre-existing, unrelated), exit code 0,
  422.54s. No regressions from `TC-14`, `TC-15`, or the same-day fail-open fix
  together.

## Governed-path handling

`scripts/ci/hooks/simulate_pr_checks.sh` and `scripts/ci/tests/test_check_evaluator_version_bump.py`
executed under the same S-115 skill context as `TC-14` (scope `scripts/ci/**`).
`scripts/pre-commit-audit.sh` required a separate override token (not in
`path_guard.py`'s governed-path list at all — falls to the forbidden-path/
override-token mechanism, same as `MISSION_AUTHORITY.yaml` earlier in this
mission). `docs/development/evaluator-changes.md` required neither (not a
governed or forbidden path).
