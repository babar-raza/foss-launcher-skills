<!-- CONTRACT: agent-executed
     purpose: initialize session and governance context before any work
     preconditions: AGENTS.md readable; .venv usable
     postcondition: session ledger initialized with dirty-file snapshot; governance files loaded
     idempotent: yes — re-init creates a new session safely
     verified: 2026-04-11
-->
# S-77: Session Start — Mandatory Session Initialization Gate

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
5. Initialize the session ledger (captures dirty-file snapshot for `/commit` scoping):
   ```bash
   .venv/Scripts/python scripts/pipeline/session_ledger.py init
   ```
   Record the returned session ID.
6. Surface backlog briefing (non-blocking — skip gracefully if files absent):
   - Read `backlog/REMINDERS.md` — show items where `Due <= today` or `Due = session-start`
   - Read `backlog/HANDOFF.md` — show "What's next" and "Blocked / Waiting"
   - Read `backlog/BACKLOG.md` — show Active (P0-P1) items (max 5)
   - Output a `BACKLOG BRIEFING` block (see format below)
   - If `backlog/` directory does not exist, output: `BACKLOG: not configured (run /backlog to set up)`
7. Only then accept the user's task

## Verification

Output this exact block when complete:

```
SESSION GATE PASSED
- AGENTS.md: read ✓
- CLAUDE.md: read ✓
- Read Order: [list the items from §2]
- Capability assessment: FULL / PARTIAL / NONE / BROKEN
- Session ledger: initialized (session ID: {id}, dirty files at start: {N})
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

1. Run `/session-start` as normal (creates a fresh session)
2. Inherit the prior session's file tracking:
   ```bash
   .venv/Scripts/python scripts/pipeline/session_ledger.py inherit
   ```
   This finds the most recent closed session and adopts all its tracked files
   into your new session.
3. If you know the specific session ID:
   ```bash
   .venv/Scripts/python scripts/pipeline/session_ledger.py inherit --session-id <id>
   ```
4. To selectively adopt files (e.g., only content changes):
   ```bash
   .venv/Scripts/python scripts/pipeline/session_ledger.py adopt --glob "content/**"
   ```
5. To adopt all dirty files at once:
   ```bash
   .venv/Scripts/python scripts/pipeline/session_ledger.py adopt --all
   ```

## Hard rules

- Do NOT accept any task before completing all 7 steps
- Do NOT skip or summarise AGENTS.md — read it fully
- If AGENTS.md is missing or unreadable, stop and report the failure
