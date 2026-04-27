---
name: backlog
id: S-88
description: >
  Unified planning and backlog management across sessions. View, update, add,
  triage, archive, and handoff backlog items. State lives in backlog/ directory.
args: "[subcommand] [args...]"
---

# S-88: Backlog — Unified Planning & Backlog Management

**Arguments**: `[subcommand] [args...]`
**Trigger**: Run `/backlog` to view current state, or with a subcommand to modify.

## Purpose

Maintains a durable backlog system across sessions. Surfaces reminders, tracks
plan-level and item-level work, supports investigation items without plans, and
provides session handoff for context switches.

All backlog state lives in `backlog/` (should be gitignored, internal-only).

**SAFE-FAILURE**: If `backlog/` or `plans/` directories do not exist, stop and ask
the operator. Never create non-standard directories like `.kilo-backlog/` etc.

## File Structure

```
backlog/
├── BACKLOG.md      — main item list with status, priority, wave, blockers
├── REMINDERS.md    — due-date reminders and session-start alerts
├── HANDOFF.md      — session handoff: what was done, what's next, what's blocked
└── inbox.md        — unprocessed intake items (triage queue)
```

## BACKLOG.md Schema

Each item follows this format:

```markdown
| ID | Title | Status | Priority | Category | Size | Wave | Blocker | Plan |
|----|-------|--------|----------|----------|------|------|---------|------|
| B-001 | Add session-start skill | Active | P1 | skills | M | 0 | — | plans/b-001-session-start.md |
```

Status values: `Inbox | Active | Queued | Deferred | Done`
Priority values: `P0 | P1 | P2 | P3`
Size values: `XS | S | M | L | XL`
Wave: topological sort on Blocker column (items with no blockers = wave 0)

## Subcommands

### `/backlog` (no args) — Briefing View

Display current backlog state:
1. Read `backlog/REMINDERS.md` — show items where `Due <= today` or `Due = session-start`
2. Read `backlog/HANDOFF.md` — show "What's next" and "Blocked / Waiting"
3. Read `backlog/BACKLOG.md` — show Active (P0-P1) items; count Queued and Deferred

Freshness check: compare HANDOFF.md status claims against current BACKLOG.md statuses.
If stale: `⚠ HANDOFF.md is stale for {N} item(s) — rely on BACKLOG.md for current state.`

Output format:
```
BACKLOG BRIEFING — {date}
Reminders due: {count}
  - {reminder text} [{priority}]

Last session ({date}): {1-line summary from HANDOFF.md}
Next steps:
  - {item from HANDOFF.md "What's next"}

Ready to execute (wave 0, unblocked):
  1. [{id}] {title} — {priority}/{size}

Active items: {count} (P0: {n}, P1: {n})
  - [{id}] {title} — {status} {blocker if any}

Queued: {count} | Deferred: {count} | Inbox: {count}
```

### `/backlog add {title}` — Add New Item

Add a new item to `backlog/inbox.md` with auto-generated ID:
```
| {B-NNN} | {title} | Inbox | — | — | — | — | — | — |
```
Prompt for priority, category, size if not provided.

### `/backlog update {id} {field}={value}` — Update an Item

Update a specific field of an item. Supported fields:
`status`, `priority`, `size`, `wave`, `blocker`, `plan`, `title`

### `/backlog triage` — Process Inbox Items

For each item in `inbox.md`:
- Prompt for priority, category, size, wave, and blockers
- Move to `BACKLOG.md` with Active or Queued status
- Clear processed items from `inbox.md`

### `/backlog archive {id}` — Archive Completed Item

Move item from Active/Queued to Done. Write to `backlog/archive/{YYYY-MM}.md`.

### `/backlog remind {text} --due {date}` — Add a Reminder

Append to `backlog/REMINDERS.md`:
```
| {date} | {text} | P{n} |
```

### `/backlog handoff` — Write Session Handoff

Write `backlog/HANDOFF.md` at session end:
```markdown
# Session Handoff — {date}

## Summary
{1-2 sentence summary of what was accomplished}

## What's next
- [{id}] {title}

## Blocked / Waiting
- [{id}] {title} — blocked on: {reason}

## Newly unblocked
- [{id}] {title} — {reason now unblocked}
```

### `/backlog plan {id}` — Create a Plan File for an Item

Create a plan file at `plans/from_backlog/{id}-{slug}.md` with standard structure:
```markdown
# Plan: {title}

## Context
{why this item exists}

## Approach
{implementation steps}

## Verification
{how to test}

## Acceptance criteria
- [ ] criterion 1
- [ ] criterion 2
```

Update the `Plan` column in BACKLOG.md to reference the new file.

### `/backlog status {id}` — Status Investigation

Gather all context about a specific item:
- Current entry in BACKLOG.md
- Plan file content (if linked)
- Recent git log mentions
- Any open findings in reports/

### `/backlog investigate {id}` — Deep Investigation

Like `/backlog status` but also:
- Read referenced files
- Check for blockers in knowledge or content
- Summarize the investigation as a note appended to the plan file

### `/backlog reconcile` — Fix Inconsistencies

Scan for:
- Items with `Plan` column pointing to missing plan files
- Duplicate IDs
- Items in Done with plans still marked in-progress
- Stale Active items (last activity > 14 days)

Report all inconsistencies; ask operator to resolve.

### `/backlog next` — What to Work on Next

Show the highest-priority, wave-0, unblocked item that hasn't been started.
Consider priority tier first, then size (prefer XS/S for quick wins), then age.

### `/backlog sweep` — Plan File Audit

For every Active/Queued P0/P1 item with a Plan column:
- Verify the plan file exists
- Check if the plan is actionable (has steps and acceptance criteria)
- Report any issues

## Post-conditions

- `backlog/BACKLOG.md` updated (for write subcommands)
- `backlog/HANDOFF.md` updated (for `handoff` subcommand)
- `backlog/REMINDERS.md` updated (for `remind` subcommand)
- Plan files created in `plans/from_backlog/` (for `plan` subcommand)
- No custom directories created outside the `backlog/` and `plans/` convention
