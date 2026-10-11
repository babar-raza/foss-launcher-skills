# Skill Run Finalization Policy (NRM-034)

**Date**: 2026-05-21
**Decision**: Option C — documentation-only enforcement
**Status**: Accepted

## Problem

Sessions that use `git commit` directly (instead of `/commit` / S-76) leave skill runs in
`PENDING` state in the skill run ledger. These unfinalized runs accumulate and require
manual cleanup.

Specifically: the gap-closure sprint (SR-01) produced 4 pending runs that needed manual
finalization after the fact, because operators committed content changes with bare `git commit`
instead of routing through S-76.

## Decision

**Option C — documentation-only enforcement**: Document the requirement clearly and rely on
operator discipline. No automated gate was added at this stage because the failure mode
(pending runs) is recoverable and the cost of a hard gate is higher than the risk.

## Rule

**Always use `/commit` (S-76) for content commits.** S-76 automatically finalizes the
active skill run and records the commit SHA in the ledger.

**Direct `git commit` is permitted only for non-content changes**: scripts, docs, config,
and governance files where no skill run is active.

| Change type | Correct commit method |
|-------------|----------------------|
| Content (content/ directory) | `/commit` (S-76) |
| Scripts, config, docs | `git commit` directly (no active skill run) |
| Mixed (content + scripts) | `/commit` (S-76) — S-76 stages and commits all |

## Evidence

SR-01 (gap-closure sprint session ledger) documented 4 pending runs requiring manual
finalization. All 4 were caused by operators using `git commit` directly while a skill
run was active.

## Exception: Manual Finalization

If `/commit` (S-76) is blocked (e.g., hook failure, protected path conflict), finalize
the skill run manually after committing:

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/ops/skill_run_manager.py \
  finalize --run-id {id} --outcome success --commit-sha $(git rev-parse HEAD)
```

To find the active run ID:
```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/ops/skill_run_manager.py list --status pending
```

## Related

- S-76 (commit skill): `.claude/commands/commit.md` / `skills/commit.md`
- Session ledger: `scripts/pipeline/commands/ops/session_ledger.py`
- Skill run manager: `scripts/pipeline/commands/ops/skill_run_manager.py`
