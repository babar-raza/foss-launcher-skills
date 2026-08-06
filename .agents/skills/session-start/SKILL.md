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
   Record the returned session ID, **then export it for the rest of the
   session** (HARDEN-A2/A12, 2026-07-22):
   ```bash
   export AGENT_SESSION_ID=<the-returned-id>
   ```
   Every subsequent `session_ledger.py`/`skill_context.py` call in this session
   should run with `AGENT_SESSION_ID` set in its environment — this is what
   routes it onto the per-session-isolated path (no shared global "active
   session"/"active skill context" pointer another concurrent session could
   silently close or supersede — see ST-021). Without it, resolution still
   works for the common single-session case, but two sessions active at once
   become a loud, blocking ambiguity error instead of a silent one — exporting
   the id avoids ever hitting that error path at all.

   **Worktree-per-session (the suggested default for any session expected to
   commit):** this repo is a shared checkout with no git-index isolation
   between concurrent sessions (ST-021) — a session doing multi-stage writes
   (a product launch, a broad refresh, anything spanning several commits)
   should start in an isolated worktree via the `EnterWorktree` tool before
   step 1, rather than working directly in the shared checkout. A quick
   single-file edit doesn't need this; anything that will touch many files
   over multiple steps does. This fixes the underlying shared-working-tree
   git-index race at its root — the `AGENT_SESSION_ID` convention above only
   fixes the ledger/attribution layer around it, not the git-level race
   itself.
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
     Plan file was found on disk, check whether the plan needs S-91 normalization by running
     the real check (not a re-described copy of its logic — the two had already drifted once):
     ```bash
     .venv/Scripts/python scripts/ci/checks/check_plan_quality.py {plan-path} --json
     ```
     Trigger normalization on any finding (`PQ-01` mixed context, `PQ-02` stale-unnormalized,
     `PQ-03` completed-mixed-with-open, `PQ-04` maturity ambiguity, `PQ-05` long-unnormalized) —
     these already cover: H2 sections with sprint/retrospective/postmortem keywords, file mtime
     >7 days with no `## Plan Normalization Record` section, and completed/open-work mixing.
     Session-inherited-from-another-agent (HANDOFF.md present with prior-session context) is not
     covered by the script; check that separately. For any plan matching at least one trigger,
     append to the BACKLOG BRIEFING output block:
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
     Check **health first, then age**. Derive health from the gate's exit code, not by
     eyeballing the JSON (MT021):
     ```bash
     PYTHONPATH=scripts/pipeline .venv/Scripts/python \
       scripts/pipeline/commands/diagnostics/repo_patrol.py gate --json
     ```
     - Exit **2** (`blocked` — failed, missing, or no `scan_health` because the report
       predates ST-058) or exit **1** (`degraded`): suggest re-running `/repo-patrol`
       **regardless of age**, and state that the last scan did not reach all orgs.
       Findings from such a report are incomplete — an empty candidate list does NOT
       mean "nothing new exists".
     - Exit **0** (`ok`) and the report is older than 7 days: suggest running `/repo-patrol`
     - The advisory is informational: report the gate's verdict, never let its non-zero
       exit code fail or block the session.
     - If `reports/discovery/sweep_report.json` exists and has `high_count > 0` or `medium_count > 0`: suggest running `/discovery-triage`
     - If neither file exists: suggest running `/repo-patrol` then `/change-sweep` for initial baseline
     ```
     DISCOVERY ADVISORY:
       Patrol report: {age} days old | Health: {ok|degraded|failed|unknown} ({orgs_ok}/{orgs_requested} orgs)
       Sweep HIGH: {N} | Sweep MEDIUM: {N}
       [suggestion if applicable]
     ```
     Emit `Discovery: clear` (one line) **only** when the gate exits **0** AND the patrol
     report is < 7 days old AND there are no HIGH/MEDIUM sweep findings.
     Never emit `Discovery: clear` on a non-zero gate exit — a failed scan refreshes
     `generated_at` in every pre-ST-058 artifact, so age alone would let the failure
     silence the only monitor that would prompt a re-run.
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
