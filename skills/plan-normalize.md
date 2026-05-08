<!-- CONTRACT: agent-executed
     purpose:       review and normalize a plan file into an execution-safe working set;
                    classify sections, verify claims against current repo state, extract
                    open work, recommend single next executable item, produce exclusion list
     preconditions: plan file exists and is readable; .venv usable; related files (if
                    supplied) exist; backlog/BACKLOG.md and backlog/HANDOFF.md are optional
     postcondition (assess):  PLAN-NORMALIZE VERDICT block written to stdout; no files modified
     postcondition (amend):   execution-pack sibling created alongside the plan (or plan
                               edited in-place with --in-place); verdict written to stdout
     postcondition (launch):  first safe item executed; plan/exec-pack updated with evidence;
                               backlog/HANDOFF.md updated if item maps to a backlog entry
     idempotent:    yes for assess; no for launch (executes real work)
     verified: 2026-04-17
-->
# S-91: Plan Normalize — Execution-Safe Plan Quality Gate

**Arguments**: $ARGUMENTS
Expected format: `{plan-file} [--related {path}...] [--mode assess|amend|launch] [--in-place]`

## Purpose

Stop agents from executing mixed-context plans blindly.

Plans accumulate historical design context, sprint archives, completed-work records,
and capability claims at various maturity levels. An agent resuming or inheriting such
a plan cannot safely distinguish "done" from "still open" or "spec-only" from
"verified live" without explicit classification.

This skill classifies every section of the target plan, verifies claims against the
current repo state, extracts only still-open work, and produces a single next
executable item — blocking execution if any failure condition is met.

**This skill is the mandatory gate before executing any plan that is:**
- inherited from another agent
- long (>4 H2 sections) or contains archive/postmortem/sprint content
- last modified more than 7 days ago
- the output of a prior planning skill that was not immediately executed

It does not replace specialized planning skills. It sits above them as a quality
and execution-readiness gate.

## Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `{plan-file}` | required | Path to the target plan file |
| `--related {path}` | none | Zero or more related files (backlog, handoff, conventions, reminders); may be specified multiple times |
| `--mode assess` | **default** | Classify and produce verdict only; no file writes |
| `--mode amend` | — | Classify + write execution-pack sibling; optionally edit plan in-place |
| `--mode launch` | — | assess + amend then execute only the single recommended next item |
| `--in-place` | off | (amend/launch only) Edit the plan file directly instead of creating a sibling |

## Pre-conditions

1. `{plan-file}` argument is present and the file exists on disk
2. `.venv` is usable (for skill context gates)
3. All `--related` paths (if supplied) exist
4. `backlog/BACKLOG.md` and `backlog/HANDOFF.md` are read if they exist (non-blocking)

## Steps

> **Skill context gate** — run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-91 --scope "{plan-file}"
> ```

### Step 1 — Parse arguments

Extract `{plan-file}`, all `--related` paths, `--mode`, and `--in-place` from `$ARGUMENTS`.

Verify `{plan-file}` exists. If missing, abort immediately with:
```
PLAN-NORMALIZE: file not found: {path}
Aborting — no plan to normalize.
```

### Step 2 — Read all inputs

Read the target plan file in full. Record:
- All H2 / H3 section headers (titles become the section map rows)
- Presence of indicator keywords in each section: "archive", "completed", "sprint",
  "postmortem", "amendment", "historical", "done", "superseded", "intentionally omitted",
  "must not", "out of scope", "implemented", "spec-only", "documented", "partially validated"
- Any explicit capability-maturity language
- Any explicit next-step sentences ("recommended next action", "execute", "run next")

Read all `--related` files.
Read `backlog/BACKLOG.md` (if exists): note status of any items that share titles with
plan sections.
Read `backlog/HANDOFF.md` (if exists): note "What was done" and "Critical path" content.

### Step 3 — Classify every major section

For each H2 (or H3 where H2 is absent), assign exactly one classification:

| Classification | Keep for execution | Meaning |
|----------------|--------------------|---------|
| `historical-reference` | no | Prior design decisions, context, motivation — not actionable |
| `verified-current-state` | conditional | Claims the agent can verify against files/code right now |
| `completed-archive` | no | Work explicitly finished; must not drive new execution |
| `open-actionable` | yes | Work that is still open and potentially executable |
| `operator-guidance` | yes | Rules, constraints, non-goals set by the operator |
| `design-rationale` | no | Why choices were made; not executable on its own |
| `intentionally-omitted` | yes (exclusions only) | Features or work explicitly ruled out of scope |

If a section cannot be unambiguously assigned one classification, mark it `ambiguous`
and record it as a blocking condition for the verdict.

### Step 4 — Extract all claims

From every `open-actionable` and `verified-current-state` section, extract:

- **Capability claims**: "X is implemented", "Y is live", "Z works in production"
- **Next-step claims**: "The next action is…", "Recommended: run…", "Execute…"
- **Status claims**: "Done", "Complete", "Passing", "Blocked by…"
- **Omission markers**: "Do not build", "Out of scope", "Must not" → feed exclusions

### Step 5 — Verify claims against current repo state

For each capability and next-step claim, attempt verification:
- **Capability claims** → check referenced files exist; check referenced scripts are
  present at the stated path; check referenced skills appear in AGENTS.md §12 / [docs/registries/skills.md](../docs/registries/skills.md)
- **Next-step claims** → check the referenced command/skill is registered; check its
  preconditions are currently met
- **Status claims** → cross-reference against backlog item status, HANDOFF.md "What
  was done", and `git log --oneline -20` (read-only)
- **Omission markers** → record verbatim; do not verify (operator-set constraints)

Classify each claim:

| Claim status | Meaning |
|--------------|---------|
| `live-verified` | Confirmed against current repo state |
| `likely-true` | Consistent with related files but not directly verifiable |
| `unverified` | Plan asserts this; no current evidence found |
| `contradicted` | Current repo state contradicts the plan's assertion |

### Step 6 — Extract open work

From `open-actionable` sections only, extract every distinct work item.
Mark each with exactly one status:

| Status | Meaning |
|--------|---------|
| `ready` | Unblocked; preconditions met; files/commands identified |
| `blocked` | Depends on another item or external state not yet ready |
| `stale` | Referenced files/commands no longer exist as described |
| `already-done-elsewhere` | Evidence in git/backlog shows this is complete |
| `needs-replan` | Too vague, contradicted, or missing files/validation |
| `invalid-superseded` | Explicitly superseded in plan or backlog |

### Step 7 — Select one next executable item

From all `ready` items, select the single best candidate using these preferences in order:

1. Real remediation over meta-work (writing plans, filing reports, updating docs)
2. Unblocked work over vague strategic work
3. Has named files and a clear validation method
4. Does not depend on a capability classified `unverified` or `contradicted`
5. Matches the current system state, not prior plan intent

If no `ready` item exists, record `PLAN-NORMALIZE: no ready items — execution blocked`
and do not select a candidate.

Never select multiple items. For each non-chosen candidate, record why it did not win.

### Step 8 — Check failure conditions

**Set `execution-ready-as-is: no` and block launch if any of the following are true:**
- Two or more sections are classified `ambiguous`
- The recommended next action is `unverified` or points outside the plan without a
  registered skill to invoke
- Any `open-actionable` item that is `ready` relies on a capability classified
  `unverified` or `contradicted`
- The plan reopens a `completed-archive` item without `contradicted` evidence of regression
- The next item has no named files, no clear validation method, or no completion evidence
- The plan directly contradicts current repo state in a way that blocks safe execution

### Step 9 — Produce the PLAN-NORMALIZE VERDICT block

Write the six-section output (see Output Schema below).

### Step 10 — If `--mode amend`

**Without `--in-place`** (default): Write `{plan-file-stem}-exec-pack.md` alongside the
source plan. The exec pack contains only:
- Open work table (ready items only, columns: ID, Title, Status, Files, Validation)
- Recommended next item with why-it-wins rationale
- Exclusions list
- Ordered validation steps

Historical, rationale, and archive sections are excluded from the exec pack.

**With `--in-place`**: Edit the plan file directly:
1. Wrap all `historical-reference`, `completed-archive`, and `design-rationale` sections
   in HTML comment markers: `<!-- ARCHIVE-START: {section title} -->` …
   `<!-- ARCHIVE-END -->` (collapsed for execution; preserved for audit)
2. Prepend a new `## Execution Pack` section at the top of the file with exec-pack content
3. Append a `## Plan Normalization Record` section at the bottom recording:
   date, mode, verdict, confidence, section-map summary

### Step 11 — If `--mode launch`

Execute only the single recommended next item selected in Step 7.
- If the item references a registered skill → invoke it with appropriate arguments
- If the item is a direct file operation (read / verify / write) → execute it directly

After execution:
- Record outcome evidence in the plan or exec pack (Evidence column of the item)
- If the item maps to an open backlog entry, update the status in `backlog/HANDOFF.md`
  under "What was done this session"
- Do NOT proceed to a second item in the same skill invocation

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-91 --status completed
> ```

## Output Schema

```
PLAN-NORMALIZE VERDICT — {YYYY-MM-DD}
Plan: {plan-file}
Mode: assess | amend | launch

A. VERDICT
   execution-ready-as-is: yes | no
   confidence: high | medium | low
   key reasons:
     - {reason 1}
     - {reason 2}
   top risks:
     - {risk 1}

B. SECTION MAP
   | Section | Classification | Keep for execution |
   |---------|----------------|--------------------|
   | {title} | {class}        | yes / no           |

C. OPEN WORK REGISTER
   | ID | Title | Source section | Status | Blocker | Files likely involved | Validation method | In exec pack |
   |----|-------|----------------|--------|---------|----------------------|-------------------|-------------|

D. NEXT ITEM
   chosen: {item title or "none — no ready items"}
   why it wins: {reason}
   runner-up: {title} — not chosen because: {reason}

E. EXCLUSIONS
   completed (must not reopen): {list or "none"}
   intentionally omitted (must not build): {list or "none"}
   stale / superseded: {list or "none"}
   archive-only sections: {list or "none"}

F. AMENDED EXECUTION PACK
   (only present when --mode amend or --mode launch)
   ordered actions:
     1. {action} — validates by: {method} — evidence expectation: {what to look for}
   non-goals: {list}
```

## Non-negotiable Behavioral Rules

- Never execute a plan blindly
- Never let historical context drive live execution without re-verification
- Never reopen completed work without `contradicted` evidence of regression
- Never flatten capability maturity distinctions (spec-only ≠ implemented)
- Never select multiple "next items" when one can be chosen
- Never return only criticism; always return an execution-safe path or a clear block reason

## Postconditions

**assess**: PLAN-NORMALIZE VERDICT written to stdout; no files modified.
**amend**: Exec pack sibling created (or plan edited in-place); verdict written.
**launch**: First safe item executed; plan/backlog updated with evidence.

## Integration

This skill is the mandatory pre-execution gate when any other skill or plan references:
- A plan that is inherited, long (>4 H2 sections), or amended
- A plan last modified >7 days ago
- A plan containing postmortem, sprint, or archive sections
- A plan generated by another agent without immediate execution

Planning skills that produce long plans should reference this skill as the mandatory
pre-execution normalization step. Handoff templates should record whether the current
plan has passed this skill and whether the execution pack is current.

---

## LLM Metrics Obligation

If this skill invokes `llm.professionalize.com` directly or through `LLMRouter`,
the run carries a **metrics obligation** (METRICS-PLAN-001, `AGENTS.md §15`):

- All professionalize calls must use `ProfessionalizeClient`, `LLMRouter`, or a
  registered adapter entry in `metrics_callsite_registry.yaml`.
- Each run must capture per-call `MetricsEvent` records and aggregate them into a
  validated `MetricsRow` via `RunMetrics`.
- Default mode is **dry-run**. Live posting requires explicit owner approval and
  `AGENT_METRICS_ENDPOINT` / `AGENT_METRICS_TOKEN` set locally.
- Non-professionalize calls (Gemini, Ollama, M2M) are excluded from
  `token_usage` and `api_calls_count`.
- Metrics failures must not crash or block the parent pipeline job.
