# Archived Document

Archived: 2026-05-30

Reason: Superseded by the docs architecture refactor. This file is retained for history only; do not use it as current operating guidance.

Successor: See docs/README.md for the current documentation map and canonical references.

Original path: docs/_archive/root-orphans/skill-quality-gates-pre-refactor.md

---

# Skill Quality Gates

This document describes the skill quality gate system: what gates exist, when
they are mandatory, how to invoke them, and how to interpret their output.

Quality gates are skills that evaluate a precondition — a plan, a content
page, a knowledge model — before allowing a downstream action to proceed.
They exist because agents are vulnerable to executing stale, ambiguous, or
incomplete inputs blindly. Gates surface these problems before they cause
hard-to-reverse errors.

---

## Gate Inventory

| Skill | ID | When mandatory | Effect | Modes |
|-------|----|---------------|--------|-------|
| `plan-normalize` | S-91 | Before executing any plan that is inherited, stale (>7 days), or contains archive/sprint sections | Classifies each plan section, identifies open items, produces a NEXT ITEM recommendation | assess, amend, launch |
| `content-check` | S-23 | Before committing any content page edit | Audits evidence, claim IDs, and frontmatter validity | — |
| `ground-check` | S-24 | After content generation, before commit | Verifies factual grounding against knowledge model | — |

Cross-reference: `AGENTS.md §12` / [current skills reference](../../reference/skills.md) for the active skill registry summary.

### Monkeypatch compliance

Skills that generate or modify test code MUST comply with AGENTS.md §16 (Tiered
Monkeypatch Policy). T1 (path constant patching) and T2 (internal function replacement)
are banned. See §16 for required alternatives and annotation schemas.

---

## S-91 plan-normalize

### What it does

`plan-normalize` reads a plan file and produces a structured verdict that:
- classifies every H2 section into one of 7 categories
- identifies which items are open, completed, blocked, stale, or invalid
- surfaces the single most-actionable next item
- lists intentional exclusions separately so they are not confused with gaps
- amends the plan in place (if `--mode amend`) or launches the first ready item (if `--mode launch`)

The skill prevents agents from executing mixed-context plans — plans that
combine historical sprint retrospectives, completed archive sections, and
open work items in a single document — without first separating them.

### Trigger conditions

Run `/plan-normalize {plan-file}` before executing a plan when **any** of the
following are true:

| Trigger | Description |
|---------|-------------|
| Plan inherited from another agent | State may have drifted; prior agent's context is unavailable |
| Plan last modified >7 days ago | State is likely stale relative to the repo |
| Plan contains archive/sprint/postmortem H2 sections | Mixed context creates ambiguity about which items are actually open |
| Plan has >4 H2 sections with no normalization record | Large plans need explicit section classification |
| Capability maturity ambiguity | Plan marks items "ready" but they depend on spec-only or unverified capabilities |

These triggers are also detected statically by `scripts/ci/checks/check_plan_quality.py`
(see CI Static Analysis section below).

### Invocation examples

```bash
# assess mode (default): produce verdict block, no plan changes
/plan-normalize plans/my-plan.md

# assess with related context files
/plan-normalize plans/my-plan.md --related plans/design-rationale.md

# amend mode: produce verdict AND rewrite the plan with classified sections
/plan-normalize plans/my-plan.md --mode amend --in-place

# launch mode: normalize + immediately execute the first ready item
/plan-normalize plans/my-plan.md --mode launch
```

### Output schema (all modes)

Every `plan-normalize` invocation (assess, amend, launch) produces a
**PLAN-NORMALIZE VERDICT** block with six sections:

| Section | Content |
|---------|---------|
| A. VERDICT | `execution-ready-as-is: yes/no`, confidence score, blocking conditions |
| B. SECTION MAP | Table: each H2 section → classification + rationale |
| C. OPEN WORK REGISTER | Structured list of open items with status, files, validation |
| D. NEXT ITEM | Single recommended next action with full execution spec |
| E. EXCLUSIONS | Items confirmed out-of-scope or intentionally omitted |
| F. AMENDED EXECUTION PACK | Rewritten plan (amend/launch modes only) |

### Section classifications (7)

| Classification | Meaning |
|---------------|---------|
| `historical-reference` | Past events, retrospectives, sprint notes — read-only context |
| `verified-current-state` | Facts confirmed against repo state right now |
| `completed-archive` | Work that is done and merged — should not re-appear as open items |
| `open-actionable` | Work that is ready to execute in the current session |
| `operator-guidance` | Constraints, boundaries, rules set by the operator |
| `design-rationale` | Design decisions and their reasoning — not executable |
| `intentionally-omitted` | Features explicitly deferred or excluded — never to be built |

### Item statuses (6)

| Status | Meaning |
|--------|---------|
| `ready` | Fully specified, unblocked, can be executed now |
| `blocked` | Depends on an incomplete or unavailable precondition |
| `stale` | Specification refers to state that may have changed |
| `already-done-elsewhere` | Completed in a different plan or session |
| `needs-replan` | Ambiguous or underspecified — cannot be executed as written |
| `invalid-superseded` | Replaced by a newer item or decision |

### Verdict interpretation

| `execution-ready-as-is` | What it means | Action |
|------------------------|---------------|--------|
| `yes` | Plan is clean; proceed with D. NEXT ITEM | Execute the recommended item |
| `no` | One or more blocking conditions detected | Review blocking conditions in A. VERDICT; use amend mode to fix |

**Blocking conditions** (any one causes `execution-ready-as-is: no`):
- Plan contains ambiguous sections (mixed archive + open work)
- One or more open items rely on unverified or spec-only capabilities
- Next item recommendation is contradicted by other sections
- Plan has not been run through normalize since state-changing events

---

## CI Static Analysis: check_plan_quality.py

`scripts/ci/checks/check_plan_quality.py` is an advisory static analysis script that
detects plan files requiring S-91 normalization without invoking an LLM. It
runs at CI time and produces human-readable or JSON output.

```bash
# Scan a directory of plan files
python scripts/ci/checks/check_plan_quality.py plans/

# Scan a single file
python scripts/ci/checks/check_plan_quality.py plans/my-plan.md

# JSON output for tooling
python scripts/ci/checks/check_plan_quality.py plans/ --json

# Custom age threshold (default: 7 days)
python scripts/ci/checks/check_plan_quality.py plans/ --min-age-days 14
```

The script is **advisory only** — it exits 0 even when findings are present.
It is not a hard block; a human or agent must decide whether to normalize.

### Detection rules

| Rule | Label | Trigger |
|------|-------|---------|
| PQ-01 | MIXED_CONTEXT | Sprint/retrospective/postmortem H2 section alongside open-action language |
| PQ-02 | STALE_UNNORMALIZED | File last modified >N days ago with no `## Plan Normalization Record` |
| PQ-03 | COMPLETED_MIXED_WITH_OPEN | `## Completed` / `## Done` / `## Archive` alongside `## Open Work` / `## Backlog` |
| PQ-04 | MATURITY_AMBIGUITY | "spec-only" or "partially validated" alongside "ready" in the same section |
| PQ-05 | LONG_UNNORMALIZED | >4 H2 sections with no `## Plan Normalization Record` |

---

## Integration Points

| System | Where S-91 is referenced |
|--------|--------------------------|
| `AGENTS.md §3` | Mental model refresh: run `/plan-normalize` on stale or archive-containing plans at session start |
| `AGENTS.md §6` | Plan execution gate: mandatory before executing inherited or mixed plans |
| `AGENTS.md §12` | Skill registry: S-91 entry with description and invocation syntax |
| `skills/plan-normalize.md` | Canonical skill definition (authoritative) |
| `scripts/ci/checks/check_plan_quality.py` | Static CI analysis detecting normalization triggers without LLM |

---

## Adding a New Quality Gate

To add a new skill quality gate to this system:

1. Register the skill in `AGENTS.md §12` with a `gate:` annotation.
2. Add a trigger condition to `AGENTS.md §6` (the plan execution gate section).
3. Add a row to the Gate Inventory table in this document.
4. If the gate can be approximated statically, add a rule to `check_plan_quality.py`.
5. If the gate runs at session start, add a sub-step to `skills/session-start.md` Step 6.
