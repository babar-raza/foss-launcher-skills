---
name: session-start
id: S-77
description: >
  Mandatory session initialization gate. Read all governance files, confirm
  read order, initialize session tracking, and surface backlog briefing before
  accepting any task.
args: ""
---

# S-77: Session Start — Mandatory Session Initialization Gate

**Trigger:** Run at the start of every session before any other command or task.

## Purpose

Ensures the agent has read all mandatory governance files and can correctly
state the active read order and skill-first execution mandate before accepting
any user request.

## Steps

> **Optional context gate** — if `scripts/skill_context.py` exists, run before step 1:
> ```bash
> python scripts/skill_context.py begin --skill S-77 --scope "*"
> ```

### Step 1: Read AGENTS.md

Read `AGENTS.md` in full. This is the authoritative governance document.
If `AGENTS.md` is missing or unreadable, **stop and report the failure** — do not
proceed with cached knowledge.

### Step 2: Read agent-specific instructions

Read your active agent instructions file. This is one of:
- `CLAUDE.md` — if running in Claude Code
- `CODEX.md` — if running in Codex CLI
- `.kilocode/rules-code/` — if running in Kilo Code
- Any other agent-specific file if documented in AGENTS.md

If no agent instructions file exists: note the absence and continue.

### Step 3: State read order and capability assessment

Confirm aloud:
- The current read order from AGENTS.md (what must be read before doing work)
- The skill-first execution mandate: all work must match a registered skill, require
  gap escalation if no skill fits, or be classified as broken if no path exists.
  There are no ad-hoc or "just this once" exemptions.

### Step 4: Initialize session tracking (optional)

If `scripts/session_ledger.py` exists:
```bash
python scripts/session_ledger.py init
```
Record the returned session ID.

If the script is absent: proceed without session tracking. Note this in the output.

### Step 5: Surface backlog briefing (optional, non-blocking)

If a `backlog/` directory exists, surface pending items:
- Read `backlog/REMINDERS.md` — show items where `Due <= today` or `Due = session-start`
- Read `backlog/HANDOFF.md` — show "What's next" and "Blocked / Waiting"
- Read `backlog/BACKLOG.md` — show Active (P0-P1) items (max 5)

For each Active P0/P1 item with a Plan column, verify the referenced plan file
exists on disk. If missing, surface as first-priority warning:
```
⚠ MISSING PLAN FILES (P0/P1):
  [{id}] {title} — plan not found: {path}
  Action: reconstruct the plan or update the backlog entry
```

If `backlog/` does not exist: output `BACKLOG: not configured`

Skip this step gracefully if any backlog file is absent.

### Step 6: Only then accept the user's task

### Verification output

```
SESSION GATE PASSED
- AGENTS.md: read ✓
- Agent instructions: read ✓  [or: not found]
- Read Order: [list items from AGENTS.md §2]
- Skill-first mandate: active — no ad-hoc exemptions exist
- Session tracking: initialized (session ID: {id})  [or: not configured]
```

### Backlog briefing format (if configured)

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

### Resuming another operator's session

1. Run `/session-start` as normal (creates a fresh session)
2. If session tracking is configured:
   ```bash
   python scripts/session_ledger.py inherit
   ```
   This finds the most recent closed session and adopts all its tracked files.
3. If you know the specific session ID:
   ```bash
   python scripts/session_ledger.py inherit --session-id <id>
   ```

> **Optional context close** — if `scripts/skill_context.py` exists, run after step 5:
> ```bash
> python scripts/skill_context.py end --skill S-77 --status completed
> ```

## Hard rules

- Do NOT accept any task before completing all 6 steps
- Do NOT skip or summarize AGENTS.md — read it fully
- If AGENTS.md is missing or unreadable: stop and report the failure
