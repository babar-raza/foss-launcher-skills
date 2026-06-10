---
name: session-start
id: S-82
description: >
  Mandatory session initialization gate. Ensures the agent has read all
  governance files, loaded backlog context, and confirmed capability assessment
  before accepting any user request.
args: ""
---

# S-82: Session Start — Mandatory Session Initialization Gate

**Trigger:** Run at the start of every session before any other command or task.

## Purpose

Ensures the agent has read all mandatory governance files and can correctly
state the active read order and capability assessment method before accepting
any user request.

## Steps

1. Read `AGENTS.md` in full
2. Read `CLAUDE.md`
3. Confirm: state the current §2 Read Order aloud
4. Confirm: state the capability assessment method from AGENTS.md §6b
   - Also state the anti-reframing rule: "There is no 'forensic', 'ad-hoc', or
     'operator-directed' exemption from skill-first execution. All work matches
     a registered skill (FULL), requires gap escalation (PARTIAL/NONE), or is
     broken (BROKEN). No other classification exists."
5. Surface backlog briefing (non-blocking — skip gracefully if files absent):
   - Read `backlog/REMINDERS.md` — show items where `Due <= today` or `Due = session-start`
   - Read `backlog/HANDOFF.md` — show "What's next" and "Blocked / Waiting"
   - Read `backlog/BACKLOG.md` — show Active (P0-P1) items (max 5)
   - **Plan-file audit** (P0/P1 items only): For each Active P0/P1 item with a non-empty
     Plan column, verify the referenced file exists on disk. If any are missing, surface
     them as first-priority warnings:
     ```
     MISSING PLAN FILES (P0/P1):
       [{id}] {title} — plan not found: {path}
       Action: reconstruct or reconcile the plan before proceeding
     ```
   - Output a `BACKLOG BRIEFING` block (see format below)
   - If `backlog/` directory does not exist, output: `BACKLOG: not configured`
6. Only then accept the user's task

## Verification

Output this exact block when complete:

```
SESSION GATE PASSED
- AGENTS.md: read
- CLAUDE.md: read
- Read Order: [list the items from §2]
- Capability assessment: FULL / PARTIAL / NONE / BROKEN
- Anti-reframing: no ad-hoc/forensic/operator-directed exemptions exist
```

## Backlog Briefing Format

```
BACKLOG BRIEFING — {date}
Reminders due: {count}
  - {reminder text} [{priority}]

Last session ({date}): {1-line summary from HANDOFF.md}
Next steps:
  - {item from HANDOFF.md "What's next"}

Active items: {count} (P0: {n}, P1: {n})
  - [{id}] {title} — {status} {blocker if any}

Queued: {count} | Deferred: {count} | Inbox: {count}
```

## Resuming Another Operator's Session

If another operator started work and you need to continue their session:

1. Run `/session-start` as normal
2. Read `backlog/HANDOFF.md` to understand what was in progress
3. If a plan file is referenced, read it before accepting any task
4. Announce: "Continuing session from {date}; last work: {1-line summary}"

## Hard rules

- Do NOT accept any task before completing all 6 steps
- Do NOT skip or summarize AGENTS.md — read it fully
- If AGENTS.md is missing or unreadable, stop and report the failure
