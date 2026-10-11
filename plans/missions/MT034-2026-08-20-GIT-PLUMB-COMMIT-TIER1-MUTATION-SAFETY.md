# MT034-2026-08-20-GIT-PLUMB-COMMIT-TIER1-MUTATION-SAFETY

**Status**: CLOSED_WITH_VALID_DEFERRALS
**Opened**: 2026-08-20 (first-time `.supervisor` PSL binding of a plan already executed via
the AGENTS.md skill track, same pattern as MT010/MT013/MT016/MT024/MT029/MT031)
**Closed**: 2026-08-20
**Governing plan**: `C:\Users\prora\.claude\plans\found-a-real-bug-purrfect-moonbeam.md`

## What this mission was

While cleaning up after a blocked `git_plumb_commit.py` run, a prior session found the
real `.git/index` staged after a *failed* plumbing attempt -- contradicting the tool's own
docstring claim that it never touches the real index. The user asked for a first-principles
production assessment, then explicitly requested two successive deeper reassessments before
approving a plan (three total review passes), specifically because this tool sits on the
repo's commit path. The approved plan identified two independently-real mutation bugs
(pre-commit-audit.sh Step 10's worktree restore, Step 5's plain-Python content-hash write)
plus a methodology-level root cause (reactive, incident-driven discovery of this tool's own
safety contract), and designed a hardening: an empirical isolation canary, a mechanism-
agnostic runtime postcondition, `PC_AUDIT_NO_MUTATE` gating for both mutating steps, and a
WARN-only soft-launch posture for the new hard-blocking checks.

## What was completed

**Original execution** (commit `54206d711c4d97bc08c4aff889c93e5cb3bc3695`, pushed to
`origin/main`):
- Track A (unconditional, real interactive hook): `scripts/pre-commit-audit.sh` Step 10 now
  checks for unstaged delta before doing a full worktree restore -- a partially-staged file
  (`git add -p` staging only a `graded_at:` bump) no longer has its real unstaged edits
  silently destroyed.
- Track B (`git_plumb_commit.py`'s Tier-1 parity-check path): Step 5 and Step 10 both
  respect a new `PC_AUDIT_NO_MUTATE` env var (set only by `git_plumb_commit.py`) and report
  findings instead of mutating. `git_plumb_commit.py` gained an isolation canary
  (`_verify_index_isolation`, cached per bash/git pairing), a runtime postcondition
  (`_real_index_snapshot`/`_real_content_snapshot`), `PlumbCommitIsolationBreach`/
  `PlumbCommitPostconditionBreach`, and a `strict_isolation`/`--strict-isolation` flag
  defaulting to non-blocking WARN mode.
- Two additional real defects found and fixed while writing regression tests against the
  live script (neither had a prior incident): `check_graded_at_only.py`'s Windows CRLF
  stdout corrupting candidate paths read via `read -r` (Step 10 had likely never actually
  reverted a file on this platform); `provenance_normalize_hash.py --dry-run`'s "Would
  update: N" vs "Updated: N" label mismatch (would have silently defeated the Step 5
  check-only branch).
- Dogfooded: the fix itself was committed through the newly-hardened tool -- all 35 real
  Tier-1 steps ran clean, zero isolation/postcondition warnings.
- New/modified test files: `test_git_plumb_commit.py` (+9 tests, 45 total),
  `test_precommit_audit_step5_step10.py` (new, 5 tests), `test_precommit_audit_mutation_
  safety.py` (new, 7 tests) -- plus the mutation-safety registry
  (`precommit_audit_mutation_registry.yaml` + `check_precommit_audit_mutation_safety.py`).
- Gap escalation report filed and resolved:
  `reports/skill-gaps/2026-08-20-git-plumb-commit-tier1-mutation-safety.md` (local-only,
  gitignored, per repo convention).

**This convergence pass** (Stage 1 audit -> Stage 2 hardening -> Stage 3 execution,
1 taskcard):
- Stage 1 found 1 mandatory, HIGH-severity finding (L2-MT034-01): none of this mission's 3
  test files ran in any CI workflow -- confirmed by grepping all 6 pytest-invoking GitHub
  Actions workflows. This directly undermined the "durably regression-protected" claim the
  session's own closing summary had made without qualification (classified `MISLEADING` in
  the claim matrix).
- Stage 2 hardened into 1 taskcard, TC-MT034-01.
- Stage 3 executed it: added the 3 test files to `.github/workflows/skill-governance.yml`'s
  existing "Run governance test suite" pytest step, AND extended that workflow's own
  `push`/`pull_request` trigger `paths:` lists to cover this mission's source files (without
  which the step would only have fired by coincidence). Verified via a real, full local run
  of the exact modified CI command (355s): all 20 of this mission's tests passed. Committed
  (`99dd9a9bc5b6f427d4e699bff9875f47d2d13560`), pushed.
- Found 1 further, genuinely unrelated defect during that verification run
  (L2-MT034-04: `scripts/pipeline/commands/foss/upstream_issue_workflow.py` has no
  pipeline-registry entry, failing `test_registration_check_exits_zero`) -- disclosed in
  full, deliberately NOT fixed (out of this mission's chartered scope) and NOT filed to
  `backlog/BACKLOG.md` this pass (that file is large and actively used by a concurrently
  running, unrelated mission; recorded fully in this mission's own `.supervisor` state and
  in the final report to the user instead).
- Scored TC-MT034-01 across all 15 quality dimensions (all >= 4): `EXECUTION_COMPLETE_WITH_
  LIMITATIONS`.

## Verification performed

- `pytest scripts/pipeline/tests/test_git_plumb_commit.py -v` -> 45 passed
- `pytest scripts/pipeline/tests/test_precommit_audit_step5_step10.py -v` -> 5 passed (real
  script text extracted live from disk, not hand-copied)
- `pytest scripts/pipeline/tests/test_precommit_audit_mutation_safety.py -v` -> 7 passed
- Real commit through the real 35-step pre-commit hook (twice, once per commit this
  mission produced) -> 35 passed, 1 skipped, 0 failed, both times
- Real, full local run of the exact CI command TC-MT034-01 modified (8 files/dirs,
  `-v --tb=short`) -> 1233 passed overall (all 20 of this mission's own tests among them);
  2 unrelated, independently-confirmed-pre-existing failures disclosed, not fixed
- Real push to `origin/main`, confirmed via `git ls-remote` against the actual remote (not
  just the local ref) after each of the 2 commits

Full detail: `.supervisor/state/MT034-2026-08-20-GIT-PLUMB-COMMIT-TIER1-MUTATION-SAFETY/`
(Stage 1/2/3 artifacts, claim-classification matrix, quality scoring, final-all-green
candidate).

## Remaining follow-ups / non-blockers

- **L1-MT034-01**: `strict_isolation` defaults to `False` (soft-launch WARN mode), by
  design. A human needs to decide when to flip the default (or pass `--strict-isolation`
  explicitly) once there's been a real review window against live usage.
- **L1-MT034-02**: Phase 2b of the governing plan (full ~32-step real-script integration
  test, bash/git toolchain pinning) deliberately deferred, needs its own separate sign-off.
- **L2-MT034-02**: the weekly CI cron caller (`upstream-monitor.yml`) has not yet exercised
  this code in a live GitHub Actions run (next natural run: next Monday 08:00 UTC).
- **L2-MT034-03**: the mutation-safety checker's 3 advisory findings (all confirmed false
  positives, comment/echo text) have no allowlist annotation -- cosmetic, backlog-worthy.
- **L2-MT034-04** (found this pass, not fixed): `upstream_issue_workflow.py` needs a
  `scripts/pipeline/config/registry.yaml` entry -- unrelated to this mission, will make
  `skill-governance.yml`'s governance-test-suite step show red on its next trigger for a
  reason unrelated to whatever change triggers it. Whoever owns that module (or the next
  session with uncontended `backlog/BACKLOG.md` access) should file/fix it.
- **L3-MT034-01**: no telemetry tracks graduation from soft-launch to enforcing mode for
  `strict_isolation` -- backlog-worthy, not built this pass (disproportionate for a tool
  invoked at most weekly).

## MISSION_AUTHORITY.yaml note

Root slot deliberately **not** taken -- held by a different, unrelated, in-progress mission
(`concurrent-toasting-biscuit`). This mission's own work was already 100% complete before
this binding began, matching the MT010/MT013/MT016/MT031 precedent for not needing the
exclusive root lock.
