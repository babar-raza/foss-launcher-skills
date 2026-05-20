# Backlog Directory

This directory holds durable cross-session planning state for the foss-launcher-skills system.
The `/session-start` skill (S-82) reads these files at the start of every agent session.

---

## Files

### `BACKLOG.md` — Active work items

Format (required columns):

```markdown
| ID | Title | Status | Priority | Plan | Owner | Notes |
|----|-------|--------|----------|------|-------|-------|
| BL-001 | Launch words/python | Active | P0 | plans/launch-words-python.md | writer | Blocked: stale model |
```

- **Status**: `Inbox` | `Active` | `Queued` | `Deferred` | `Done`
- **Priority**: `P0` (urgent) → `P3` (nice-to-have)
- **Plan**: path to the governing plan file (or blank)

### `HANDOFF.md` — Cross-session continuity

```markdown
## Last session ({YYYY-MM-DD})
{1-2 sentence summary of what was done}

## What's next
- [ ] {specific next action}
- [ ] {specific next action}

## Blocked / Waiting
- {item}: waiting on {what}
```

### `REMINDERS.md` — Time-sensitive alerts

```markdown
| Due | Priority | Reminder |
|-----|----------|---------|
| session-start | P0 | Check stale_since in all active products |
| 2026-06-01 | P1 | Renew GITHUB_TOKEN before it expires |
```

- **Due**: ISO date (`2026-06-01`) or `session-start` (shown every session)

---

## Quick Start

1. Copy and rename the templates above into `BACKLOG.md`, `HANDOFF.md`, and `REMINDERS.md`.
2. Run `/session-start` in an agent session — it will read all three files automatically.
3. Update `HANDOFF.md` at the end of each session before closing.

## What is NOT stored here

- Source code or skill files — those live in `skills/`
- Knowledge artifacts — those live in `knowledge/`
- Reports — those live in `reports/`
- Anything gitignored (credentials, session ledger files)
