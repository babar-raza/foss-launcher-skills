---
name: plan-health-watchdog
id: S-122
description: >
  Detect stalled non-terminal taskcards and plan-markdown prose that
  contradicts the structured taskcards.jsonl store, via field comparison
  not fragile regex-only guessing. Generalized from aspose.org's
  plan-health-watchdog skill (S-113) -- ported 2026-08-30.
args: "--mission-id <id> [--plan-file <plan.md>] [--threshold-days N]"
---

# S-122: Plan Health Watchdog -- Structured Stall Detection

**Arguments**: $ARGUMENTS (`--mission-id` required; `--plan-file` and
`--threshold-days` optional)

## Purpose
Make "is this plan's prose still true, and is any task silently stuck?" a
machine-checkable question instead of a re-reading-the-whole-doc exercise.
Queries the **structured** `taskcards.jsonl` store's `recorded_at`/`status`
fields directly -- a reliable field comparison, not a fragile scan of
markdown phrasing a future edit could defeat.

## When to use
- At session start, before a new plan claims a problem space an existing
  plan/mission already owns.
- Periodically, to surface non-terminal tasks that have gone quiet.

## Adaptation note (generalized from source)
Source's version references a specific schema revision tag and a specific
prior-incident plan by name. This port keeps the two genuinely portable
mechanisms -- structured-field stall detection and markdown/store parity
checking -- and drops the schema-revision label and the incident-specific
narrative (this repo's `taskcard_store.py`/`schema_validators.py`, ported
2026-08-29, use their own unversioned schema; there is no equivalent tag to
carry over). Source also names an optional "LLM-assisted judgment" step for
confirming a doc's "this is live" claim against repo state; this port omits
it -- this repo's ported taskcard/CLI stack has no LLM-router equivalent
wired to a skill of this kind, and adding one speculatively would be
scope this skill doesn't need to close.

## Pre-conditions
- A `taskcards.jsonl` exists for the mission at
  `reports/plan_state/{mission_id}/taskcards.jsonl` (via `taskcard_store.py`).
  If absent, the mission is untracked -- the tool reports this and exits 0
  (advisory, not a failure).

## Steps

### 1. Run the watchdog
```bash
.venv/Scripts/python.exe scripts/pipeline/commands/ops/plan_health_watchdog.py \
  --mission-id <mission_id> [--plan-file <plan.md>] [--threshold-days 5]
```
Exit 0: no stalled tasks, no contradictions. Exit 1: at least one of either.

### 2. Stall query
For each non-terminal task (status not in CLOSED / *_VERIFIED /
PILOT_PROVEN / INDEPENDENTLY_REVIEWED / SUPERSEDED / OUT_OF_SCOPE), compare
`recorded_at` against the threshold (default 5 business days, Mon-Fri
calendar, no holiday table -- a documented simplification). A task stuck at
the same status past the threshold is the target signal.

### 3. Parity query (only if `--plan-file` given)
Scans the plan markdown for an explicit `[STATUS: ...]` tag on the same
line as a known task ID (e.g. `**SYNC-5 -- Java/Maven cluster [STATUS:
CLOSED]**`), and flags any tagged line whose claim contradicts the
store's actual current status for that ID. Silence in the markdown is
never a contradiction -- a task ID mentioned in prose with no `[STATUS:
...]` tag is not a claim, so it is never compared. This is the same
explicit-tag design aspose.org's own check_taskcard_plan_parity.py uses;
an earlier version of this port instead scanned for loose done/not-done
vocabulary near a task ID and threw false positives on prose that merely
*mentioned* an ID (e.g. describing future closeout criteria) -- adopting
the tag requirement removed that failure mode rather than just tolerating
it. `--strict-coverage` additionally flags any non-excluded store task
that carries no markdown tag at all.

## Output
Printed report only (no file written): stalled-task list with ages, and
the parity verdict (contradicting lines, if any, with line numbers).

## Post-conditions
- Read-only: never edits the plan, taskcards, or content.
- Idempotent (pure read).

## Related Skills
None yet in this repo. Backing modules: `scripts/pipeline/lib/taskcard_store.py`,
`scripts/ci/checks/check_taskcard_plan_parity.py`.
