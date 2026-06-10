# S-98: Backlog — Unified Planning & Backlog Management

**Arguments:** `[subcommand] [args...]`

**Trigger:** Run `/backlog` to view current state, or with a subcommand to modify.

## Purpose

Maintains a durable backlog system across sessions. Surfaces reminders, tracks
in-progress work, manages handoffs between sessions, and provides planning
primitives for multi-session programs.

**SAFE-FAILURE**: If `backlog/` or `plans/` directories do not exist, STOP and ask the operator.
Never create custom folder structures like `.kilo-backlog/` or `kilo-plans/`.

## Directory Layout

```
backlog/
  BACKLOG.md     — authoritative item list (status, priority, plan reference)
  REMINDERS.md   — time/event-triggered reminders
  HANDOFF.md     — session-to-session context transfer
  inbox.md       — unprocessed items pending triage
plans/
  from_backlog/  — plan files created by /backlog plan
```

## Subcommands

| Subcommand | Action |
|---|---|
| `briefing` | Show today's reminders, last session summary, active items (also: default when no subcommand) |
| `add {title} --priority {P0-P3}` | Add new item to inbox or directly to backlog |
| `update {id} --status {status}` | Update item status, priority, or note |
| `triage` | Interactively process inbox items into backlog |
| `remind {date|event} {text}` | Add a reminder |
| `handoff` | Write HANDOFF.md capturing current session context |
| `archive {id}` | Archive a closed item |
| `plan {id}` | Create a plan file for a backlog item; write to `plans/from_backlog/` |
| `replan {id}` | Amend an existing plan file for a backlog item |
| `harden {id}` | Verify plan file integrity against current repo state |
| `status {id}` | Detailed status investigation for an item |
| `investigate {id}` | Research item and add findings to the item record |
| `investigate-run {id}` | Execute the investigation plan for an item |
| `surface {context}` | Surface relevant backlog items given current context |
| `next` | Recommend the single highest-priority executable item |
| `reconcile` | Sync backlog item statuses with current git/plan state |
| `trace {id}` | Show full traceability: plan → commits → verification |
| `close {id}` | Governed closeout: verify done criteria, update status, archive |
| `merge {id1} {id2}` | Merge two related items |
| `group {ids...} --name {name}` | Group items under a parent |
| `link {id1} --blocks {id2}` | Declare a blocking relationship |
| `sweep` | Scan all plans for stale items and surface for review |

## Status Values

| Status | Meaning |
|---|---|
| `Inbox` | Unprocessed — needs triage |
| `Active` | In progress this session |
| `Queued` | Ready to start; not yet active |
| `Blocked` | Waiting on dependency or external action |
| `Deferred` | Intentionally postponed |
| `Done` | Completed; pending archive |
| `Archived` | Closed and moved to archive |

## Priority Values

| Priority | Meaning |
|---|---|
| P0 | Critical — blocking launch or critical bug |
| P1 | High — important this sprint |
| P2 | Normal — backlog |
| P3 | Low — nice to have |

## Steps

For each subcommand, the skill:

1. **Reads** the relevant backlog files
2. **Applies** the requested operation
3. **Writes** updated files to `backlog/`
4. **Confirms** the operation with a summary

For the default (no subcommand) or `briefing`:
1. Read `backlog/REMINDERS.md` — show items where `Due <= today` or `Due = session-start`
2. Read `backlog/HANDOFF.md` — show last session summary and "What's next"
3. Read `backlog/BACKLOG.md` — show Active (P0-P1) items (max 5)
4. Read `backlog/inbox.md` — show count of unprocessed items

## Post-conditions

- Backlog state updated per subcommand
- `backlog/HANDOFF.md` updated on `handoff`
- Plan files created/amended in `plans/from_backlog/` on `plan`/`replan`
