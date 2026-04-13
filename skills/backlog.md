<!-- CONTRACT: agent-executed
     purpose: unified backlog management — view, update, add, triage, archive, remind, handoff, reconcile
     preconditions: backlog/ directory exists with BACKLOG.md, REMINDERS.md, HANDOFF.md, inbox.md
     postcondition: backlog state updated per subcommand; briefing displayed
     idempotent: yes — read-only subcommands are safe to repeat; write subcommands are append-only
     verified: 2026-04-13
-->
# S-88: Backlog — Unified Planning & Backlog Management

**Arguments:** `[subcommand] [args...]`

**Trigger:** Run `/backlog` to view current state, or with a subcommand to modify.

## Purpose

Maintains a durable backlog system across sessions. Surfaces reminders, tracks
plan-level and item-level work, supports investigation items without plans,
and provides session handoff for context switches.

All backlog state lives in `backlog/` (gitignored, internal-only).

## Subcommands

### `/backlog` (no args) — Briefing View

Display the current backlog state. This is the default when no subcommand is given.

**Steps:**
1. Read `backlog/REMINDERS.md` — show items where `Due <= today` or `Due = session-start`
2. Read `backlog/HANDOFF.md` — show "What's next" and "Blocked / Waiting" from last session
3. Read `backlog/BACKLOG.md` — show Active (P0-P1) items, then count of Queued and Deferred
4. Output the briefing in this format:

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

Stale items (>14 days no activity): {count}
  - [{id}] {title} — last activity: {date} ({N} days ago)
```

**Staleness computation**: An item is stale if all of these are true for >14 days:
- No modification to referenced plan file (check mtime)
- No commits mentioning the item ID (`git log --grep="{id}"`)
- No status change in `backlog/CHANGELOG.md`

### `/backlog update` — Automated Plan Scanning

Discover plan files, extract open items, reconcile with BACKLOG.md.

**Steps:**
1. Scan these locations for `.md` files:
   - `plans/healing/`
   - `plans/from_chat/`
   - `plans/` (top-level files only)
   - `.claude/plans/` (with repo-affinity filtering — see below)
2. For each file found, extract items with status markers:
   - `[ ]`, `TODO`, `pending`, `Not Started`, `- **Status**: Not Started` → pending
   - `[x]`, `done`, `complete`, `DONE`, `CLOSED`, `- **Status**: Done`, `Status: Done` (case-insensitive) → done
   - `[-]`, `in progress`, `WIP`, `IN PROGRESS`, `- **Status**: In Progress` → in-progress
   - `[!]`, `blocked`, `BLOCKED`, `- **Status**: Blocked` → blocked
   - `[~]`, `skipped`, `deferred`, `DEFERRED`, `- **Status**: Deferred` → deferred
3. Compare extracted items against `backlog/BACKLOG.md`:
   - New items not in BACKLOG.md → report as NEW
   - Items whose status changed → report as CHANGED
   - Items in BACKLOG.md not found in any plan → report as ORPHANED
4. Update `backlog/BACKLOG.md` with changes (append new items, update statuses)
5. Update staleness: compute days since last file modification for each plan
6. Output summary: `{N} new, {N} changed, {N} orphaned, {N} plans scanned`

**`.claude/plans/` repo-affinity filtering:**

The `.claude/plans/` directory is a shared global pool across all projects on this
machine. To avoid pulling in unrelated plans, fingerprint each file for aspose.org
affinity. A file is considered related if its content contains **2+ of these signals**:

- Repo-specific paths: `AGENTS.md`, `knowledge/`, `content/docs.aspose.org`,
  `content/products.aspose.org`, `plans/healing/`, `plans/from_chat/`, `scripts/pipeline/`
- Repo-specific terms: `aspose`, `FOSS`, `gap-eval`, `batch-reference`,
  `evidence-repair`, `site-plan`, `hugo`
- Skill IDs: `S-` followed by digits (e.g., S-77, S-88)

Files matching 0-1 signals are skipped. Report skipped file count for spot-checking.

### `/backlog add {title}` — Add Standalone Task

Append a task to `backlog/inbox.md` under "Standalone Tasks".

**Steps:**
1. Read `backlog/inbox.md`
2. Determine next `ST-NNN` ID by counting existing Standalone Tasks entries
3. Append row: `| ST-{NNN} | {title} | P2 | {today} | |`
4. Confirm: `Added ST-{NNN}: {title}`

### `/backlog investigate {title}` — Add Investigation Item

Append an investigation item to `backlog/inbox.md` under "Investigation Needed".

**Steps:**
1. Read `backlog/inbox.md`
2. Determine next `INV-NNN` ID by counting existing Investigation entries
3. Append row: `| INV-{NNN} | {title} | {today} | |`
4. Confirm: `Added INV-{NNN}: {title}`

### `/backlog remind {text} --due {date}` — Add Reminder

Append a reminder to `backlog/REMINDERS.md`.

**Steps:**
1. Read `backlog/REMINDERS.md`
2. Determine next `R-NN` ID
3. Parse `--due` value (accept: `session-start`, `weekly`, `YYYY-MM-DD`, `before:{task-id}`)
4. Append row: `| R-{NN} | {text} | {due} | P2 | manual |`
5. Confirm: `Added R-{NN}: {text} (due: {due})`

### `/backlog handoff` — Write Session Handoff

Overwrite `backlog/HANDOFF.md` with current session summary.

**Steps:**
1. Ask the operator (or infer from session context):
   - What was done this session?
   - What should happen next?
   - What is blocked or waiting?
   - Any context the next session needs?
2. Write `backlog/HANDOFF.md` with the standard template:
   ```
   # Session Handoff
   > Last session: {session-id} on {date}
   ## What was done
   ## What's next
   ## Blocked / Waiting
   ## Context for next session
   ```
3. Confirm: `Handoff written for session {id}`

### `/backlog archive {plan-path-or-pattern}` — Archive Completed Plans

Move completed plan files to `plans/archive/` and update tracking.

**Steps:**
1. Resolve `{plan-path-or-pattern}` — supports:
   - Exact path: `plans/healing/2026-03-25-dotnet-self-review.md`
   - Glob pattern: `plans/healing/2026-03-*`
   - Keyword: `from_chat` (expands to `plans/from_chat/`)
2. For each matched file:
   - Verify all tasks in the file are `done`, `closed`, or `deferred` (warn if any are open)
   - Move file to `plans/archive/{original-relative-path}`
   - Log: `Archived: {path} -> plans/archive/{path}`
3. Update `backlog/BACKLOG.md`: mark any items referencing archived plans as `done`
4. Output summary: `{N} files archived, {N} backlog items closed, {N} warnings`

### `/backlog triage` — Triage Inbox Items

Review `backlog/inbox.md` and disposition each item.

**Steps:**
1. Read `backlog/inbox.md`
2. For each item in Investigation Needed and Standalone Tasks:
   - Display the item
   - Ask: promote to BACKLOG.md? attach to plan? defer? drop?
3. Apply the disposition:
   - **Promote**: move to appropriate section in `backlog/BACKLOG.md`, assign priority
   - **Attach**: add plan reference, move to BACKLOG.md
   - **Defer**: move to Deferred section in BACKLOG.md with reason
   - **Drop**: remove from inbox.md (no further tracking)
4. Output summary: `{N} promoted, {N} attached, {N} deferred, {N} dropped`

### `/backlog reconcile` — Evidence-Based Reconciliation

Compare active backlog items against current system evidence and classify each item.

**Steps:**
1. Read `backlog/BACKLOG.md` — collect all Active and Queued items
2. For each item, run these evidence checks:

   **a. Plan check** — Read the referenced plan file, extract taskcard status:
   - Taskcard marked Done/Closed → candidate for closure
   - Taskcard marked In Progress → verify against other evidence
   - Plan file missing/archived → flag as ORPHANED

   **b. Commit check** — `git log --grep="{item-ID}" --oneline`:
   - Commits found → extract hashes as evidence
   - Also check `git log --grep="Addresses:.*{item-ID}"` for linked commits

   **c. Content check** (content-related items only):
   - Read frontmatter `grade:` field from referenced pages
   - Compare against the condition described in the item

   **d. Test check** (test-related items only):
   - Check if referenced test files/functions exist
   - `grep -r "def test_{name}" scripts/pipeline/tests/`

   **e. Validation check** (pipeline/tool items only):
   - Check if referenced script exists and was modified since item creation

3. Classify each item:
   - **RESOLVED** — all evidence shows the issue no longer exists
   - **PARTIAL** — some evidence of progress, acceptance checks not fully met
   - **STILL-OPEN** — no evidence of resolution found
   - **STALE** — no activity (commits, plan edits) in >14 days
   - **SUPERSEDED** — a later item or commit addresses the same root cause
   - **ORPHANED** — referenced plan no longer exists

4. Output the reconciliation report:
   ```
   BACKLOG RECONCILIATION — {date}
   Items checked: {N}
     RESOLVED: {N}    PARTIAL: {N}    STILL-OPEN: {N}
     STALE: {N}       SUPERSEDED: {N} ORPHANED: {N}

   Details:
     [{id}] {title} — {classification}
       Evidence: {commit hash | test file | grade state | plan status}
       Recommendation: {close | update-status | investigate | merge-with-{other-id}}
   ```

5. Apply operator-confirmed actions:
   - RESOLVED → move to Recently Completed with evidence in Evidence column
   - PARTIAL → update status to `in-progress`, attach evidence note
   - STALE → flag in next briefing, ask operator to re-prioritize or defer
   - SUPERSEDED → mark `dropped` with `superseded-by:{item-ID}` in Evidence column
   - ORPHANED → move to inbox for re-triage

6. Append all status changes to `backlog/CHANGELOG.md`

## Files

| File | Purpose |
|------|---------|
| `backlog/BACKLOG.md` | Canonical backlog index — single source of truth for all items |
| `backlog/REMINDERS.md` | Reminder queue — surfaced at session boundaries |
| `backlog/HANDOFF.md` | Session handoff — what happened, what's next |
| `backlog/inbox.md` | Unattached items — investigation, standalone tasks, ideas |
| `backlog/CHANGELOG.md` | Append-only audit trail of status changes |
| `plans/archive/` | Completed plan archive |

## Status Transition Rules

| From | To | Required |
|------|----|----------|
| any | `done` | Evidence in Evidence column (commit hash, test reference, grade state, or operator attestation) |
| any | `dropped` | Reason in Evidence column (`superseded-by:{id}`, `invalid:{reason}`, or attestation) |
| any | `deferred` | Reason in Deferred table's Reason column |
| `done` | any other | Explicit reopen with reason (regression, false closure) |
| any | `in-progress` / `queued` / `next` / `blocked` / `waiting` | No precondition |

All status changes must be logged to `backlog/CHANGELOG.md` with: date, item ID, old status, new status, evidence reference, and actor (agent/human).

## Hard rules

- All backlog files are gitignored and internal-only — never commit them
- Do NOT modify plan files in `plans/healing/` or `plans/from_chat/` without explicit operator request
- Do NOT auto-archive plans without operator confirmation
- Do NOT scan `.claude/plans/` files that fail repo-affinity filtering
- When adding items, always use the next available sequential ID
- When updating BACKLOG.md, preserve the table structure exactly
- Reminders are honest — they surface at session boundaries only, no background scheduling
- **Evidence-first closure**: Do not transition any item to `done` without an Evidence column entry (commit hash, test reference, grade state, or explicit operator attestation)
- **Evidence-first dropping**: Do not transition any item to `dropped` without a reason in Evidence (`superseded-by:{id}`, `invalid:{reason}`, or attestation)
- **Changelog is append-only**: `backlog/CHANGELOG.md` records every status change — never delete entries
- **No stale assumptions**: Before generating new taskcards from backlog items, run `/backlog reconcile` on those items first — stale items must be revalidated
- **Escalate drift**: If `/backlog reconcile` finds >5 items misclassified (open but resolved, or done but failing), escalate to operator before proceeding
