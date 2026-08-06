---
name: readme-refresh
id: S-120
description: >
  Skill description pending
---

<!-- CONTRACT: registered-cli-wrapper
     purpose: operate one run-bound README refresh for one FOSS product repository
     preconditions: product active in data/products.json, not excluded, real push/admin access
     postcondition: run is AWAITING_REVIEW, APPROVED, PUSHED, BLOCKED, or ABANDONED
     idempotent: yes — immutable receipts, state checkpoints, single-owner-per-product locking
     verified: 2026-08-06
-->

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# S-120: README Refresh

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}`

## Official execution contract

Use only the registered control plane:

```bash
.venv/Scripts/python scripts/pipeline/commands/foss/readme_refresh_run.py start FAMILY PLATFORM \
  [--run-id ID] [--session-id ID] [--skip-preflight]
.venv/Scripts/python scripts/pipeline/commands/foss/readme_refresh_run.py plan --run-id ID [--session-id ID]
.venv/Scripts/python scripts/pipeline/commands/foss/readme_refresh_run.py ingest-candidate --run-id ID [--session-id ID]
.venv/Scripts/python scripts/pipeline/commands/foss/readme_refresh_run.py verify-examples --run-id ID [--session-id ID]
.venv/Scripts/python scripts/pipeline/commands/foss/readme_refresh_run.py recheck --run-id ID [--session-id ID]
.venv/Scripts/python scripts/pipeline/commands/foss/readme_refresh_run.py status --run-id ID
.venv/Scripts/python scripts/pipeline/commands/foss/readme_refresh_run.py approve --run-id ID \
  --note TEXT [--session-id ID]
.venv/Scripts/python scripts/pipeline/commands/foss/readme_refresh_run.py push --run-id ID \
  [--session-id ID] [--dry-run]
.venv/Scripts/python scripts/pipeline/commands/foss/readme_refresh_run.py verify --run-id ID [--session-id ID]
.venv/Scripts/python scripts/pipeline/commands/foss/readme_refresh_run.py abandon --run-id ID \
  --reason TEXT [--session-id ID]
.venv/Scripts/python scripts/pipeline/commands/foss/readme_refresh_run.py recover --run-id ID \
  --reason TEXT [--session-id ID]
```

State machine: `CREATED → INPUTS_PINNED → PLANNED → VERIFYING_EXAMPLES → AWAITING_REVIEW →
APPROVED → PUSHING → PUSHED`. `BLOCKED` is re-enterable from `INPUTS_PINNED`/`PLANNED`/
`VERIFYING_EXAMPLES`/`PUSHING`. `ABANDONED` is terminal from any non-terminal state. `PUSHED`
and `ABANDONED` are the only terminal states. Every mutating call requires a stable session
identity (`--session-id` or `AGENT_SESSION_ID`/`CODEX_THREAD_ID`/`CLAUDE_CODE_SESSION_ID`) and
is checked against the run's `session_owner` — a different session cannot touch someone else's
run. One `ACTIVE.json` per `(family, platform)` plus a `FileLock` prevents two runs owning the
same product concurrently.

## Steps

> **Skill context gate** — run before `start`:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-120 --scope "reports/repo-presenter/{family}/{platform}/*,reports/readme_refresh_runs/{family}/{platform}/*"
> ```

1. **`start`** — resolves the product against `data/products.json` (must be `active: true`,
   not in `data/registry_exclusions.json`), runs a real `gh api repos/{org}/{repo} --jq
   .permissions` pre-flight check (refuses without real push/admin access — this is the literal
   fix for `foss-java-publish`/S-110's documented gap, which only assumed access as prose and
   never checked it), pins the clone-cache `HEAD` SHA. Transitions `CREATED → INPUTS_PINNED`.

2. **`plan`** — emits `facts/factpack.json`: real archetype classification (`data/
   diagram_archetypes.json`, defaulting to `transform` when no override entry exists), real
   capability-dependency edges (`data/diagram_capability_dependencies.json` — `None` when the
   product has never been traced, which must never be read as "confirmed independent"), real
   install/package data (`data/package_registry.json`), real case-sensitive license-file
   detection against the clone cache, and the old upstream README's real link/heading
   inventory. Transitions `INPUTS_PINNED → PLANNED`.

3. **Agent composes the candidate.** The script does not write README prose — the agent reads
   `facts/factpack.json` and writes `reports/repo-presenter/{family}/{platform}/readme.md`
   directly, following the Template section's standard structure (plan:
   `C:\Users\prora\.claude\plans\d-users-prora-onedrive-documents-github-humble-tome.md`). Every
   item in the factpack's `old_readme_inventory` (links, headings) must either land somewhere
   real in the candidate or be a deliberate, verified drop — `ingest-candidate`'s
   `check_dropped_content` hard gate below enforces this, it is not optional diligence.

4. **`ingest-candidate`** — runs the real deterministic checks module
   (`scripts/pipeline/commands/foss/readme_refresh_checks.py`, 19 functions) against the
   candidate. **Hard gates** (any finding blocks the transition): required sections present,
   no `forum.aspose.com`/`*.aspose.app` links, license link target resolves case-sensitively on
   disk, At-a-glance diagram has no orphaned Capability nodes, the diagram matches the recorded
   `data/diagram_capability_dependencies.json` entry (no-op when none exists), no undisclosed
   BLOCKING command from `upstream-issues.md` is repeated as a normal install/build step, and no
   real old-README link/heading was silently dropped. **Heuristic checks** (surfaced for
   judgment, never auto-fail): suspicious direct-PRODUCT diagram edges, unreachable capability
   nodes, mechanism-duplicate output nodes, process-narration smells, Enterprise Edition
   anchor-text naming, a weak API-reference intro sentence, and named-member accuracy (a
   grep-based heuristic — see that function's own docstring for its honest, stated scope
   limits, most importantly that it does not trace inheritance). Transitions
   `PLANNED → VERIFYING_EXAMPLES` only once every hard gate passes.

5. **`verify-examples`** — runs the (pluggable) per-language compile/run verification pass and
   writes `verification/result.json` plus `upstream-issues.md` (written for every run, including
   the clean case — an absent file is itself a bug). **Honest scope note**: the default runner
   reports every code block `BLOCKED-WITH-REASON: TOOLCHAIN-UNAVAILABLE` rather than claiming a
   compile that never happened — real per-language toolchain wiring (`javac`/`javap`, `dotnet`,
   `go build`, `cargo`, `cmake`/`ninja`, a disposable Python venv, `tsc`) is separate, follow-on
   work, injectable via `configure(verification_runner=...)`. Only transitions
   `VERIFYING_EXAMPLES → AWAITING_REVIEW` once every block has a real, named status.

6. **`recheck`** — re-runs the deterministic checks in place after manual edits during
   `AWAITING_REVIEW`, without a state transition. Use this after applying reviewer feedback
   instead of re-planning from scratch.

7. **`approve`** — **the skill must never call this on its own initiative; only on an
   unambiguous, fresh instruction from the user in that turn.** Re-verifies the pinned clone-cache
   `HEAD` hasn't drifted since `start`; if it has, forces the run back to `PLANNED` for re-review
   rather than approving stale content — `approve` itself will raise in that case, it never
   silently substitutes a replan for an approval.

8. **`push`** — disposable-clone + branch + git-plumbing commit (`write-tree`/`commit-tree`/
   `update-ref`, never the shared clone cache) + surgical-diff check (declared file set only,
   currently just `README.md`) + push + `gh pr create --draft`. `--dry-run` rehearses every step
   up to (not including) the live network write, then returns the run to `APPROVED` — it never
   reaches `PUSHED` without a real push. Draft PRs always — a human explicitly marks "Ready for
   review"; this skill never merges.

9. **`verify`** — post-push, safely re-runnable any time: confirms the PR still exists and its
   head matches the approved candidate.

## Post-conditions

- `AWAITING_REVIEW`: candidate has passed every hard-gate deterministic check and every code
  block has a named verification status.
- `PUSHED`: a draft PR is open against the product's real default branch, with `README.md` as
  the only changed file, evidence recorded at `reports/readme_refresh_runs/{family}/{platform}/
  {run_id}/` and `reports/repo_presenter_actions.jsonl` (once that shared ledger is built —
  not yet wired into this pass).

## Error handling

- `start`: pre-flight access failure, product not found/excluded, or an already-active run for
  the same product all raise before any state is created.
- `ingest-candidate`: any hard-gate finding raises with `checks/result.json` written first, so
  the specific failing check is always inspectable, not just a bare failure message.
- `verify-examples`: raises if any code block has no named status; never silently advances.
- `push`: any failure (clone, plumbing, surgical-diff mismatch, network push, `gh pr create`)
  transitions the run to `BLOCKED` with the failure reason recorded, rather than leaving it in
  an ambiguous `PUSHING` state — `recover` resumes from `resume_state` afterward.

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-120 --status completed
> ```
