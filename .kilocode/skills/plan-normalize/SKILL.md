---
name: plan-normalize
id: S-96
description: >
  Execution-safe plan quality gate. Reviews and normalizes a plan file into an
  execution-safe working set by classifying sections, verifying claims against
  current repo state, and recommending the single next executable item.
args: "{plan-file} [--related {path}...] [--mode assess|amend|launch] [--in-place]"
---

# S-96: Plan Normalize — Execution-Safe Plan Quality Gate

**Arguments**: $ARGUMENTS
Expected format: `{plan-file} [--related {path}...] [--mode assess|amend|launch] [--in-place]`

## Purpose

Stop agents from executing mixed-context plans blindly. Plans accumulate historical design
context, sprint archives, completed-work records, and capability claims at various maturity
levels. An agent resuming or inheriting such a plan without normalization risks executing
stale work, re-doing completed work, or acting on outdated constraints.

**S-96 is the mandatory first step** before executing any plan that:
- Spans more than one session
- Was inherited from another operator
- Contains sprint/retrospective/postmortem sections
- Has a file mtime > 7 days with no normalization record

## Modes

| Mode | What it does |
|---|---|
| `assess` (default) | Read-only analysis; prints PLAN-NORMALIZE VERDICT to stdout; no file changes |
| `amend` | Creates an execution-pack sibling file alongside the plan with current-state sections only |
| `launch` | Assesses, amends, then executes the first safe item; updates plan with evidence |

## Steps

### Step 1: Classify plan sections

Read the full plan file and classify each section:

| Class | Criteria |
|---|---|
| `EXECUTABLE` | Pending work with current, unambiguous instructions |
| `COMPLETED` | Past work with clear done signals (dates, commit hashes, test results) |
| `HISTORICAL` | Design decisions, retrospectives, sprint archives |
| `STALE` | References artifacts, IDs, or paths that no longer exist |
| `SPECULATIVE` | Future ideas, "maybe", "consider", conditionals with no trigger |
| `BLOCKED` | Requires human input or external action before proceeding |

### Step 2: Verify claims against current repo state

For each EXECUTABLE section:
- Check that referenced files exist on disk
- Check that referenced skill IDs exist in `skills/registry.yaml`
- Check that referenced script paths exist
- Check that any mentioned test suites still pass

Mark sections with verification failures as `STALE`.

### Step 3: Identify the single next executable item

From EXECUTABLE sections, select the highest-priority item that:
- Has no unresolved dependencies
- References only verified artifacts
- Can be completed in a single session

### Step 4: Produce output

**`assess` mode** — print to stdout only:
```
PLAN-NORMALIZE VERDICT
Plan: {file}
Assessed: {ISO datetime}

Sections classified:
  EXECUTABLE:   N
  COMPLETED:    N
  HISTORICAL:   N
  STALE:        N
  SPECULATIVE:  N
  BLOCKED:      N

Verification failures:
  {list of stale references with details}

Next executable item:
  {section title / task description}
  Priority: {P0|P1|P2}
  Dependencies: {none | list}

Exclusion list (not safe to execute this session):
  {list of STALE, BLOCKED, HISTORICAL items}

Recommendation: {SAFE_TO_EXECUTE | NEEDS_CLEANUP | BLOCKED}
```

**`amend` mode** — write `{plan-file}-exec-pack.md` alongside the plan containing only EXECUTABLE sections plus the verdict block. Original plan is not modified unless `--in-place`.

**`launch` mode** — assess → amend → execute the single next item using the appropriate skill. Update plan with:
```markdown
## Plan Normalization Record
Normalized: {ISO datetime}
Next item executed: {item title}
Skill invoked: {skill-id}
Result: {PASS | FAIL}
```

## Post-conditions

- `assess`: VERDICT printed; no files modified
- `amend`: execution-pack created; original plan preserved (or amended in-place)
- `launch`: first safe item executed; plan updated with normalization record

## Triggers (when to invoke automatically)

Per AGENTS.md guidance, invoke this skill before executing any plan when:
- Plan file mtime > 7 days and no `## Plan Normalization Record` section
- Plan contains H2 sections with sprint/retrospective/postmortem keywords
- Session is inherited from another operator
