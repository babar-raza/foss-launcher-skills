---
name: cleanroom-regen
id: S-97
description: >
  Skill description pending
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

<!-- CONTRACT: agent-executed
     purpose: Cleanroom content regeneration — regenerate, diff, review, apply, verify, commit-gate for one family/platform
     cli: python scripts/pipeline/commands/ops/cleanroom_regen.py {mode} --family {family} --platform {platform} [options]
     postcondition: all run artifacts written to runs/cleanroom/{run_id}/
     postcondition: commit-ready mode writes tracked evidence to reports/cleanroom/{run_id}/
     postcondition: apply-decision uses baseline_git_sha for reverts, never HEAD
     postcondition: content/ unchanged unless on isolated branch with --confirm-overwrite
     id: S-97
     depends_on: [S-62, S-57, S-56, S-58, S-61]
     verified: 2026-05-02
-->

# S-97: Cleanroom Regen — Regenerate, Diff, Review, Apply, Gate

Runs a full cleanroom regeneration workflow for one `{family}/{platform}` target.
Regenerates content from scratch, classifies every change, applies editorial verdicts,
and produces a commit-readiness gate.

**Arguments:** `$ARGUMENTS`
**Expected format:** `{family} {platform} [--mode {mode}] [--subdomain {sub}] [--run-id {id}] [--level 1|2]`

---

## Skill Context Gate

> Run before ANY step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-97 --scope "data/schemas/**,scripts/pipeline/**,.claude/commands/**,reports/**"
> ```

---

## Arguments

Parse `$ARGUMENTS` into:

- `family` — e.g. `cells`, `slides`, `words`
- `platform` — e.g. `java`, `net`, `python`, `cpp`
- `--mode` — one of: `inspect`, `snapshot`, `regenerate-cleanroom`, `diff`, `review`,
  `apply-decision`, `verify`, `commit-ready` (default: `inspect`)
- `--subdomain` — `reference`, `blog`, `docs`, `kb`, `products`, or omit for all
- `--run-id` — explicit run ID (default: auto-generated `YYYYMMDD-HHMMSS-{family}-{platform}`)
- `--level` — `1` (content overwrite, default) or `2` (full launch replay including knowledge rebuild)
- `--confirm-overwrite` — required for `regenerate-cleanroom` mode
- `--keep-risky-pending` — leave RISKY_REVIEW files on disk instead of reverting
- `--keep-unclear-pending` — leave UNCLEAR_NEEDS_EVIDENCE files on disk instead of reverting

---

## Mode Reference

All modes delegate to `scripts/pipeline/commands/ops/cleanroom_regen.py`.

### Mode 1: `inspect` (read-only)

Validates scope readiness. Safe to run on main. Does not create a run lock.

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/ops/cleanroom_regen.py inspect \
  --family {family} --platform {platform} \
  [--subdomain {sub}] [--run-id {id}] [--runs-root runs/cleanroom]
```

**Output:** `runs/cleanroom/{run_id}/inspect-report.json`
**Exit codes:** 0=ready, 1=blockers found, 2=invalid args

---

### Mode 2: `snapshot` (read-only)

Records baseline content state. Creates run lock. Must be run before any destructive mode.

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/ops/cleanroom_regen.py snapshot \
  --family {family} --platform {platform} \
  [--subdomain {sub}] [--run-id {id}]
```

**Output:** `baseline-manifest.json`, `git-baseline.json`, `run_state.json`, `baseline-summary.md`

---

### Mode 3: `regenerate-cleanroom` (WRITES to content/ — DESTRUCTIVE)

**Gate: MUST be on isolated branch. MUST pass `--confirm-overwrite`. MUST have baseline manifest.**

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/ops/cleanroom_regen.py regenerate-cleanroom \
  --family {family} --platform {platform} --run-id {id} \
  --confirm-overwrite [--level 1|2]
```

**Two-phase protocol for non-reference subdomains:**

- **Phase A (CLI):** The CLI runs `batch_reference.py --rebuild-all` for reference subdomain.
  For `blog`, `docs`, `kb`, `products`, the CLI emits `regeneration-plan.json` with one entry per page
  and a skeleton `agent-execution-ledger.json` with `phase_b_complete: false`.

- **Phase B (THIS SKILL, agent context):** After Phase A, read `regeneration-plan.json`.
  For each entry with `status: PLANNED`:
  1. Mark entry `status: RUNNING` in ledger, set `started_at`
  2. Invoke named generator skill with `skill_args`
  3. Verify output file(s) exist on disk
  4. Set `status: COMPLETED` (with `output_files`) or `status: FAILED` (with `error`)
  5. Append result to `agent-page-results.json`
  6. If FAILED: also append to `agent-failures.json` with `retry_hint`
  7. Pages with `auto_updatable: false`: set `status: SKIPPED_WITH_REASON`, note in `agent_notes`
  8. After all entries reach terminal state: write final ledger with `phase_b_complete: true`

  **Fake-completion guards (enforce all):**
  - COMPLETED requires non-empty `output_files`
  - Every file in `output_files` must exist on disk at write time
  - Every file in `output_files` must be within declared scope (out-of-scope = FAILED)
  - SKIPPED_WITH_REASON requires non-empty `agent_notes`
  - Phase B does NOT proceed to Mode 4 (diff) until all entries are terminal

**Output:** `regeneration-log.json` (reference), `regeneration-plan.json`, `agent-execution-ledger.json`

---

### Mode 4: `diff` (read-only)

Classifies every content change vs baseline. Requires Phase B complete for non-reference subdomains.

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/ops/cleanroom_regen.py diff \
  --family {family} --platform {platform} --run-id {id}
```

**Output:** `diff-report.json`, per-category JSON files, `changed-files.md`

---

### Mode 5: `review` (read-only)

Applies page-type-aware editorial rubric to classify ADDED/EDITED files.

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/ops/cleanroom_regen.py review \
  --family {family} --platform {platform} --run-id {id}
```

**Verdict hierarchy:** BAD_REVERT > RISKY_REVIEW > UNCLEAR_NEEDS_EVIDENCE > GOOD_KEEP

**Output:** `review-report.json`, `review-summary.md`

After review mode: the agent reads `review-summary.md` and confirms each verdict.
Apply deterministic verdicts (GOOD_KEEP, BAD_REVERT) automatically.
Escalate only genuinely ambiguous files — do NOT block on deterministic verdicts.

---

### Mode 6: `apply-decision` (WRITES to content/ — reverts bad files)

Reverts BAD_REVERT files to `baseline_git_sha` (NEVER HEAD). Deletes new bad files.
By default also reverts RISKY_REVIEW and UNCLEAR files (conservative).

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/ops/cleanroom_regen.py apply-decision \
  --family {family} --platform {platform} --run-id {id} \
  [--keep-risky-pending] [--keep-unclear-pending]
```

**Output:** `decision-ledger.json`

---

### Mode 7: `verify` (read-only)

Runs validation chain on all GOOD_KEEP files. Runs full pytest suite.

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/ops/cleanroom_regen.py verify \
  --family {family} --platform {platform} --run-id {id}
```

**Output:** `validator-report.json`, `test-report.json`

---

### Mode 8: `commit-ready` (read-only)

Produces commit-readiness checklist (13 checks). Generates commit message template on PASS.

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/ops/cleanroom_regen.py commit-ready \
  --family {family} --platform {platform} --run-id {id}
```

**Output:** `runs/cleanroom/{run_id}/commit-readiness-report.json`
**Tracked evidence:** `reports/cleanroom/{run_id}/commit-readiness-report.json`

On PASS, emit the `commit_message_template` from the report and proceed with `/commit`.

---

## Standard Execution Sequence

```bash
# 0. Ensure on isolated branch (never run regenerate-cleanroom on main)
git checkout -b test/cleanroom-{family}-{platform}-$(date +%Y%m%d)

# 1. Inspect (safe on any branch)
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/ops/cleanroom_regen.py inspect \
  --family {family} --platform {platform} --run-id {run_id}

# 2. Snapshot
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/ops/cleanroom_regen.py snapshot \
  --family {family} --platform {platform} --run-id {run_id}

# 3. Regenerate (CLI Phase A)
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/ops/cleanroom_regen.py regenerate-cleanroom \
  --family {family} --platform {platform} --run-id {run_id} --confirm-overwrite

# 3b. Phase B (agent) — only if regeneration-plan.json has non-reference entries

# 4. Diff
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/ops/cleanroom_regen.py diff \
  --family {family} --platform {platform} --run-id {run_id}

# 5. Review
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/ops/cleanroom_regen.py review \
  --family {family} --platform {platform} --run-id {run_id}

# 6. Apply decision
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/ops/cleanroom_regen.py apply-decision \
  --family {family} --platform {platform} --run-id {run_id}

# 7. Verify
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/ops/cleanroom_regen.py verify \
  --family {family} --platform {platform} --run-id {run_id}

# 8. Commit ready
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/ops/cleanroom_regen.py commit-ready \
  --family {family} --platform {platform} --run-id {run_id}
```

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Readiness blocker |
| 2 | Invalid arguments or unknown mode |
| 3 | Dirty content/ tree blocker |
| 4 | Unsafe branch — regenerate-cleanroom refused on main |
| 5 | Missing prerequisite artifact from prior mode |
| 6 | Schema validation failure on artifact |
| 7 | Generation failure during regenerate-cleanroom |
| 8 | Diff classification error |
| 9 | BAD_REVERT files found |
| 10 | Unresolved RISKY or UNCLEAR files |
| 11 | Validator failure |
| 12 | Test suite failure |
| 13 | Commit-readiness gate failed |
| 14 | Out-of-scope content changes detected |
| 15 | Run lock conflict |

---

## Skill Run Record

After successful `commit-ready` (Mode 8 EXIT 0):

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/ops/skill_run_manager.py record \
  --skill S-97 --family {family} --platform {platform} \
  --run-id {run_id} --status success
```

End skill context after all modes complete:

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-97
```
