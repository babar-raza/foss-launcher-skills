<!-- CONTRACT: agent-executed
     purpose: forensic investigation + hardening of this repo's GitHub Actions workflows — trigger/dependency/permission/secret/cache correctness, plus CI-weight reduction; MT074: also the tracked templates in scripts/ci/deployed-workflows/** that are deployed to Aspose/aspose.org-workflows (template checklist, code-before-YAML deploy order)
     preconditions: git working tree clean for .github/workflows/**,scripts/ci/** (including scripts/ci/deployed-workflows/**); .venv usable; gh CLI authenticated
     postcondition: every reviewed workflow has documented findings with a VERIFIED_CLOSED or explicitly-deferred disposition; evidence bundle at reports/sprint/workflow-harden-{date}/
     idempotent: no — investigation findings vary run to run as workflows change; fixes are additive
     verified: 2026-10-07
     id: S-115
     depends_on: []
-->

# S-115: Workflow Harden — GitHub Actions CI Forensic Audit & Hardening

**Arguments**: $ARGUMENTS
**Expected format**: `[--workflow <file>] [--investigate-only] [--resume] [--dry-run] [--max-findings N]`

- `--workflow <file>` — limit the sprint to one `.github/workflows/<file>.yml` (default: all workflows in `.github/workflows/`)
- `--investigate-only` — Phase 0 only; produce investigation artifacts, no execution
- `--resume` — resume from the last checkpoint in `reports/sprint/workflow-harden-{date}/phase_state.json`
- `--dry-run` — investigation + taskcards but no execution
- `--max-findings N` — maximum finding count before escalation (default: 30)

## Purpose

Manually review every GitHub Actions workflow in `.github/workflows/` (and any composite
action or `scripts/ci/**` script it invokes), classify defects and fragility using a fixed
taxonomy, and fix what's safe to fix in the same sprint: missing safeguards (timeouts),
correctness gaps (a `continue-on-error` step whose output a later blocking step silently
depends on), permission/credential scope flags, and opportunities to make CI **lighter**
(faster, fewer redundant steps, dependency caching) without weakening any gate.

**Not a content skill.** Never writes to `content/`. Modifies `.github/workflows/*.yml`,
composite actions, and `scripts/ci/**` support scripts only.

**This repo has no GitLab CI and no self-hosted runners** (confirmed 2026-07-18 — all
workflows run on `ubuntu-latest`; no `.gitlab-ci.yml` exists). This skill's scope is
GitHub Actions only. If either changes in the future, re-validate this assumption in
Phase 0 Step 0.1 before proceeding as if it still holds.

## Reuse Gate

Before this skill was created, existing coverage was checked and found absent:

1. `pipeline-harden` (S-99) is explicitly scoped to `scripts/pipeline/` content-generation
   code and states "Not a content skill" with no mention of `.github/workflows/`.
2. `S-62` (`batch-reference`) is unrelated (bulk reference-page generation).
3. `path_guard.py`'s `ALLOWED_PREFIXES`/`FORBIDDEN_PREFIXES` had no entry for
   `.github/workflows/` — it fell to default-deny, meaning every prior CI-file edit needed
   a fresh one-off override token instead of a governed, repeatable process.
4. No skill in the ~115-entry registry has "workflow", "CI", "actions", or "`.github`" in
   its trigger/scope (confirmed via `docs/registries/skills.md` full-text scan).

Conclusion: capability gap (§6b state **NONE**) — justified as a new skill rather than
folding into S-99 (different file surface, different governance path: `.github/workflows/`
was ungoverned by any skill's declared scope, whereas S-99's scope is `scripts/pipeline/`).

## Anti-Proliferation Controls

| Control | Value |
|---------|-------|
| Lifecycle owner | Solo operator (same maintainer as S-87, S-99) |
| Future overlap rule | Any new skill touching `.github/workflows/**` or `scripts/ci/**` CI-definition files must check against S-115 first |
| Discoverability | Registered in `docs/registries/skills.md`; scope declared via Skill Context Gate below |

## Skill Context Gate

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin \
  --skill S-115 \
  --scope ".github/workflows/**,scripts/ci/**"
```

## Pre-conditions

1. Git working tree clean for `.github/workflows/**` and `scripts/ci/**` — if dirty, HALT; commit or stash first.
2. `.venv/Scripts/python` (or `.venv/bin/python`) resolves — if broken, HALT; repair venv first.
3. `gh auth status` succeeds — if not authenticated, HALT; this skill needs `gh` for remote verification.
4. Confirm the "no GitLab / no self-hosted runners" assumption still holds (Step 0.1) before treating findings as GitHub-only.

## Hard Limits

- **Max findings**: default 30. Phase 0 finding count exceeding this -> HALT and escalate.
- **Never weaken a gate**: no removing matrices, no converting a blocking check to
  `continue-on-error` to manufacture green, no widening `permissions:` beyond what a
  taskcard's investigation proves is needed.
- **No `content/` writes**: skill context scope excludes `content/`.
- **No secret rotation**: credential/PAT scope concerns are recorded as findings with a
  recommendation; this skill never rotates or regenerates secrets (out of CLI reach
  without the token owner's action).
- **Lightening must not reduce coverage**: caching, step consolidation, or trigger
  narrowing must not skip work a workflow was created to do — verify the same checks still
  run, just faster or with less duplication.

---

## MT074: Scope also covers `scripts/ci/deployed-workflows/**`

Added by mission MT074. Besides `.github/workflows/**`, this skill governs the **tracked templates of the
workflows that run from another repository**: `scripts/ci/deployed-workflows/*.yml`. They are
copy-deployed into `Aspose/aspose.org-workflows` (`.github/workflows/`), check out `Aspose/aspose.org`
fresh on each run, and run its scripts from `main`. The path is already inside the context scope
`scripts/ci/**`; name it explicitly when you begin, so the skill-run record shows it was in scope:

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin \
  --skill S-115 --scope ".github/workflows/**,scripts/ci/**,scripts/ci/deployed-workflows/**"
```

Phase 0 additionally inventories `scripts/ci/deployed-workflows/*.yml`, fetches each deployed copy
read-only (`gh api repos/Aspose/aspose.org-workflows/contents/.github/workflows/<name>.yml --jq .content | base64 -d`),
and records `check_workflow_drift.py --no-seed` output in `state_snapshot.json`. A dirty working tree for
that directory is a HALT, same as `.github/workflows/**`.

**Template checklist (every change to a deployed-workflow template).** Record each line PASS/FAIL with evidence:

1. Least-privilege `permissions:` on every job (`contents: read` unless a step proves a write is needed); no widening to make a step pass.
2. A `concurrency:` group and a `timeout-minutes:` on every job.
3. No new secret: only the existing repository token secrets, none echoed, none in a URL printed to the log; actions pinned per the repo's current norm.
4. Schedule and trigger set unchanged unless the change is the point of the PR; any new `workflow_dispatch` input has a safe default (a heavy path is dispatch-only and defaults off).
5. Default path does the cheap, clone-free work; nothing heavy (full clones of the whole fleet) on the scheduled path.
6. Never auto-merge and never push content or write to `main` from CI: outputs are issues, artifacts and a PR whose `add-paths` list is exactly the intended state files.
7. Issue/PR automation is idempotent: keyed titles/branches, update-not-duplicate on re-run, a per-run cap on new issues, and a documented behaviour for the first run after a long gap.
8. Exit semantics are intentional and recorded: what fails the job (infrastructure error, token or rate-limit failure, too many `UNKNOWN`) versus what is reported (drift itself).
9. Failure of an optional step can never block the step that does the primary work (`continue-on-error` only where nothing downstream trusts its output), and the failure is surfaced in the job summary.
10. Structure tests pass: `scripts/ci/tests/test_deployed_workflows_wiring.py` (step order, `add-paths`, key formats, permissions, concurrency, schedule intact), YAML parses, and the local template differs from the deployed copy only by the intended diff (`diff` against the fetched copy).

**Deploy ordering is load-bearing.** The deployed YAML runs scripts from a fresh checkout of `main`, so the
code those scripts need must be on `main` **before** the workflow YAML is deployed (YAML first makes the
next run fail). Order: code on `main`, then a PR in `Aspose/aspose.org-workflows` updating only the changed
templates (reviewed by someone other than the author; this skill's checklist is the review), then a
`workflow_dispatch` run and verification, then `check_workflow_drift.py --approve <name> --reason ...`
(it refuses unless deployed equals the reviewed template) and a commit of the rewritten
`data/workflow_deploy_baselines.json`. `workflow-drift-watch` reports `DIVERGED` between the code push and
the workflows-PR merge; that window is expected. Rollback is reverting the workflows PR
(`gh workflow disable` as a stop-gap). This skill stages the package and the runbook; the deployment itself
needs the operator's go-ahead.

---

## PHASE 0: Investigation (Read-Only)

**Checkpoint**: `investigation_complete`

### Step 0.1 — State Verification

Record current state:

| Item | What to check | Record as |
|------|---------------|-----------|
| Workflow inventory | List all `.github/workflows/*.yml` (or the one named by `--workflow`) | `workflow_files` |
| Composite actions | `.github/actions/**` if present | `composite_actions` |
| GitLab presence | `.gitlab-ci.yml` existence, `glab` CLI availability | `gitlab_in_scope` (expected: false) |
| Self-hosted runners | grep all workflows for `runs-on:` values other than GitHub-hosted labels | `self_hosted_runners` (expected: none) |
| gh auth | `gh auth status`, `gh api user` | `gh_identity` |

Write: `reports/sprint/workflow-harden-{date}/preflight/state_snapshot.json`

### Step 0.2 — Prior Findings Audit

If a previous `reports/sprint/workflow-harden-*/` bundle exists, re-verify its findings
against current file content (workflows drift between sprints). Assign verdict per finding:
`VERIFIED | PARTIALLY_VERIFIED | CONTRADICTED | UNVERIFIED`.

Write: `reports/sprint/workflow-harden-{date}/preflight/claim_audit.json`

### Step 0.3 — Hidden Problem Discovery

For every workflow file (and any script/action it calls), apply this 8-dimension probe:

| Probe | Question |
|-------|----------|
| P-01: Trigger/rules correctness | Are branch/path filters, PR vs push vs schedule behavior, and `workflow_dispatch` inputs correct and non-redundant? |
| P-02: Dependency/execution graph | Are `needs`, job ordering, and concurrency groups correct? Any race conditions? |
| P-03: Runner/environment | Confirmed `ubuntu-latest` (or documented reason otherwise) — no ambiguous or ambiguous-label self-hosted assumptions |
| P-04: Permissions & secrets | Least privilege `permissions:` block; secrets referenced only where needed; no hardcoded values |
| P-05: Action/dependency integrity | Actions pinned to a version tag or SHA (not floating `@main`); no deprecated actions |
| P-06: Build/test/lint correctness | Do commands actually validate what they claim; any swallowed exit codes; does a `continue-on-error` step feed a later blocking step's input? |
| P-07: Cache/artifact correctness | Cache keys correct and non-contaminating; artifacts produced/consumed correctly |
| P-08: CI weight | Redundant steps, missing dependency caching, unnecessary step count for what the job verifies |

Record each problem as HP-NN with: workflow file, probe, title, detail, severity, line
reference, evidence.

Write: `reports/sprint/workflow-harden-{date}/preflight/hidden_problems.json`

### Step 0.4 — Root Cause Model

Synthesize hidden problems into root causes (RC-01..RC-NN), mapping affected workflows.

Write: `reports/sprint/workflow-harden-{date}/preflight/root_causes.json`

### Step 0.5 — Finding Taxonomy

Classify every finding using this fixed set (do not invent new categories ad hoc):

`CONFIRMED_DEFECT | CONFIRMED_FRAGILITY | CONFIGURATION_DRIFT | CREDENTIAL_OR_PERMISSION_DEFECT | SECURITY_RISK | OBSERVABILITY_GAP | MAINTAINABILITY_GAP | HEALTHY_WITH_EVIDENCE | UNVERIFIED`

Assign severity tier:

| Tier | Criteria |
|------|----------|
| CRITICAL | Secret leak risk, silent false-green on a blocking check, supply-chain compromise vector |
| HIGH | Missing timeout risking indefinite hangs, a `continue-on-error` step whose output a blocking step trusts unconditionally |
| MEDIUM | Missing cache causing avoidable CI weight, PAT with broader scope than demonstrably needed |
| LOW | Style/consistency, SHA-pinning opportunity, minor redundant steps |

**Hard stop**: finding count > `--max-findings` -> HALT.

Write: `reports/sprint/workflow-harden-{date}/preflight/finding_taxonomy.json`

### Step 0.6 — Preserve/Harden/Redesign Matrix

Classify each workflow: `PRESERVE | HARDEN | REDESIGN`. (`DEPRECATE` is available but should
be rare — deleting a workflow file is a T-01 tracked action per `docs/DELETION_GOVERNANCE.md`
and needs a DGR; flag rather than act if a workflow looks removable.)

Write: `reports/sprint/workflow-harden-{date}/preflight/component_matrix.json`

### Step 0.7 — Taskcard Generation

Generate taskcards TC-00..TC-NN. Required fields:

```json
{
  "taskcard_id": "TC-00",
  "title": "...",
  "category": "SAFEGUARD | CORRECTNESS_FIX | CACHING | PERMISSION_REVIEW | DOCS",
  "phase": 1,
  "files_to_modify": [],
  "verification_criteria": { "local": "...", "remote": "..." },
  "related_findings": [],
  "dependencies": [],
  "specification": "..."
}
```

**Phase assignment rules:**
- Phase 1 (parallel, low-risk): missing `timeout-minutes`, dependency caching additions
- Phase 2: correctness fixes with cross-step dependencies (e.g. `continue-on-error` /
  downstream-consumer fixes)
- Phase 3: documentation of flagged-but-not-fixed items (PAT scope recommendation, etc.)

**Constraint**: every HIGH/CRITICAL finding must map to at least one taskcard, or an
explicit `DEFERRED` disposition with a reason (e.g. "requires secret owner action").

Write: `reports/sprint/workflow-harden-{date}/preflight/taskcards.json`

### Step 0.8 — Blocker Resolution

Identify and resolve execution blockers (e.g. `actionlint` not installed — install via a
safe method, or fall back to YAML-parse-only validation and note the gap).

Write: `reports/sprint/workflow-harden-{date}/preflight/blocker_resolution.json`

**If `--investigate-only` or `--dry-run`**: stop here.

**Save checkpoint**: `phase_state.json` with `investigation_complete: true`

---

## PHASES 1-3: Execution

### Standard Taskcard Execution Protocol

For each taskcard in phase order:

1. **Pre-check**: all dependency taskcards are `VERIFIED_CLOSED`
2. **Edit**: apply the taskcard's specification to the named files
3. **Local validation**: YAML parse + `actionlint` (if available) on every changed file
4. **Check invariants**: no mandatory/blocking step was removed or downgraded to
   `continue-on-error`; no `permissions:` broadened beyond the taskcard's justification
5. **Record**: update taskcard JSON -> `current_state: VERIFIED_CLOSED`
6. **On failure**: `git checkout -- {files_modified}` -> `current_state: FAILED`; skip dependents

### Phase 1 — Safeguards & Caching (parallel)

Typical: add `timeout-minutes` to jobs that lack it; add `actions/setup-python` `cache: pip`
(or `actions/cache`) where dependency installs repeat across jobs.

**Checkpoint**: `phase_1_complete`

### Phase 2 — Correctness Fixes

Typical: resolve any `continue-on-error` step whose JSON/output a later *blocking* step
consumes unconditionally — either remove `continue-on-error` if the step's success is truly
required, or make the consumer explicitly validate/fail on a missing or malformed artifact.

**Checkpoint**: `phase_2_complete`

### Phase 3 — Documentation & Deferred Items

Typical: record credential/permission scope recommendations (e.g. a cross-repo PAT's write
scope) in the evidence bundle as `DEFERRED` with a clear reason — not a code change.

**Checkpoint**: `phase_3_complete`

---

## POST-EXECUTION: Evidence Bundle

### Verification Steps

1. **Local**: YAML parse + `actionlint` on every changed workflow file
2. **Remote**: for `workflow_dispatch`-enabled workflows, `gh workflow run` + `gh run watch`
   to observe a real green run; for push-triggered workflows, monitor the next natural run
   via `gh run list` / `gh run view --log`
3. **Governance CI**: `skill-governance.yml` must pass on the commit that introduces/uses
   this skill — the concrete proof the skill itself is correctly registered

### Evidence Bundle Structure

```
reports/sprint/workflow-harden-{date}/
  preflight/
    state_snapshot.json
    claim_audit.json
    hidden_problems.json
    root_causes.json
    finding_taxonomy.json
    component_matrix.json
    taskcards.json
    blocker_resolution.json
  taskcards/
    TC-{NN}.json
  evidence/
    actionlint_results.json
    remote_run_results.json
  phase_state.json
  final_verdict.md
```

### Final Verdict Format

```markdown
# Sprint Verdict: Workflow Harden

**Date**: {ISO date}
**Sprint ID**: workflow-harden-{date}
**Verdict**: EXECUTION_COMPLETE | PARTIAL_EXECUTION | INVESTIGATION_ONLY

## Summary
- Taskcards: {executed}/{total}
- Findings: {count} by severity tier
- Workflows touched / unchanged (HEALTHY_WITH_EVIDENCE)

## Files Modified / Findings Addressed / Deferred Items / Acceptance Criteria
```

---

## Acceptance Criteria

| # | Criterion | Verification |
|---|-----------|--------------|
| AC-01 | Every workflow file manually reviewed | Entry in `hidden_problems.json` or explicit HEALTHY verdict per file |
| AC-02 | Every HIGH/CRITICAL finding has a taskcard or DEFERRED disposition | `taskcards.json` cross-check |
| AC-03 | No mandatory check weakened | Diff review: no `continue-on-error` added to a previously-blocking step without justification |
| AC-04 | Local validation passes | YAML parse + `actionlint` (or documented fallback) on all changed files |
| AC-05 | Remote verification | `skill-governance.yml` green on the introducing commit; touched workflows show a green run |
| AC-06 | Evidence bundle complete | All required files exist |

---

## Stop Conditions

| Condition | Action |
|-----------|--------|
| Finding count > `--max-findings` | HALT at Step 0.5 |
| GitLab CI or self-hosted runner discovered in Step 0.1 | HALT — this skill's scope assumption no longer holds; escalate before continuing |
| A fix would remove/weaken a mandatory gate | HALT that taskcard; escalate instead of applying |
| `content/` write attempted | BLOCKED by skill context |
| Taskcard FAILED + downstream depends | SKIP dependents; PARTIAL_EXECUTION |

---

## Error Handling

| Failure | Action |
|---------|--------|
| Git dirty for skill scope | HALT; stash or commit first |
| `gh auth status` fails | HALT; fix authentication before remote verification steps |
| `actionlint` unavailable and not installable safely | Fall back to YAML-parse-only local validation; note the gap in evidence |
| `--resume` but no `phase_state.json` | Start from Phase 0 |
| File already modified by a concurrent session | Abort taskcard; record with diff; do not silently overwrite |

---

## Rollback Matrix

| Trigger | Scope | Method |
|---------|-------|--------|
| Local validation failure | Last taskcard | `git checkout -- {files_modified}` |
| Remote run regression (previously-green workflow now fails) | Last taskcard | `git checkout -- {files_modified}`; investigate before retry |
| Sprint abort | All changes | `git checkout -- .github/workflows/ scripts/ci/` |

---

## State Management

### Phase State Schema

```json
{
  "sprint_id": "workflow-harden-{date}",
  "baseline_workflow_count": 0,
  "current_phase": 0,
  "phases": {
    "investigation": "COMPLETE | IN_PROGRESS | NOT_STARTED",
    "phase_1": "...", "phase_2": "...", "phase_3": "..."
  },
  "taskcards_closed": [],
  "taskcards_failed": [],
  "taskcards_skipped": [],
  "updated_at": "ISO-8601"
}
```

### Taskcard State Machine

```
NOT_STARTED -> IN_PROGRESS -> VERIFIED_CLOSED (validation + evidence written)
                            -> FAILED (revert + skip dependents)
                            -> SKIPPED (dependency failed)
```

### Resume Behavior

On `--resume`: read `phase_state.json`, find first non-COMPLETE phase, re-run Step 0.1 to
confirm the GitLab/self-hosted-runner assumption still holds before continuing.

---

## Shared Infrastructure (Reuse, Not Duplicate)

| Component | Path | How |
|-----------|------|-----|
| Checkpoint/resume | `scripts/pipeline/commands/governance/skill_context.py` | Standard begin/end |
| Override tokens | `scripts/pipeline/commands/governance/override_manager.py` | For any forbidden/unlisted path touched outside this skill's own scope (e.g. registry updates) |
| Path guard reference | `scripts/pipeline/commands/governance/path_guard.py` | `ALLOWED_PREFIXES` is the source of truth for what's governed vs. forbidden |
| Deletion governance | `docs/DELETION_GOVERNANCE.md` | Consult before ever deleting/renaming a workflow file (T-01) |

---

## Skill Context Close

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end \
  --skill S-115 --status completed
```

Use `--status failed` if halted due to error.

## LLM Metrics Obligation

This skill does not directly invoke `llm.professionalize.com`.
