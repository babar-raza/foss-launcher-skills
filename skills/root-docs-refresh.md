---
name: root-docs-refresh
id: S-121
description: >
  Repeatable, deterministic-check-driven refresh of the seven root-level operator/governance
  docs (OPERATOR_GUIDE.md, RUNBOOK.md, CODEX.md, GRADE_CONTRACT.md,
  LAYMAN_SYSTEM_STATUS_REVIEW.md, TASK_BACKLOG.md, TASK_BACKLOG_20260521.md) through the
  registered run-bound root_docs_refresh_run.py state machine.
args: "(no arguments — always operates on the fixed seven-file set)"
---

<!-- CONTRACT: registered-cli-wrapper
     purpose: operate one run-bound refresh of this repo's seven root operator/governance docs
     preconditions: none external — this repo is always the target, no per-product resolution
     postcondition: run is AWAITING_REVIEW, APPROVED, COMMITTED, BLOCKED, or ABANDONED
     idempotent: yes — immutable receipts, state checkpoints, single global-lock ownership
     verified: 2026-08-07
-->

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# S-121: Root Docs Refresh

**Arguments**: none — always operates on the fixed seven-file set.

## Why this skill exists

These seven files drift from the repo's true state in ways no prior gate caught: dead
references to deleted packages, mislabeled skill IDs, a "FROZEN" grading contract that
silently outpaced its own code, dated snapshots read as current. A prior manual audit found
and fixed seven such defects by hand; this skill exists so the next round doesn't repeat that
manual audit from scratch. The deterministic checks it runs
(`scripts/pipeline/commands/governance/root_docs_checks.py`) are the **same functions**
imported by `scripts/ci/checks/check_root_docs_truth.py`'s commit-time gate — this skill and
the automated gate can never disagree about what "correct" means, because they call the same
code. See plan `moonlit-strolling-sunset.md` for the full root-cause diagnosis.

## Official execution contract

Use only the registered control plane:

```bash
.venv/Scripts/python scripts/pipeline/commands/governance/root_docs_refresh_run.py plan \
  [--run-id ID] [--session-id ID]
.venv/Scripts/python scripts/pipeline/commands/governance/root_docs_refresh_run.py recheck \
  --run-id ID
.venv/Scripts/python scripts/pipeline/commands/governance/root_docs_refresh_run.py submit \
  --run-id ID
.venv/Scripts/python scripts/pipeline/commands/governance/root_docs_refresh_run.py approve \
  --run-id ID --note TEXT [--session-id ID]
.venv/Scripts/python scripts/pipeline/commands/governance/root_docs_refresh_run.py commit-prepare \
  --run-id ID --files PATH [PATH ...] --reason TEXT
.venv/Scripts/python scripts/pipeline/commands/governance/root_docs_refresh_run.py finalize \
  --run-id ID --commit-sha SHA
.venv/Scripts/python scripts/pipeline/commands/governance/root_docs_refresh_run.py status \
  --run-id ID
.venv/Scripts/python scripts/pipeline/commands/governance/root_docs_refresh_run.py abandon \
  --run-id ID --reason TEXT
```

State machine: `CREATED → FACTS_PINNED → AWAITING_REVIEW → APPROVED → COMMITTED`. `BLOCKED`
is re-enterable from `FACTS_PINNED`/`AWAITING_REVIEW`/`APPROVED`. `ABANDONED` is terminal from
any non-terminal state. `COMMITTED` and `ABANDONED` are the only terminal states. Every
mutating call requires a stable session identity (`--session-id` or
`AGENT_SESSION_ID`/`CODEX_THREAD_ID`/`CLAUDE_CODE_SESSION_ID`). One global `ACTIVE.json` +
`FileLock` prevents two sessions from running a root-docs-refresh concurrently — a direct
defense against this repo's documented concurrent-session hazard (ST-021).

## Steps

> **Skill context gate** — run before `plan`:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-121 --scope "reports/root_docs_refresh/*"
> ```

1. **`plan`** — pins the current git `HEAD` SHA, runs the full deterministic check suite
   against the seven files' current on-disk content, and writes
   `reports/root_docs_refresh/{run_id}/factpack.json` (live facts: active-product count from
   `data/products.json`, per-file check results) plus `checks/result.json`. Transitions
   `CREATED → FACTS_PINNED`.

2. **Agent/human remediation** (not a script step). Read `checks/result.json`. For each
   `HARD_GATE` finding, fix it — these are unambiguous (a referenced path doesn't exist, a
   skill ID is wrong, `GRADE_CONTRACT.md`'s frozen baseline disagrees with the code constant).
   For each `HEURISTIC` finding, use judgment — is this hardcoded count a candidate to point
   at its live source instead, does this file look like a dead snapshot that should move to
   `docs/_archive/root-orphans/`. This is deliberately the only judgment-bound step, scoped to
   exactly what `checks/result.json` surfaced — not an open-ended re-read of all seven files.

3. **`recheck`** — re-runs every check against the current working-tree state, in place,
   without a transition. Use after each remediation pass instead of re-planning from scratch.

4. **`submit`** — **hard gate**: `FACTS_PINNED → AWAITING_REVIEW` only when the latest check
   results show zero `HARD_GATE` findings across all seven files. Raises, listing every
   blocking finding by file and message, otherwise — never silently advances.

5. **`approve`** — **the skill must never call this on its own initiative; only on an
   unambiguous, fresh instruction from the user in that turn.** Re-verifies the pinned git
   `HEAD` hasn't moved since `plan`; if it has (another session committed to `main` in the
   meantime), forces the run back to `FACTS_PINNED` for re-plan rather than approving a
   possibly-stale factpack — `approve` itself raises in that case, it never silently
   substitutes a re-plan for an approval.

6. **`commit-prepare`** — creates one override token per changed file
   (`override_manager.py`), pre-authorizing the subsequent `/commit` invocation against
   `path_guard`'s default-deny for root-level writes. Does not touch git itself — `/commit`
   (S-76) is the only sanctioned commit path, invoked as a separate, explicit skill call after
   this step, never `git commit` directly.

7. **`finalize`** — call after `/commit` (S-76) has actually landed the change. Records the
   resulting commit SHA, consumes every override token `commit-prepare` created, and
   transitions `APPROVED → COMMITTED`.

## Post-conditions

- `AWAITING_REVIEW`: the candidate has passed every hard-gate deterministic check.
- `COMMITTED`: the seven files reflect current repo state, evidence recorded at
  `reports/root_docs_refresh/{run_id}/` (factpack, before/after check results, commit SHA).

## Error handling

- `plan`: raises before creating any state if another session's run is active and
  non-terminal — never silently takes over someone else's in-flight refresh.
- `submit`: raises with the full list of blocking findings; the manifest stays `FACTS_PINNED`.
- `approve`: raises and forces `FACTS_PINNED` on git-HEAD drift, or on an empty `--note`.
- `finalize`: token-consumption failures are swallowed (already consumed/missing is not a
  finalize-blocking condition) — the commit itself already landed by this point.

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-121 --status completed
> ```
