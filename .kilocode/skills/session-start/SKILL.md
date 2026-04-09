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
6. Only then accept the user's task

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

## Hard rules

- Do NOT accept any task before completing all 5 steps
- Do NOT skip or summarise AGENTS.md — read it fully
- If AGENTS.md is missing or unreadable, stop and report the failure
