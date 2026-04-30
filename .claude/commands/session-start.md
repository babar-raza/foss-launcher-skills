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

> **Session gate bootstrap** — run as the very first action, before anything else:
> ```bash
> bash scripts/ci/hooks/bootstrap_session_gate.sh
> ```
> Creates `.claude/.agents_read` so all subsequent tool calls are unblocked. Idempotent.

> **Skill context gate** — run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-77 --scope "*"
> ```


1. Read `AGENTS.md` in full
2. Read `CLAUDE.md`
3. Confirm: state the current §2 Read Order aloud
4. Confirm: state the capability assessment method from AGENTS.md §6b (full detail: docs/workflows/gap-escalation.md)
   - Also state the anti-reframing rule: "There is no 'forensic', 'ad-hoc', or
     'operator-directed' exemption from skill-first execution. All work matches
     a registered skill (FULL), requires gap escalation (PARTIAL/NONE), or is
     broken (BROKEN). No other classification exists."
5. Initialize the session ledger (captures dirty-file snapshot for `/commit` scoping):
   ```bash
   .venv/Scripts/python scripts/pipeline/commands/ops/session_ledger.py init
   ```
   Record the returned session ID.
5a. Knowledge status advisory (non-blocking -- never delays session):
    Read `data/products.json` to enumerate all FOSS products. For each product entry
    with a `clone_url` field, check whether merged knowledge is available:
    - `knowledge/{family}/{platform}/merged/model.yaml` exists AND `stale_since` is null
      → COMPLETE
    - model.yaml exists AND `stale_since` is not null
      → STALE (will block generation and evaluation)
    - `knowledge/{family}/{platform}/` directory exists but no merged/model.yaml
      → PARTIAL (scout ran but merge never completed)
    - Directory is absent entirely
      → MISSING (no knowledge bootstrap done)

    Output a `KNOWLEDGE STATUS` block summarizing the count of each status class and
    listing any products that are STALE, PARTIAL, or MISSING by name. Omit COMPLETE
    products from the list if there are 5 or more COMPLETE entries (just show the count).

    Non-blocking: proceed to step 6 regardless of knowledge status. The block is an
    advisory only -- it does NOT gate session start. STALE and MISSING products are
    blocked from generation and content evaluation by the pipeline gates (batch_reference,
    site_planner, evaluators), not by this check.

6. Surface backlog briefing (non-blocking — skip gracefully if files absent):
   - Read `backlog/REMINDERS.md` — show items where `Due <= today` or `Due = session-start`
   - Read `backlog/HANDOFF.md` — show "What's next" and "Blocked / Waiting"
   - Read `backlog/BACKLOG.md` — show Active (P0-P1) items (max 5)
   - **Plan-file audit** (P0/P1 items only): For each Active P0/P1 item with a non-empty
     Plan column, verify the referenced file exists on disk. If any are missing, surface
     them as first-priority warnings before the rest of the briefing:
     ```
     ⚠ MISSING PLAN FILES (P0/P1):
       [{id}] {title} — plan not found: {path}
       Action: run `/backlog plan --reconstruct {id}` or `/backlog reconcile`
     ```
   - **Plan normalization audit** (non-blocking advisory, S-91): For each P0/P1 item whose
     Plan file was found on disk, check whether the plan needs S-91 normalization by scanning
     for: (a) H2 sections with sprint/retrospective/postmortem keywords, (b) file mtime >7 days
     ago with no `## Plan Normalization Record` section, (c) session inherited from another
     agent (HANDOFF.md present with prior-session context). For any plan matching at least one
     trigger, append to the BACKLOG BRIEFING output block:
     ```
     PLANS NEEDING NORMALIZATION:
       [{id}] {title} - plan: {path} - trigger: {reason}
       Action: run `/plan-normalize {path}` before executing this plan
     ```
     If no plans need normalization, omit this section silently. Non-blocking: session proceeds
     regardless of whether any plans need normalization.
   - Report harvest advisory (read-only, never blocks session):
     Run `report_extract.py reports/ --count-only` and cross-reference `harvest_ledger.py status`.
     ```
     HARVEST ADVISORY:
       Unharvested qualifying reports: {N}
       Items pending review: {N}
       Items in failure queue: {N}
     ```
     If UNHARVESTED > 0: list report paths with item counts.
     If FAILED > 0: warn and suggest `/backlog harvest --retry-failed`.
     If all counts are 0: emit `Harvest: clear` (one line).
     Graceful skip if extractor or ledger not available (scripts missing or reports/ empty).
   - Discovery advisory (read-only, never blocks session — skip gracefully if reports/ absent):
     Check age and content of discovery reports:
     - If `reports/discovery/patrol_report.json` exists and is older than 7 days: suggest running `/repo-patrol`
     - If `reports/discovery/sweep_report.json` exists and has `high_count > 0` or `medium_count > 0`: suggest running `/discovery-triage`
     - If neither file exists: suggest running `/repo-patrol` then `/change-sweep` for initial baseline
     ```
     DISCOVERY ADVISORY:
       Patrol report: {age} days old | Sweep HIGH: {N} | Sweep MEDIUM: {N}
       [suggestion if applicable]
     ```
     If both reports are current (patrol < 7 days) and no HIGH/MEDIUM findings: emit `Discovery: clear` (one line).
     Advisory is informational only — do NOT invoke S-93, S-94, or S-95 automatically.
   - Output a `BACKLOG BRIEFING` block (see format below)
   - If `backlog/` directory does not exist, output: `BACKLOG: not configured (run /backlog to set up)`
7. Only then accept the user's task

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-77 --status completed
> ```

## Verification

Output this exact block when complete:

```
SESSION GATE PASSED
- AGENTS.md: read ✓
- CLAUDE.md: read ✓
- Read Order: [list the items from §2]
- Capability assessment: FULL / PARTIAL / NONE / BROKEN
- Anti-reframing: no ad-hoc/forensic/operator-directed exemptions exist
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
   .venv/Scripts/python scripts/pipeline/commands/ops/session_ledger.py inherit
   ```
   This finds the most recent closed session and adopts all its tracked files
   into your new session.
3. If you know the specific session ID:
   ```bash
   .venv/Scripts/python scripts/pipeline/commands/ops/session_ledger.py inherit --session-id <id>
   ```
4. To selectively adopt files (e.g., only content changes):
   ```bash
   .venv/Scripts/python scripts/pipeline/commands/ops/session_ledger.py adopt --glob "content/**"
   ```
5. To adopt all dirty files at once:
   ```bash
   .venv/Scripts/python scripts/pipeline/commands/ops/session_ledger.py adopt --all
   ```

## Hard rules

- Do NOT accept any task before completing all 7 steps
- Do NOT skip or summarise AGENTS.md — read it fully
- If AGENTS.md is missing or unreadable, stop and report the failure
