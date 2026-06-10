<!-- CONTRACT: agent-executed
     purpose: Cleanroom content regeneration -- regenerate, diff, review, apply, verify, commit-gate for one family/platform
     cli: PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/ops/cleanroom_regen.py {mode} --family {family} --platform {platform} [options]
     postcondition: all run artifacts written to runs/cleanroom/{run_id}/
     postcondition: commit-ready mode writes tracked evidence to reports/cleanroom/{run_id}/
     postcondition: apply-decision uses baseline_git_sha for reverts, never HEAD
     postcondition: content not modified unless on isolated branch with --confirm-overwrite
     id: S-106
     depends_on: [S-44, S-48, S-49, S-50, S-53]
     ported_from: aspose.org S-97
     verified: 2026-05-05
-->

# S-106: Cleanroom Regen -- Regenerate, Diff, Review, Apply, Gate

Runs a full cleanroom regeneration workflow for one `{family}/{platform}` target.
Regenerates content from scratch, classifies every change, applies editorial verdicts,
and produces a commit-readiness gate.

**Arguments:** `$ARGUMENTS`
**Expected format:** `{family} {platform} [--mode {mode}] [--subdomain {sub}] [--run-id {id}] [--level 1|2]`

---

## Arguments

Parse `$ARGUMENTS` into:

- `family` -- e.g. `cells`, `slides`, `words`
- `platform` -- e.g. `java`, `net`, `python`, `cpp`
- `--mode` -- one of: `inspect`, `snapshot`, `regenerate-cleanroom`, `diff`, `review`,
  `apply-decision`, `verify`, `commit-ready` (default: `inspect`)
- `--subdomain` -- `reference`, `blog`, `docs`, `kb`, `products`, or omit for all
- `--run-id` -- explicit run ID (default: auto-generated `YYYYMMDD-HHMMSS-{family}-{platform}`)
- `--level` -- `1` (content overwrite, default) or `2` (full launch replay)
- `--confirm-overwrite` -- required for `regenerate-cleanroom` mode
- `--keep-risky-pending` -- leave RISKY_REVIEW files on disk instead of reverting
- `--keep-unclear-pending` -- leave UNCLEAR_NEEDS_EVIDENCE files on disk instead of reverting

---

## Mode Reference

All modes delegate to `scripts/pipeline/commands/ops/cleanroom_regen.py`.

### Mode 1: `inspect` (read-only)

Validates scope readiness. Safe to run on main. Does not create a run lock.

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/ops/cleanroom_regen.py inspect \
  --family {family} --platform {platform} \
  [--subdomain {sub}] [--run-id {id}]
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

**Output:** `baseline-manifest.json`, `git-baseline.json`, `run_state.json`

---

### Mode 3: `regenerate-cleanroom` (WRITES -- DESTRUCTIVE)

**Gate: MUST be on isolated branch. MUST pass `--confirm-overwrite`. MUST have baseline manifest.**

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/ops/cleanroom_regen.py regenerate-cleanroom \
  --family {family} --platform {platform} --run-id {id} \
  --confirm-overwrite [--level 1|2]
```

---

### Mode 4: `diff` (read-only)

Classifies every content change vs baseline.

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/ops/cleanroom_regen.py diff \
  --family {family} --platform {platform} --run-id {id}
```

---

### Mode 5: `review` (read-only)

Applies page-type-aware editorial rubric to classify ADDED/EDITED files.

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/ops/cleanroom_regen.py review \
  --family {family} --platform {platform} --run-id {id}
```

**Verdict hierarchy:** BAD_REVERT > RISKY_REVIEW > UNCLEAR_NEEDS_EVIDENCE > GOOD_KEEP

---

### Mode 6: `apply-decision` (WRITES -- reverts bad files)

Reverts BAD_REVERT files to `baseline_git_sha` (NEVER HEAD).

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/ops/cleanroom_regen.py apply-decision \
  --family {family} --platform {platform} --run-id {id} \
  [--keep-risky-pending] [--keep-unclear-pending]
```

---

### Mode 7: `verify` (read-only)

Runs pytest suite on GOOD_KEEP files.

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/ops/cleanroom_regen.py verify \
  --family {family} --platform {platform} --run-id {id}
```

---

### Mode 8: `commit-ready` (read-only)

Produces commit-readiness checklist (13 checks). Generates commit message template on PASS.

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/ops/cleanroom_regen.py commit-ready \
  --family {family} --platform {platform} --run-id {id}
```

---

## Standard Execution Sequence

```bash
# 0. Ensure on isolated branch
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
| 3 | Dirty content tree blocker |
| 4 | Unsafe branch -- regenerate-cleanroom refused on main |
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
