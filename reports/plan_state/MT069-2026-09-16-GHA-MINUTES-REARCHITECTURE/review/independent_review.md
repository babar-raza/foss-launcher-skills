# TC-11: Independent Review of Dossiers, Decisions, and Threat Assessment

**Mission:** MT069-2026-09-16-GHA-MINUTES-REARCHITECTURE
**Date:** 2026-09-17
**Method:** A fresh Agent session, with no prior context or attachment to this mission's
own conclusions, was asked to adversarially re-verify TC-01 through TC-10's deliverables
against ground truth (live `git`/`gh api` calls, direct file reads) rather than trust the
artifacts' own self-description — per this mission brief's Stage 15 instruction and this
repo's "genuine independence" review culture. Every finding it returned was then
independently re-verified a second time by the primary session before any correction was
written, per this repo's own standing rule against trusting a prior write-up (including
another agent's) as settled without live re-checking.

## Verdict

**PARTIAL_EXECUTION_WITH_CORRECTIONS_APPLIED** — 6 real findings surfaced (1 CRITICAL
code defect, 2 documentation-accuracy defects repeated across multiple files, 1 resolved
open question, 1 factually-wrong "mystery" framing repeated across multiple files, 1
evidence-doc internal-consistency defect), plus 1 additional structural defect (invalid
JSON) found independently by the primary session while applying the corrections below,
not originally flagged by the review agent. **All 7 are fixed as of this document.** No
`CONFIRMED` finding remains open. This satisfies the mission brief's Stage 15
requirement to correct the authoritative plan and state before proceeding, not merely
log findings against it.

## Findings, corrections applied, and verification

### 1. CRITICAL — fail-open gap in TC-15's new pre-commit enforcement gate

**Finding**: `check_evaluator_version_bump.py`'s `check()` read
`scripts/pipeline/content_eval/__init__.py`'s content via `_INIT_PATH.read_text()` — the
**working-tree disk copy** — regardless of whether the invocation was a pre-commit check
judging what is about to be committed. A developer who bumped `EVALUATOR_VERSIONS[name]`
on disk but forgot `git add scripts/pipeline/content_eval/__init__.py` would have the
new Step 44 pre-commit gate read the disk copy, see the bump, and **PASS** — even though
the resulting commit would not actually contain that bump. This is fail-**open**, not
"fails closed" as the original TC-15 evidence doc's "known limitation" section
characterized a narrower, related issue (the `EVALUATOR-VERSION-BUMP-EXEMPT` marker
being invisible when staged-but-uncommitted).

**Verification**: confirmed by direct code reading
(`scripts/ci/checks/check_evaluator_version_bump.py` lines 104-186) before any fix was
attempted, then reproduced live in a throwaway scratch git repository (a bump present on
disk for `__init__.py` but never staged, alongside a staged evaluator-file change) via
the real CLI — pre-fix, this exact scenario passed (exit 0); confirmed via direct code
inspection this was solely due to the disk read (the scratch-repo reproduction could not
be preserved as an automated regression fixture, since `check_evaluator_version_bump.py`'s
`_run_git` is intentionally hardcoded to `cwd=_REPO_ROOT` — it is designed to only ever
operate inside its home repo).

**Fix applied**:
- `check()` gained a `staged: bool = False` parameter; when true and `init_head_text`
  isn't injected, `head_text` comes from the git **index** via `_file_at_ref(_INIT_REL_PATH,
  "")` (`git show :path` — the empty-ref pathspec syntax for "the index," reusing the
  existing helper unchanged) instead of disk.
- `_diff_added_lines`/`has_exemption` gained the same `staged` parameter, switching the
  `EVALUATOR-VERSION-BUMP-EXEMPT` exemption diff from `git diff {base}...HEAD` to
  `git diff --cached {base}` — this also closes the narrower, previously-documented
  exemption-marker limitation as a side effect.
- `main()` gained a `--staged` CLI flag.
- `scripts/pre-commit-audit.sh`'s Step 44 now passes `--staged`; its comment block was
  rewritten to describe the real (fail-open, not "safe-direction") risk that was closed.
  `scripts/ci/hooks/simulate_pr_checks.sh`'s invocation (correctly simulating the real
  push-triggered CI workflow, which legitimately diffs an already-committed working tree
  against a base branch) is unchanged and correctly still omits `--staged`.
- 2 new regression tests added to `scripts/ci/tests/test_check_evaluator_version_bump.py`
  (`test_staged_mode_reads_index_not_working_tree`,
  `test_non_staged_mode_still_reads_working_tree_disk_copy`), monkeypatching
  `_file_at_ref`/`_INIT_PATH` directly to exercise the real read-path logic (the existing
  6 tests all inject `init_head_text`, bypassing this code path entirely — which is
  exactly why none of them could have caught this).

**Files changed**: `scripts/ci/checks/check_evaluator_version_bump.py`,
`scripts/pre-commit-audit.sh`, `scripts/ci/tests/test_check_evaluator_version_bump.py`.

**Post-fix validation**: `pytest scripts/ci/tests/test_check_evaluator_version_bump.py -v`
— 8/8 passed. Full `pytest scripts/ci/tests/` (1,114 tests collected) — 1,113 passed, 1
skipped (pre-existing, unrelated), exit code 0, 422.54s — no regressions. `bash -n
scripts/pre-commit-audit.sh` — clean.

### 2. HIGH — concurrency-guard fixes wrongly described as "done"/"landed"

**Finding**: The concurrency/cancel-in-progress guards added to
`content-governance-checks.yml`, `llms-generation.yml`, and `skill-governance.yml`
(real, correct, purely-additive 4-line edits each) were described in multiple documents
as "done," "landed," or "already added," implying durability. `git status --porcelain`
shows all three still `M` (uncommitted working-tree edits) — they would not survive a
`git checkout --` or a conflicting edit from one of this repo's many concurrent sessions
until actually committed.

**Verification**: `git status --porcelain .github/workflows/content-governance-checks.yml
.github/workflows/llms-generation.yml .github/workflows/skill-governance.yml` re-run
directly by the primary session (not just accepted from the review agent) — confirmed
all three still show `M`, nothing staged, `git diff --stat` shows the expected 4-line
purely-additive change for each.

**Fix applied**: corrected in
`plans/from_backlog/2026-09-16-gha-minutes-rearchitecture.md` (Status/CI-defect section),
`analysis/destination_decision_matrix.json` (`content-governance-checks.yml` entry),
`design/self_hosted_architecture.md` (two sections), `dossiers/content-governance-checks.md`,
and `dossiers/skill-governance.md` — each now states the fix is real but uncommitted, and
flags committing it as an open precondition for `PHB-07`'s self-hosted cutover, not a
satisfied one.

**Residual note (re-checked while fixing, not just accepted)**: an earlier session note
recorded an unrelated concurrent session's staged content sitting alongside this
mission's unstaged edit in `content-governance-checks.yml`. Re-checked live just now:
`git diff --cached --stat .github/workflows/content-governance-checks.yml` is currently
empty — nothing is staged for that file right now. This is a point-in-time observation,
not a guarantee for whenever the actual commit happens (this repo routinely has 80+
dirty files from concurrent sessions) — the plan's existing rule to commit via
`git_plumb_commit.py --files <exact list>`, never `git add -A`, is what actually protects
against this and needs no change; flagging it here as a TC-12/`PHB-07` execution-time
re-check, not a currently-open problem.

### 3. HIGH — concurrency fix misattributed to TC-14/TC-15

**Finding**: 4 documents credited the concurrency-guard fix to "`TC-14`/`TC-15` work."
Those taskcards are unambiguously about something else — `TC-14` fixed a comparison bug
in `check_platform_capabilities.py`; `TC-15` gave `check_evaluator_version_bump.py`
pre-commit enforcement. The concurrency guards were actually added via `/workflow-harden`
(S-115) under `TC-03`.

**Verification**: re-read `ci_defect_remediation/TC-14_platform_capabilities_fix.md` and
`TC-15_evaluator_version_bump_shift_left.md` directly — both are unambiguously about the
checker fixes, with no mention of workflow YAML concurrency blocks anywhere in either.

**Fix applied**: corrected in `dossiers/content-governance-checks.md`,
`dossiers/skill-governance.md`, `dossiers/llms-generation.md`, and
`design/self_hosted_architecture.md` (two sections) — each now cites `/workflow-harden`/
`TC-03` and notes the fix is real but uncommitted (see finding #2).

### 4. MEDIUM — `llms-generation.yml`'s duplication question left unresolved when it was directly resolvable

**Finding**: `llms-generation.yml`'s dossier and destination-matrix entry were left at
`INSUFFICIENT_EVIDENCE`/LOW confidence on whether its private-repo run is a necessary
fast-feedback correctness check or fully duplicated work, even though the answer was
directly checkable — the workflow's own header/Summary text states the deploy repo
re-runs the generator, and the public deploy workflow's actual content was one `gh api`
call away.

**Verification (re-verified independently a second time by the primary session, not
just accepted from the review agent's summary)**: read `.github/workflows/
llms-generation.yml` in full — its header comment and final "Summary" step state
"Deployment happens via aspose.org-workflows per-site workflows. Each site workflow runs
the generator again at deploy time." Then fetched
`gh api repos/Aspose/aspose.org-workflows/contents/.github/workflows/docs.aspose.org.yml`
directly and confirmed it invokes `python scripts/generator/llms-generator.py
--subdomain docs.aspose.org ...`. Also checked (not something the original review
summary had mentioned, found independently): that public deploy workflow is
`workflow_dispatch`-only (manual `environment: staging|production` input, not automatic
per push) and does **not** run `detect_stale_llms.py --check-only` anywhere (confirmed
absent by `grep`). This means the underlying conclusion needed a real correction, not a
simple "yes it's duplicated, eliminate it": the regeneration computation duplicates, but
the private workflow's distinct fail-fast gate value (catching a broken generator or
malformed content before a human manually triggers a deploy) is real and is **not**
replicated publicly.

**Fix applied**: `analysis/destination_decision_matrix.json`'s `llms-generation.yml`
entry changed from `INSUFFICIENT_EVIDENCE`/LOW to `REQUIRES_REDESIGN`/MEDIUM (an enum
value already used elsewhere in this matrix, not invented). `dossiers/llms-generation.md`
rewritten (§9-20) to reflect: duplication confirmed but partial, not total; recommend
keeping a lightweight verification step while shedding the full duplicate regeneration;
the previously-claimed "up to 259 min/month if eliminated" savings figure retracted as
overstated, since full elimination is no longer the recommended fix. Plan file's
Technical Findings and destination-triage table updated to match. **Honestly flagged as
not fully closed**: the specific redesign (e.g., whether `detect_stale_llms.py` can
validate staleness without a full prior regenerate) was not implemented or proven in
this pass — this is now a correctly-scoped, evidence-backed open engineering question,
not a guess.

### 5. MEDIUM — `install-literal-sweep.yml`'s "zero runs, should have fired twice" framing was factually wrong, repeated across 6 documents

**Finding**: Multiple documents characterized this workflow's zero recorded runs across
the full usage window (or even the full 172-day history) as suspicious — "should have
fired at least twice in this 18-day window," or "zero runs EVER... despite being a
weekly-scheduled bot" — implying a possible broken trigger or data-pull gap.

**Verification (re-verified independently a second time)**: `git log --follow
--diff-filter=A --format='%H %ad %s' --date=short -- .github/workflows/
install-literal-sweep.yml` — confirms the file was added 2026-09-10 (commit
`f9cbe210fb`). Its trigger is `schedule: cron: '0 11 * * 1'` (weekly, Monday 11:00 UTC) —
confirmed by direct read of the workflow file. Between 2026-09-10 and the usage window's
close (2026-09-18), exactly one Monday (2026-09-14) fell inside the window — and
`inventory/disabled_vs_running_anomaly.md` independently confirms 2026-09-14 as the date
other workflows had their last successful runs before the mass-disable. "Should have
fired at least twice" is arithmetically wrong regardless of the mass-disable; at most one
firing was ever structurally possible.

**Fix applied**: corrected in `plans/from_backlog/2026-09-16-gha-minutes-rearchitecture.md`
(2 locations), `usage/usage_dataset.json`, `usage/billing_reconciliation.md`,
`analysis/failure_signatures.json`, `analysis/importance_matrix.json`,
`analysis/destination_decision_matrix.json`, and `dossiers/install-literal-sweep.md`
(6 sections) — each now states the resolved explanation and removes the "mystery"/
defect-suggesting language. The dossier's confidence rating is corrected from "genuinely
unresolved" to "resolved on why; still provisionally LOW on the migration decision
specifically, for the ordinary reason of an open product decision plus no real-run track
record yet."

### 6. LOW — test-suite-size inconsistency between TC-14/TC-15 evidence docs and reality

**Finding**: `ci_defect_remediation/TC-14_platform_capabilities_fix.md` and
`TC-15_evaluator_version_bump_shift_left.md` both claimed "the full 1594-test governance
suite" passed. `scripts/ci/tests/` does not contain 1,594 tests.

**Verification**: `pytest scripts/ci/tests/ --collect-only -q` — reports 1,114 tests
collected (as of this review, after the 2 new tests from finding #1 above; 1,112 before
them). 1,594 is a different, larger scope: `scripts/ci/tests/` plus the additional
`scripts/pipeline` tests that `skill-governance.yml`'s own CI job runs in the same step —
the two scopes were conflated when the original evidence docs were written, not evidence
of two genuinely contradictory facts.

**Fix applied**: both evidence docs corrected to state the real `scripts/ci/tests/`
count and clarify the 1,594 figure's actual (different, larger) scope. The corrected
`scripts/ci/tests/` suite was re-run in full after finding #1's fix: 1,113 passed, 1
skipped, exit 0.

### 7. Additional defect found independently by the primary session, not originally flagged by the review agent — invalid JSON in `destination_decision_matrix.json`

**Finding**: while applying the corrections above, `.venv/Scripts/python -c "import
json; json.load(...)"` failed with `JSONDecodeError` on `analysis/
destination_decision_matrix.json`. Three entries used a malformed pattern —
`{"file": "name_dup": {"note": "..."}}` (a string value immediately followed by a colon
and object is not valid JSON) — instead of the correct `{"file": "name_dup", "note":
"..."}` pattern used correctly elsewhere in the same file. This predates this review's
corrections; it was not introduced by them.

**Fix applied**: all 3 malformed entries (`upstream-monitor.yml_dup_removed`,
`content-governance-checks.yml_dup`, `maven-publish-watcher.yml_dup`) corrected to valid
JSON syntax matching the file's own established pattern. Re-validated:
`json.load()` now succeeds, 25 decisions present.

## Checked and found solid (no correction needed)

- `inventory/workflows_inventory.json`'s `workflow_harden_citation` field — correctly
  attributes the concurrency fixes to `/workflow-harden`/`TC-03` already; this is the one
  document that had it right from the start.
- `analysis/threat_assessment.md` — secrets/permissions claims spot-checked against the
  real workflow files and confirmed accurate.
- `design/public_execution_boundary.md` — the MT066 formal-gate check result was
  live-reverified, not just cited.
- `dossiers/content-audit.md`, `dossiers/cross-repo-index-sync.md` (and by extension the
  other 18 dossiers not specifically named in any finding above) — spot-read and found
  internally consistent with their cited evidence sources.
- The taskcard/mission-authority governance trail itself (`taskcards.jsonl`,
  `MISSION_AUTHORITY.yaml` archival snapshot) — not touched by any finding; this review
  concerned the analytical content of TC-01 through TC-10's deliverables, not the
  governance mechanics around them.

## Honest limits of this review

- This review re-verified the specific claims the fresh review agent flagged, plus one
  additional structural defect found while fixing them. It is not a from-scratch
  re-audit of all ~20 dossiers' every factual claim — that would be a materially larger
  undertaking than TC-11's own scope calls for, consistent with this mission's repeated
  caution (see the plan's "Tradeoffs, risks, and honest limits" sections) against
  assuming a bounded investigation pass found every possible defect.
- The `llms-generation.yml` redesign direction (finding #4) is diagnosed, not built —
  a real follow-up item, not closed by this review.
- The concurrency-guard commit (finding #2) remains genuinely outstanding — this review
  corrected the documentation to stop claiming it's done; it does not itself commit the
  fix, which stays a `PHB-07`-adjacent precondition for a human/execution-phase decision.

## Acceptance against TC-11's own criteria

- Independent review completed with real findings, not a rubber stamp — 7 confirmed
  issues found and fixed.
- No open `CONFIRMED` finding remains — all 7 are corrected as of this document, with
  verification recorded for each.
- Every correction is evidence-backed by a live re-check performed by the primary
  session, not accepted solely on the review agent's own say-so.
