<!-- CONTRACT: agent-executed
     purpose: unified backlog management and planning — view, update, add, triage, archive, remind, handoff, reconcile, status investigation, investigation execution, contextual surfacing, plan creation, replan amendment, plan hardening, traceability, governed closeout, intake dedup, cross-item analysis, merge, group, link, wave-based execution sequencing, plan sweep
     preconditions: backlog/ directory exists with BACKLOG.md, REMINDERS.md, HANDOFF.md, inbox.md
     postcondition: backlog state updated per subcommand; briefing displayed; plan files created/amended in plans/from_backlog/; contextual surfacing available via /backlog surface
     idempotent: yes — read-only subcommands (briefing, status, trace, harden, investigate-run, surface, next) safe to repeat; write subcommands are append-only or guarded
     subcommands: 22 (briefing, update, add, investigate, investigate-run, surface, remind, handoff, archive, triage, reconcile, status, plan, replan, harden, trace, close, merge, group, link, next, sweep)
     verified: 2026-04-15

     SAFE-FAILURE: If backlog/ or plans/ directories do not exist, STOP and ask the operator.
     Never create custom folders like .kilo-backlog/, .kilo-plans/, kilo-backlog/, or kilo-plans/.
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
2. Read `backlog/HANDOFF.md` — show "What's next" and "Blocked / Waiting" from last session.
   **Freshness check**: Cross-reference HANDOFF.md "Critical path" and "Newly unblocked" items against current BACKLOG.md statuses. If any item listed as "newly unblocked", "critical path", or "next up" in HANDOFF.md has a different current status (e.g., listed as unblocked but now done, or listed as queued but now blocked), emit:
   ```
   ⚠️  HANDOFF.md is stale for {N} item(s):
     - [{id}] listed as "{handoff-status}" but current status is "{backlog-status}"
   Rely on BACKLOG.md, not HANDOFF.md, for current execution state.
   ```
   HANDOFF.md is written at session end and may lag by one or more sessions. It is orientation context, not authoritative state.
3. Read `backlog/BACKLOG.md` — show Active (P0-P1) items, then count of Queued and Deferred
4. Output the briefing in this format:

```
BACKLOG BRIEFING — {date}
Reminders due: {count}
  - {reminder text} [{priority}]

Last session ({date}): {1-line summary from HANDOFF.md}
Next steps:
  - {item from HANDOFF.md "What's next"}

Ready to execute (wave 0, unblocked):
  1. [{id}] {title} — {cat}/{priority}/{size} [{effect}] {score if set}
  2. ...
  (ranked by: priority tier, then impact score, then size ascending)

Active items: {count} (P0: {n}, P1: {n})
  - [{id}] {title} — {status} {blocker if any}

Queued: {count} | Deferred: {count} | Inbox: {count}

Effect rollup (active + queued):
  TF: {n} items | GI: {n} | HA: {n} | KF: {n} | OM: {n}

Deferred items due for review: {count}
  - [{id}] {title} — deferred since {date}, review due {review_date}

Stale items: {count}
  - [{id}] {title} — last activity: {date} ({N} days ago)
```

**Wave computation**: The Wave column in BACKLOG.md is computed via topological sort on
the Blocker column DAG. Items with no blockers are wave 0. Items blocked only by wave-0
items are wave 1, and so on. Within a wave, items are ranked by priority tier, then
impact score, then size ascending (XS first). The briefing displays wave-0 items as the
"ready to execute" queue.

**Staleness thresholds** (per-status, all requiring no plan mtime change, no commits, no CHANGELOG entry):
- `in-progress`: stale after 7 days (claims active work)
- `queued` / `next`: stale after 21 days
- `blocked` / `waiting`: stale after 30 days (external dependency)

**Deferred review check**: Read the Deferred table. For each item where Review Date is
a specific date (`YYYY-MM-DD`) and that date <= today, or `quarterly` and >=90 days have
passed since deferral, surface it in the "Deferred items due for review" section.

### `/backlog update` — Automated Plan Scanning

Discover plan files, extract open items, reconcile with BACKLOG.md.

**Steps:**
1. Scan these locations for `.md` files:
   - `plans/healing/`
   - `plans/from_chat/`
   - `plans/from_backlog/`
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
5. **Recompute waves**: Build Blocker DAG, compute topological layers, update Wave column for all Active and Queued items
6. **Lightweight duplicate detection**: For each newly extracted item, compute title keyword overlap (Jaccard) against existing BACKLOG.md items. If score >=4 (using Relationship Taxonomy weights), emit warning: `POSSIBLE DUPLICATE: [{new}] overlaps with [{existing}]`
7. Update staleness: compute days since last file modification for each plan (use per-status thresholds: 7d for in-progress, 21d for queued/next, 30d for blocked/waiting)
8. Output summary: `{N} new, {N} changed, {N} orphaned, {N} plans scanned, {N} duplicate warnings`

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
1. **Relatedness Check** (before adding):
   - Extract keywords from `{title}`
   - Scan `backlog/BACKLOG.md` (Active, Queued, Deferred, Recently Completed within 30 days) for:
     - Title keyword overlap (Jaccard on words, threshold ≥0.5)
     - Same subsystem references (file paths, script names, skill IDs mentioned in title)
   - Score each candidate using signal weights (see Relationship Taxonomy)
   - If score ≥5: `DUPLICATE DETECTED: matches [{id}] {title}` — present options: cancel / override with `duplicate-of:{id}` / merge into existing
   - If score 3–4: `POSSIBLE OVERLAP with [{id}]` — present options: merge / add with `related-to:{id}` / add as separate
   - If score 2: `RELATED ITEM: [{id}]` — suggest adding `related-to:{id}`
   - If score 0–1: proceed normally
2. Read `backlog/inbox.md`
3. Determine next `ST-NNN` ID by counting existing Standalone Tasks entries
4. **Effect suggestion**: suggest effect tag from title keywords using these heuristics:
   - Title contains `claim`, `overclaim`, `truth`, `accuracy`, `false`, `code example`, `syntax` → suggest `TF`
   - Title contains `gate`, `guard`, `threshold`, `validator`, `enforce`, `grade` → suggest `GI`
   - Title contains `heal`, `automat`, `batch`, `controller`, `remediate` → suggest `HA`
   - Title contains `knowledge`, `extract`, `scout`, `format`, `enrich`, `claim` → suggest `KF`
   - Title contains `test`, `seam`, `observ`, `backlog`, `monitor`, `CI`, `log` → suggest `OM`
   - If no match: ask operator
5. Append row: `| ST-{NNN} | {cat} | {effect} | {title} | queued | P2 | {size} | 0 | — | none | {today} |`
6. Confirm: `Added ST-{NNN}: {title} [effect:{effect}]`

### `/backlog investigate {title}` — Add Investigation Item

Append an investigation item to `backlog/inbox.md` under "Investigation Needed".

**Dispatch (before Steps):**
- Extract a leading INV-ID from `{title}` using the pattern `INV-\d+` at the start of the
  string (e.g. `INV-006` from `INV-006 — Read frontmatter grade...`).
  - If an INV-ID is extracted, check `backlog/inbox.md` for that ID:
    - Found in "Investigation Needed" → execute `/backlog investigate-run {extracted-id}` (do not add a new item)
    - Found in "Resolved Investigations" → output `{id} already resolved — see Resolved section` and STOP
    - Not found in either section → treat the full `{title}` as a new intake and proceed normally
- If no leading INV-ID is present → proceed with intake steps as normal

**Steps:**
1. **Relatedness Check** (before adding):
   - Extract keywords from `{title}`
   - Scan `backlog/BACKLOG.md` (Active, Queued, Deferred, Recently Completed within 30 days) for:
     - Title keyword overlap (Jaccard on words, threshold ≥0.5)
     - Same subsystem references (file paths, script names, skill IDs mentioned in title)
   - Score each candidate using signal weights (see Relationship Taxonomy)
   - If score ≥5: `DUPLICATE DETECTED: matches [{id}] {title}` — present options: cancel / override with `duplicate-of:{id}` / merge into existing
   - If score 3–4: `POSSIBLE OVERLAP with [{id}]` — present options: merge / add with `related-to:{id}` / add as separate
   - If score 2: `RELATED ITEM: [{id}]` — suggest adding `related-to:{id}`
   - If score 0–1: proceed normally
2. Read `backlog/inbox.md`
3. Determine next `INV-NNN` ID by counting existing Investigation entries
4. Append row: `| INV-{NNN} | {title} | {today} | |`
5. Confirm: `Added INV-{NNN}: {title}`

### `/backlog investigate-run {id}` — Execute an Existing Investigation

Perform the investigation described in an existing INV item from `backlog/inbox.md`.
Read the item's Notes as the investigation brief, execute it, and record findings inline.

> **Idempotent:** Safe to re-run. If already resolved, displays existing findings and stops.

**Steps:**
1. Read `backlog/inbox.md`; locate `{id}`:
   - Found in "Resolved Investigations" → output existing findings summary and STOP:
     `{id} already resolved on {date}: {findings summary from Resolved table}. No action taken.`
   - Found in "Investigation Needed" → proceed to Step 2
   - Not found in either section → `UNRESOLVED: {id} not found in inbox (checked Investigation Needed + Resolved)`
2. Extract the Notes text — this is the investigation brief
3. Parse the brief for what to check:
   - Files/paths to read (look for `content/`, `scripts/`, `plans/`)
   - Frontmatter fields to check (e.g., `grade:`, `graded_logic_version:`)
   - Conditions to evaluate (e.g., "whether X blocks Y")
   - Scripts to inspect (e.g., guard logic, CLI args)
   - Git history to check (e.g., "what commit introduced X")
4. Execute the investigation using available read-only tools:
   - Read referenced files; extract requested fields
   - Check referenced scripts for described logic
   - Check git log if commit-level evidence is needed
5. Produce structured findings output:
   ```
   INVESTIGATION — {id}: {title}
   Executed: {date}

   Findings:
     - {file or check}: {result}
     ...

   Conclusion:
   {2-3 sentences: what was found, what it means for the question in the brief}

   Recommendation: close-as-resolved | promote-to-backlog | defer | needs-more-info
   ```
6. Update `backlog/inbox.md` — append to the Notes column of the item:
   `resolved:{date} — {1-line summary of conclusion}`
7. If recommendation is `close-as-resolved`:
   - Remove the item from "Investigation Needed"
   - Append it to "## Resolved Investigations" section with the full findings summary

### `/backlog surface {context}` — Contextual Item Surfacing

Scan backlog for items relevant to the given context string and return top matches.
Read-only. Silent (no output) if no items score ≥3.

> **Idempotent:** Safe to call multiple times — read-only, no state changes.

**Steps:**
0. If `backlog/BACKLOG.md` does not exist → output nothing and STOP (silent skip; backlog not yet configured).
1. Extract signal tokens from `{context}`:
   - File paths and script names (e.g. `run.py`, `session_ledger.py`, `content/slides/`)
   - Product families and platforms (e.g. `slides`, `cells`, `3d`, `net`, `python`)
   - Skill IDs (e.g. `S-61`, `S-88`)
   - Subsystem terms (e.g. `no-downgrade`, `gap-eval`, `knowledge`, `tier1`, `grading`, `pipeline`)
2. Scan these item pools:
   - `backlog/BACKLOG.md` — Active (P0–P1) and Queued (P2–P3) rows
   - `backlog/inbox.md` — "Investigation Needed" rows
   - `backlog/BACKLOG.md` — Deferred rows (only if final score ≥5)
   - Skip: Recently Completed, Resolved Investigations (terminal — no action needed)
3. For each item, compute relevance score:

   | Signal | Weight |
   |--------|--------|
   | Matching file path or script name in Title/Evidence/Plan | 3 |
   | Matching product family or platform | 2 |
   | Matching subsystem term | 2 |
   | Matching skill ID | 1 |
   | Title keyword overlap ≥0.3 (Jaccard on words) | 1 |
   | Status is `next` or `in-progress` | +1 boost |

4. Filter: keep items with score ≥3. Sort by (priority asc, score desc). Cap at 5 items.
5. Dedup: if any item ID appears in `{context}` (it was the current subject), remove it.
6. If 0 items remain after filtering → output nothing (truly silent).
7. If ≥1 item: output the surfacing block:
   ```
   Related backlog items:
     [{id}] {title} — {status}/{priority}
     ...
   ```

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
   ## Wave status
   > Wave 0: {N} items completed this session, {M} remaining
   > Next wave (wave 1): {N} items unblocked by this session's completions
   > Wave freshness: {Were items added/closed/blockers changed? If yes, run `/backlog update` at next session start.}
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
3. For items being promoted or attached, **require**:
   - **Category** (Cat): suggest from title keywords using heuristics below; operator confirms
   - **Effect**: suggest from title keywords using effect heuristics (see `/backlog add`); operator confirms
   - **Size**: estimate effort (XS/S/M/L/XL)
   - **Priority**: P0-P3
   - **Review Date** (deferrals only): must not be empty — use `YYYY-MM-DD`, `after:{id}`, or `quarterly`
4. **Category suggestion heuristics**:
   - Title contains `script`, `pipeline`, `CLI`, `tool`, `runner` → suggest `S` (system)
   - Title contains `evaluator`, `grade`, `grading`, `heal`, `threshold` → suggest `S` (system)
   - Title contains `GAP-`, `fix`, `overclaim`, `caveat`, `import`, family/platform names → suggest `C` (content-fix)
   - Title contains `AGENTS.md`, `policy`, `skill`, `hook`, `forbidden` → suggest `G` (governance)
   - Title contains `test`, `coverage`, `regression`, `assert` → suggest `T` (test)
   - Title contains `backlog`, `plan`, `session`, `onboarding`, `CI` → suggest `H` (housekeeping)
5. Apply the disposition:
   - **Promote**: move to appropriate section in `backlog/BACKLOG.md` with Cat, Size, Priority, Wave=0
     - **Durable plan warning**: If promoted to P0/P1 and Plan path starts with `.claude/plans/`, warn: `⚠ Ephemeral plan path — P0/P1 items should use plans/from_backlog/ for durability`
   - **Attach**: add plan reference, move to BACKLOG.md with Cat, Size, Priority
   - **Defer**: move to Deferred section with reason AND Review Date (required, never empty)
   - **Drop**: remove from inbox.md (no further tracking)
6. Remove triaged items from `backlog/inbox.md` (enforce single-location rule)
7. Output summary: `{N} promoted, {N} attached, {N} deferred, {N} dropped`

### `/backlog reconcile` — Evidence-Based Reconciliation

Compare active backlog items against current system evidence and classify each item.

**Steps:**
1. Read `backlog/BACKLOG.md` — collect all Active and Queued items
2. For each item, run these evidence checks:

   **a. Plan check** — Read the referenced plan file, extract taskcard status:
   - Taskcard marked Done/Closed → candidate for closure
   - Taskcard marked In Progress → verify against other evidence
   - Plan file missing (path in Plan column does not exist on disk) → flag as ORPHANED_PLAN:
     - Add `plan-artifact-missing:{path}` to Evidence column
     - If item is P0/P1: auto-set status to `blocked` and report as first-priority finding
     - Report: `[{id}] ORPHANED_PLAN: {path} does not exist on disk`
   - Plan file archived → flag as ORPHANED

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

5. **Cross-Item Analysis** (after per-item checks):
   - For each pair of STILL-OPEN items: compute signal score (see Relationship Taxonomy)
   - For each STILL-OPEN item vs. each RESOLVED item (last 30 days): check if the resolved fix also addresses the open item
   - For each pair with score ≥3: flag as candidate relationship
   - Present relationship candidates in the report:
     ```
     CROSS-ITEM RELATIONSHIPS DETECTED:
       [{id1}, {id2}, ...] — {relationship type} ({shared signals})
         Recommendation: {group under parent | verify and close | link with related-to:}
     ```

6. Apply operator-confirmed actions:
   - RESOLVED → move to Recently Completed with evidence in Evidence column
   - PARTIAL → update status to `in-progress`, attach evidence note
   - STALE → flag in next briefing, ask operator to re-prioritize or defer
   - SUPERSEDED → mark `dropped` with `superseded-by:{item-ID}` in Evidence column
   - ORPHANED → move to inbox for re-triage
   - RELATIONSHIP CANDIDATE → apply operator-chosen action (merge/group/link/separate)

7. **Auto-archive completed items >30 days**: Check Recently Completed section. Items with Completed date >30 days ago are moved to `backlog/ARCHIVE.md`. Log the move.

8. **Deferred review check**: Read the Deferred table. For each item where Review Date has passed (specific date <= today, or `quarterly` and >=90 days since deferral), surface in the report as "due for review."
   **Triggered-review scan**: For each deferred item with Review Date `after:{item-id}`, check if that item's current status in BACKLOG.md is `done`. If yes, flag the deferred item for operator review:
   ```
   REVIEW TRIGGERED: [{deferred-id}] {title}
     Condition: after:{item-id} (which is now done as of {completion-date})
     Recommendation: evaluate for promotion to queued, deferral extension, or drop
   ```

8b. **GAP-* artifact detection**: After staleness scan, check `backlog/inbox.md` for rows where (a) ID starts with `GAP-` AND (b) the referenced report file path does not exist on disk (test with `os.path.exists()` or equivalent). Drop these rows and include in reconcile report:
   ```
   Dropped stale gap artifacts: N
     - GAP-{id} (report file missing: {path})
   ```
   These are test/debug artifacts created during gap escalation testing. They are never valid active items if their report files are gone.

8c. **Done-item section check**: Scan all BACKLOG.md sections that are NOT "Recently Completed", "Superseded", or "Deferred" for rows where the Status cell equals `done`. Count them. Include in reconcile report:
   ```
   Done items not yet moved to Recently Completed: N
     - [{id}] {title} — currently in {section name}
   ```
   For each found item, move the row to the Recently Completed section. This corrects the failure mode where `/backlog close` was skipped and items were only marked `done` in-place.

9. **Recompute waves**: Rebuild Blocker DAG and update Wave column for all Active and Queued items.

10. Append all status changes to `backlog/CHANGELOG.md`

## Target Resolution

Every planning subcommand that accepts `{target}` resolves it to a canonical
`(backlog_item, plan_path)` tuple using this algorithm:

**Step 1 — Classify input type:**
- If `{target}` matches an ID pattern (`SR-T01`, `MP-SR03`, `H-TC01`, `INV-001`, `ST-001`): treat as **backlog ID**
- If `{target}` is a file path (contains `/` or ends in `.md`): treat as **plan path**
- Otherwise: treat as **freetext query**

**Step 2 — Resolve to canonical backlog item:**
- **Backlog ID**: Look up in `backlog/BACKLOG.md` (Active, Queued, Deferred, Recently Completed) and `backlog/inbox.md`. If not found → `UNRESOLVED: {target} not in backlog`.
- **Plan path**: Read the plan file. Extract all backlog IDs from Backlog Cross-Reference tables, `Gap linkage:` fields, and `Backlog ID:` fields. Return the set of associated items.
- **Freetext query**: Search `backlog/BACKLOG.md` titles for substring match (case-insensitive). If exactly one match → use it. If multiple → present numbered list and ask operator. If zero → search plan file titles in `plans/healing/`, `plans/from_chat/`, `plans/from_backlog/`, `.claude/plans/`. If still zero → `UNRESOLVED: no match for "{target}"`.

**Step 3 — Resolve to existing plan file:**
- Read the `Plan` column from the matched BACKLOG.md row. If non-empty → that is the plan path.
- If no Plan column entry → grep plan file locations for the backlog ID string.
- Result: `(backlog_item, plan_path)` or `(backlog_item, None)`.

**Step 4 — Validate:**
- If plan_path is set, verify file exists on disk. If missing → flag `ORPHANED_PLAN`.
- Return resolved tuple to calling subcommand.

**Step 5 — Discover related items** (if relationship tags exist):
- Read the resolved item's Evidence column for tags: `symptom-of:`, `related-to:`, `parent-problem`, `cluster:`
- If `symptom-of:{id}` → read parent item, collect all siblings
- If `parent-problem` → read all items with `symptom-of:{this_id}`
- If `related-to:{ids}` → read those items
- Include related items in resolution output for context

---

## Planning Subcommands

### `/backlog status {target}` — Pre-Planning State Investigation

Investigate the current system state for a backlog item before planning or replanning.
Read-only — does not modify any files.

**Steps:**
1. Resolve `{target}` using Target Resolution
2. Read backlog entry (status, priority, plan reference, evidence column)
3. If plan exists, read plan file and extract taskcard statuses
4. Run evidence checks (same as `/backlog reconcile` but single-item):
   - **Plan check**: taskcard statuses from plan file
   - **Commit check**: `git log --grep="{id}" --oneline`
   - **Content check**: frontmatter grades on referenced pages (if content item)
   - **Test check**: referenced test files/functions exist (if test item)
   - **Code check**: referenced scripts exist and were modified since item creation
5. Classify status: `done` | `partially-done` | `not-done` | `done-incorrectly` | `obsolete` | `superseded` | `blocked` | `cannot-verify`
6. If relationship tags exist, show related items from Step 5 of Target Resolution
7. Output:

```
BACKLOG STATUS — {id}: {title}
Classification: {status}
Priority: {P0-P3} | Plan: {path | none} | Staleness: {N days | fresh}

Evidence:
  Plan: {taskcard summary}
  Commits: {hash list or "none found"}
  Content: {grade summary or "N/A"}
  Tests: {test summary or "N/A"}
  Code: {script modification summary or "N/A"}

Related items: {list or "none"}

Conclusion: {1-2 sentence assessment}
Recommendation: {plan | replan | close | defer | investigate-further}
```

### `/backlog plan {target}` — Create New Plan File

Create a brand-new governed plan file for a backlog item or problem statement.
A plan invocation MUST create a new file. It must NEVER amend an existing plan.

**Steps:**
1. Resolve `{target}` using Target Resolution
2. **Plan-vs-replan guard**: If an active plan already exists for this item:
   - Warn: `Active plan exists at {path}. Use /backlog replan to amend.`
   - If operator passes `--force`, create parallel plan with predecessor link
   - Otherwise halt and suggest `/backlog replan`
3. Run `/backlog status {target}` internally to gather current state
4. **Investigate the real system**: Read relevant files, check git history, inspect code, understand the actual problem. Do not trust backlog wording alone.
5. **Root-cause analysis**: Distinguish symptom from source. Identify why existing checks/plans/skills did not catch it.
6. **Solution options**: Consider at least 2 approaches. Choose the best and explain why.
7. **Generate plan file** at `plans/from_backlog/{YYYY-MM-DD}-{slug}.md` using the Plan File Template (see below)
   **Ephemeral path governance (P0/P1 items)**: If the item is P0 or P1 and the plan path would be under `.claude/plans/`, emit this warning before writing:
   ```
   ⚠️  EPHEMERAL PLAN PATH for P0/P1 item [{id}]
   Path '.claude/plans/{slug}.md' is per-user and NOT committed to git.
   It will be lost when sessions end or on a fresh clone.
   Required: write to 'plans/from_backlog/{YYYY-MM-DD}-{slug}.md' instead.
   Use '.claude/plans/' only for P2/P3 items where loss is acceptable.
   ```
   This is a hard warning for P0/P1. If operator overrides, add `ephemeral-path-acknowledged` to the Evidence column.
8. Run `/backlog harden {plan-path}` on the new file
9. Update `backlog/BACKLOG.md` — set the Plan column to the new file path
10. Append to `backlog/CHANGELOG.md`
11. Output: `Created plan: {path} with {N} taskcards`

**Slug derivation**: From backlog item title — lowercase, spaces to hyphens, strip non-alphanumeric except hyphens, max 50 chars.

### `/backlog replan {target}` — Amend Existing Plan In Place

Amend an existing plan file with a dated delta section preserving all history.
A replan invocation MUST amend the existing file. It must NEVER create a replacement.

**Steps:**
1. Resolve `{target}` using Target Resolution
2. **Replan guard**: If no plan exists for this item:
   - Error: `No existing plan found for {id}. Use /backlog plan to create one.`
   - Halt
3. Read the FULL existing plan. Extract all taskcards and their current statuses.
4. Run `/backlog status {target}` internally to gather fresh evidence
5. **Re-investigate the real system**: Verify every meaningful assumption in the existing plan against current code and system state
6. **Identify deltas**:
   - What changed since the previous plan version
   - What was validated as still correct
   - What is now obsolete (with evidence)
   - What is partially implemented
   - What remains
   - New blockers, new evidence, changed sequencing
   - Newly required taskcards
7. **Append** a dated `## Replan — {YYYY-MM-DD}` section to the plan file containing:
   ```
   ## Replan — {YYYY-MM-DD}
   > Reason: {why this replan is needed}
   > Evidence: {what changed since last version}

   ### Assumptions Validated
   - {assumption}: still correct ({evidence})

   ### Assumptions Invalidated
   - {assumption}: now obsolete ({evidence})

   ### Status Updates
   | TC | Old Status | New Status | Reason |
   |----|------------|------------|--------|

   ### New Taskcards
   {full taskcards using Taskcard Standard}

   ### Updated Backlog Cross-Reference
   | Backlog ID | Plan TC | Phase |
   |------------|---------|-------|
   ```
8. Update plan header `> Status:` if needed
9. Run `/backlog harden {plan-path}` on the amended file
10. Update `backlog/BACKLOG.md` with any status changes
11. Append to `backlog/CHANGELOG.md`
12. Output: `Replanned: {path} — {N} status updates, {M} new taskcards`

### `/backlog harden {plan-path}` — Plan Gap Sweep + Auto-Patch

Run structural completeness checks against a plan file and auto-fix what can be fixed.

**Steps:**
1. Read the plan file at `{plan-path}`
2. Run these 14 checks:

| # | Check | Severity | Auto-fixable |
|---|-------|----------|-------------|
| H-01 | Plan has `> Status:` line in header | ERROR | Yes — insert `> Status: active` |
| H-02 | Plan has `> Created:` date | ERROR | Yes — insert today |
| H-03 | Plan has `## Context` section | WARN | No |
| H-04 | Plan has `## Goals` with ≥1 numbered item | WARN | No |
| H-05 | Plan has `## Gap Table` with ≥1 row | WARN | No |
| H-06 | Every Gap Table row references existing Taskcard | ERROR | No — report missing TC |
| H-07 | Every Taskcard has `**Status:**` field | ERROR | Yes — insert `open` |
| H-08 | Every Taskcard has `**Priority:**` field | WARN | Yes — insert `P2` |
| H-09 | Every Taskcard has `#### Acceptance checks` | WARN | No |
| H-10 | Every Taskcard has Allowed paths or Forbidden | WARN | No |
| H-11 | Plan has `## Backlog Cross-Reference` table | WARN | Yes — generate from TC Backlog ID fields |
| H-12 | Every Backlog ID in Cross-Reference exists in BACKLOG.md | ERROR | No — report missing |
| H-13 | No taskcard references AGENTS.md §4 FORBIDDEN paths | ERROR | No — report violation |
| H-14 | Status not `active` while all taskcards are terminal | WARN | Yes — suggest close |

3. Apply auto-fixes for fixable items
4. Output:

```
PLAN HARDENING — {plan-path}
Checks run: 14
  PASS: {N}    WARN: {N}    ERROR: {N}

Findings:
  [{H-NN}] {severity}: {description}

Auto-fixes applied: {N}
  [{H-NN}] {what was fixed}

Remaining issues requiring operator action: {N}
```

### `/backlog trace {target}` — Requirement-to-Taskcard Traceability

Build the full traceability chain for a backlog item.
Read-only — does not modify any files.

**Steps:**
1. Resolve `{target}` using Target Resolution
2. For each backlog item in the resolved set, build the chain:
   - Backlog item → Plan file → Taskcard(s) → Gap(s) → Commits → Content/Test state
3. Identify gaps in the chain (missing taskcards, uncommitted work, untested deliverables)
4. Output:

```
TRACEABILITY — {id}: {title}

| Backlog ID | Plan TC | Gap | Commits | Content | Tests | Status |
|------------|---------|-----|---------|---------|-------|--------|

Chain gaps: {count}
  - {description of each gap}
```

### `/backlog close {target}` — Governed Closeout

Close a backlog item only after verifying implementation, tests, commits, and plan status all agree. Refuses false closure.

**Steps:**
1. Resolve `{target}` to `(backlog_items[], plan_path)`
2. For each item, verify the evidence chain:

   **a. Plan evidence**: Taskcard status is terminal (`done`/`closed`/`deferred`)
   - If not terminal → FAIL: `"{TC-ID} is still {status} — cannot close"`

   **b. Acceptance check replay**: Present each taskcard's CLI acceptance commands
   - Ask operator: `Verified? (y/n/skip)`
   - If any `n` → FAIL

   **c. Commit evidence**: `git log --grep="{id}" --oneline`
   - Collect hashes as evidence
   - Zero commits + no operator attestation → WARN

   **d. Content evidence** (content items): Page grades meet expected level

   **e. Test evidence** (test items): Test files/functions exist

3. **No false closure guard**: At least one of (commit hash, test reference, grade state, operator attestation) must be present. No exceptions.

4. Apply transitions:
   - **REQUIRED: Physically move the row** from its current section (Active/Queued/Deferred) to the "Recently Completed" section in `backlog/BACKLOG.md`. Do NOT only update the Status cell in-place — the row must be removed from its current section and appended to Recently Completed with evidence summary. Updating Status=done in-place without moving the row is an incomplete close; re-run if this occurred.
   - Update plan taskcard statuses to `done` (in-place edit — closeout is terminal)
   - Update plan `> Status:` to `closed` if all taskcards are terminal
   - Append to `backlog/CHANGELOG.md`

5. Output:

```
CLOSEOUT — {target}
Items closed: {N}
  [{id}] {title} — CLOSED
    Evidence: {summary}
Items not closeable: {N}
  [{id}] {title} — {reason}

Plan status: {closed | still active (N open taskcards remain)}
```

---

## Relationship Taxonomy

The backlog system distinguishes five relationship types between items:

| Type | Definition | Key test | Default action |
|------|-----------|----------|----------------|
| **Exact duplicate** | Same root problem, same scope, same outcome | Identical allowed_paths + same affected files + same acceptance criteria | Block new entry; point to existing |
| **Near duplicate** | Highly overlapping scope, different wording | ≥70% file overlap + similar title keywords | Link or merge; ask operator |
| **Symptom-sibling** | Different symptoms, same root cause | Same triggering commit OR one fix resolves both | Group under root-cause parent; keep separate child taskcards |
| **Related cluster** | Coordinated execution needed, distinct root causes | Same subsystem + shared file modifications | Cross-reference with `related-to:`; suggest sequencing |
| **Legitimately separate** | Similar domain, truly different problem | Different root causes + different affected files | No action; confirm if flagged |

### Matching signals and weights

| Signal | Weight | Rationale |
|--------|--------|-----------|
| Same file in allowed_paths | 3 | Strongest execution conflict indicator |
| Same commit in evidence | 3 | Same root cause proven |
| Same plan file reference | 2 | Already logically grouped |
| Same subsystem | 2 | Likely coordinated execution |
| Title keyword overlap ≥0.7 (Jaccard on words) | 2 | Strong textual match |
| Same blocker | 1 | Correlated but may be coincidence |
| Same session origin | 1 | Temporal correlation |
| Title keyword overlap 0.5–0.7 | 1 | Weak textual match |

**Classification thresholds** — sum of matching signal weights:
- ≥5 → exact/near duplicate candidate
- 3–4 → symptom-sibling candidate
- 2 → related cluster candidate
- 0–1 → likely separate

All classifications are presented to the operator for confirmation. No auto-merge, no auto-group.

## Relationship Metadata

Relationship tags in the **Evidence** column of `backlog/BACKLOG.md` (backward-compatible with existing `superseded-by:` convention):

| Tag | Format | Meaning |
|-----|--------|---------|
| `duplicate-of:{id}` | Single ID | Exact duplicate; `{id}` is authoritative |
| `related-to:{id1},{id2}` | Comma-separated | Cross-reference to related items |
| `symptom-of:{id}` | Single ID | Symptom child; `{id}` is root-cause parent |
| `parent-problem` | Flag | Root-cause umbrella for symptom children |
| `cluster:{name}` | Short name | Named group for operator visibility |
| `merged-into:{id}` | Single ID | Item was merged; `{id}` survived |
| `superseded-by:{id}` | Single ID | (existing) Item replaced by newer work |

**Merge rules**: When items merge, the surviving item keeps its ID/title/status. The absorbed item gets `dropped` with `merged-into:{id}`. Evidence from absorbed item is copied to survivor. CHANGELOG records both transitions.

**Grouping rules**: Parent items are navigation aids, not execution units. Children retain their own status, priority, plan references, and taskcards. Parent status = `in-progress` while any child is open; `done` only when ALL children are terminal.

**Resume workflow**: An agent starting from any item reads its Evidence tags. If `symptom-of:{id}` → read parent to see all siblings. If `parent-problem` → read all children. `/backlog status` includes this discovery automatically.

### `/backlog merge {source_id} into {target_id}` — Merge Items

Merge one backlog item into another, preserving evidence.

**Steps:**
1. Read both items from `backlog/BACKLOG.md`
2. Verify source is not already completed (warn if so)
3. Show both items side-by-side; ask operator to confirm
4. Apply merge:
   - Target keeps its ID, title, status
   - Source gets status `dropped`, Evidence `merged-into:{target_id}`
   - Source's evidence (commits, tests) copied to target's Evidence
   - Source's plan cross-reference added to target's plan
5. Append to `backlog/CHANGELOG.md`
6. Output: `Merged [{source_id}] into [{target_id}]. Source dropped.`

**Anti-over-merge rules:**
- Do not merge across priority tiers (P0 into P2). Use `related-to:` instead.
- Do not merge items with different plan files. Use `related-to:` and document execution order.
- Maximum 7 children per parent. Split into sub-groups if exceeded.
- Operator confirmation required for all merges.

### `/backlog group {id1} {id2} [id3...] --parent {parent_id|new}` — Group Symptom-Siblings

Group related items under a root-cause parent.

**Steps:**
1. Read all specified items from `backlog/BACKLOG.md`
2. If `--parent new`: create new parent item with `parent-problem` tag
3. If `--parent {id}`: add `parent-problem` tag to existing item
4. Add `symptom-of:{parent_id}` to each child item's Evidence
5. Optionally add `## Related Items` section to parent's plan file
6. Append to `backlog/CHANGELOG.md`
7. Output: `Grouped [{ids}] under parent [{parent_id}]`

### `/backlog link {id1} {id2}` — Cross-Reference Items

Lightweight bidirectional cross-reference without hierarchy.

**Steps:**
1. Add `related-to:{id2}` to id1's Evidence
2. Add `related-to:{id1}` to id2's Evidence
3. Append to `backlog/CHANGELOG.md`
4. Output: `Linked [{id1}] ↔ [{id2}]`

---

## Execution Sequencing Subcommands

### `/backlog next [--count N]` — Wave-Based Execution Queue

Compute dependency waves and return the top N executable items. Read-only.

> **Idempotent:** Safe to call multiple times — read-only, no state changes.

**Steps:**
1. Read `backlog/BACKLOG.md` — collect all Active and Queued items with status `queued` or `next`
2. Build a directed acyclic graph from the Blocker column:
   - Each item is a node
   - Each Blocker reference is a directed edge (blocker → blocked)
   - Items with `none` or empty Blocker are root nodes
3. **Cycle detection**: If a cycle is found, flag the involved items and exclude them from wave computation
4. Compute topological layers (waves):
   - Wave 0: items with no blockers
   - Wave 1: items whose all blockers are in wave 0
   - Wave N+1: items whose all blockers are in wave 0..N
5. Filter wave 0 items: remove any with status `blocked`, `waiting`, `in-progress`, or `deferred`
5a. **Plan artifact check**: For remaining wave-0 items with a non-empty Plan column, verify the file exists on disk. Items with `plan-artifact-missing:` in Evidence are excluded from "Ready now" and listed separately as "Blocked (missing plan)".
6. Rank remaining wave-0 items by:
   a. Priority tier (P0 first, then P1, P2, P3)
   b. Impact score from Evidence column (`impact:I{n}` — lower I = higher impact; I1 > I2 > I3)
   c. Size ascending (XS first — quick wins surface)
6a. **Self-verify size ordering**: Within each priority tier, confirm sizes are non-decreasing (XS ≤ S ≤ M ≤ L ≤ XL). If any adjacent pair is out of order, swap them.
7. Return top N items (default 5)
8. Separately list G=0 items (no plan or no acceptance checks, effort >= M) as "needs planning"
9. Output:

```
EXECUTION QUEUE — {date}

Ready now (wave 0):
  1. [{id}] {title} — {cat}/{priority}/{size} [{effect}]
  2. [{id}] {title} — {cat}/{priority}/{size} [{effect}]
  ...

In progress: {count}
  - [{id}] {title} — since {date or "unknown"}

Next wave (wave 1, {count} items):
  - [{id}] {title} — waiting on [{blocker_ids}]

Blocked (missing plan): {count}
  - [{id}] {title} — plan-artifact-missing: {path}

Needs planning before execution: {count}
  - [{id}] {title} — missing: {plan | acceptance checks}

Waves summary: {wave_count} waves, {total_items} items
  Wave 0: {n} ready | Wave 1: {n} | Wave 2: {n} | ...
```

### `/backlog sweep` — Batch Plan File Cleanup

Scan plan directories for completed, orphaned, and stale plan files. Suggest archival.

**Steps:**
1. Scan these directories for `.md` files:
   - `plans/healing/`
   - `plans/from_chat/`
   - `plans/from_backlog/`
2. For each file:
   a. Extract all taskcard statuses (using same patterns as `/backlog update`)
   b. Check if any `backlog/BACKLOG.md` Active or Queued item references this file in Plan column
   c. Check file mtime (last modification date)
3. Classify each file:
   - **ARCHIVABLE**: All taskcards terminal (done/closed/deferred/dropped) AND no active backlog item references it
   - **ORPHANED**: No taskcard status markers found AND no backlog item references it AND file mtime >30 days
   - **STALE**: At least one non-terminal taskcard AND file mtime >30 days AND no backlog item references it
   - **ACTIVE**: At least one non-terminal taskcard OR referenced by active backlog item
4. Output report:

```
PLAN SWEEP — {date}
Directories scanned: {list}
Files found: {total}

  ARCHIVABLE: {count} — all tasks done, no active backlog refs
    {path} (last modified: {date})
    ...

  ORPHANED: {count} — no status markers, no backlog refs, >30d old
    {path} (last modified: {date})
    ...

  STALE: {count} — open tasks but no activity >30d
    {path} (last modified: {date})
    ...

  ACTIVE: {count} — in use
```

5. If ARCHIVABLE + ORPHANED > 0:
   - Ask operator: `Archive {N} completed/orphaned plans? (y/n/selective)`
   - If `y`: invoke `/backlog archive` for each ARCHIVABLE and ORPHANED file
   - If `selective`: present numbered list, operator picks which to archive
   - If `n`: no action taken
6. For STALE files: suggest investigation or deferral, do not auto-archive

---

## Taskcard Standard

Every taskcard in a plan file governed by `/backlog plan` or `/backlog replan` must include:

**Required fields:**
- `**Priority:**` P0–P3
- `**Effort:**` XS/S/M/L/XL
- `**Status:**` open | in-progress | nearly-done | blocked | done | dropped | deferred
- `**Gap linkage:**` G-NN reference (or `standalone`)
- `#### Scope` section with Problem + Work required
- `**Allowed paths:**` (at least one file or directory)
- `#### Acceptance checks` with at least one CLI command and expected output

**Optional fields** (include when relevant):
- `**Backlog ID:**` — when taskcard maps to a tracked backlog item
- `**Depends:**` TC-NN — when hard ordering dependency exists
- `**Forbidden:**` — specific paths/actions to avoid
- `#### Deliverables` — when output is not obvious from acceptance checks
- `#### Rollback` — for changes touching production content or system scripts
- `#### Review dimensions` table — only for Effort L or XL taskcards

## Plan File Template

New plan files created by `/backlog plan` use this structure:

````markdown
# {Title}
> Created: {YYYY-MM-DD}
> Source: /backlog plan — {backlog_item_id}: {title}
> Status: active
> Predecessor: {path_to_prior_plan | none}

## Context
{2-4 sentences: what is broken/missing, how discovered, why it matters now.}

## Goals
1. {Concrete verifiable outcome}

## Gap Table

| Gap ID | Severity | Description | Taskcard |
|--------|----------|-------------|----------|
| G-01 | {Critical/High/Medium/Low} | {description} | {TC-ID} |

## Taskcards

---

### {TC-ID} — {Short title}
**Priority:** {P0-P3} | **Effort:** {XS/S/M/L/XL} | **Status:** open
**Gap linkage:** {G-NN}
**Backlog ID:** {backlog_item_id}

#### Scope
**Problem:** {what is broken/missing}
**Work required:**
1. {step}

**Allowed paths:**
- {file or directory}

**Forbidden:** {what must not be touched}

#### Acceptance checks
```bash
{exact command}
# Expected: {output}
```

#### Deliverables
- {file or artifact}

#### Rollback
{revert steps}

---

## Healing Triage
- New information during execution: patch this plan (append to latest Replan delta)
- Failed acceptance check: stop-the-line, investigate root cause, add new taskcard
- Partially proven assumption: downgrade confidence, add verification taskcard
- False-green signal: re-run with --no-cache/--force, compare, escalate if divergent
- Re-entry loop: investigate → patch plan → implement → prove → update status

## Backlog Cross-Reference

| Backlog ID | Plan TC | Phase |
|------------|---------|-------|
````

## Replan Delta Template

Replan deltas are appended to existing plan files by `/backlog replan`:

```markdown
---

## Replan — {YYYY-MM-DD}
> Reason: {why}
> Evidence: {what changed}

### Assumptions Validated
- {assumption}: still correct ({evidence})

### Assumptions Invalidated
- {assumption}: now obsolete ({evidence})

### Status Updates
| TC | Old Status | New Status | Reason |
|----|------------|------------|--------|

### New Taskcards
{full taskcards using Taskcard Standard}

### Updated Backlog Cross-Reference
| Backlog ID | Plan TC | Phase |
|------------|---------|-------|
```

---

## Files

| File | Purpose |
|------|---------|
| `backlog/BACKLOG.md` | Canonical backlog index — single source of truth for all items (includes Wave column for execution sequencing) |
| `backlog/ARCHIVE.md` | Completed items >30 days old — moved by reconcile |
| `backlog/REMINDERS.md` | Reminder queue — surfaced at session boundaries |
| `backlog/HANDOFF.md` | Session handoff — what happened, what's next |
| `backlog/inbox.md` | Unattached items — investigation, standalone tasks, ideas |
| `backlog/CHANGELOG.md` | Append-only audit trail of status changes |
| `plans/from_backlog/` | Plan files created by `/backlog plan` — distinct provenance from healing/chat plans |
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
- **Plan creates, never amends**: `/backlog plan` always creates a new file in `plans/from_backlog/`. If an active plan exists, it warns and suggests `/backlog replan` instead.
- **Replan amends, never creates**: `/backlog replan` always appends a dated delta to an existing file. If no plan exists, it errors and suggests `/backlog plan` instead.
- **Replan is append-only**: Replan sections are appended chronologically. Earlier sections are never edited (except terminal closeout status).
- **Harden before publish**: `/backlog plan` and `/backlog replan` both call `/backlog harden` before completing.
- **Intake dedup is mandatory**: `/backlog add` and `/backlog investigate` run the Relatedness Check before adding. Operator can override, but the check always runs.
- **No auto-merge**: Relationship detection is automated; merge/group/link actions always require operator confirmation.
- **Anti-over-merge**: Max 7 children per parent. No cross-priority-tier merge. No cross-plan-file merge. See `/backlog merge` for full rules.
