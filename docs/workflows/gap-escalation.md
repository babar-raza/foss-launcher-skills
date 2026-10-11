# Capability Classification and Gap Escalation

> Source: AGENTS.md §6b
> Status: Current (restored from archive 2026-06-24)
> Override token: 20260624-113217-docs-workflows-mental-model-refresh-md

Before starting any task not covered by a single registered skill, classify your capability level:

## Capability States

| State | Definition | Required action |
|-------|-----------|----------------|
| **FULL** | Every step covered by a registered skill | Invoke the skill chain; no gap report needed |
| **PARTIAL** | Some steps covered, others not | Execute skill-covered steps; produce gap escalation for uncovered steps; do not perform uncovered steps via ad hoc work |
| **NONE** | No registered skill covers this requirement | Do not start work; produce gap escalation report immediately; await human decision |
| **BROKEN** | Required skill exists but fails | Capture failure output; produce breakage report; do not bypass; await human decision |

## Classification Output Template

```
CAPABILITY ASSESSMENT — {brief task description}
State: FULL | PARTIAL | NONE | BROKEN
Skill(s) covering this task: [list skill IDs, or "none"]
Gap (if PARTIAL or NONE): [describe what is not covered]
Planned action: [what you will do next]
```

For direct invocations of a single registered skill, this output is implicit.

## Gap Escalation Report

When state is PARTIAL or NONE, save to `reports/skill-gaps/{YYYY-MM-DD}-{task-slug}.md`:

```
SKILL GAP ESCALATION
Task: {what was requested}
Capability state: PARTIAL | NONE
Skills invoked (completed): [list]
Uncovered requirement: {precise description}
Impact: {what the user won't get until this gap is filled}

ENHANCEMENT PLAN
  Title: {short name for the missing skill}
  Proposed skill ID: {next S-xx}
  Input: {what the skill would receive}
  Output: {what the skill would produce}
  Skill file: .claude/commands/{proposed-name}.md
  Estimated complexity: LOW | MEDIUM | HIGH
  Workaround: YES | NO
```

## Disposition: where a NONE/BROKEN gap actually belongs

Before writing `ENHANCEMENT PLAN`, classify disposition and record it in
`reports/skill-gaps/index.yaml`. Only `recurring-candidate` may propose a new
skill ID.

| Disposition | Test | Destination |
|---|---|---|
| `broken-dependency` | An existing registered skill fails because *something it depends on* (a hook, a script, a gate) has a bug — the skill's own contract is fine | Fix the dependency directly; `Proposed skill ID: n/a` |
| `constitutionally-excluded` | The target file/domain is declared human-authority-only (e.g. AGENTS.md's own routing table) or otherwise explicitly outside the skill-automation model | Direct human-authored edit; no skill/script by design |
| `operator-infra-script` | A single-purpose, run-once-or-occasionally script would fully resolve this, and it is not meant to be invoked by a skill chain or CI step | `scripts/maintenance/registry.yaml` (see its own header comment for the one-shot/repair/migration distinction) |
| `bounded-oneoff` | A small, first-occurrence, bounded code/config patch — no durable, repeatable artifact needed | `skill_context.py gap` |
| `recurring-candidate` | The deliverable is repeatable/parameterizable and produces a report artifact on every future invocation, AND (complexity is MEDIUM+ OR the same domain tag has ≥2 prior `index.yaml` entries) | Propose a new skill, following the S-93 repo-patrol shape |

This does not change the escalation protocol itself: every PARTIAL/NONE/BROKEN
state still produces a written report and awaits human decision. This section
disambiguates what that decision should be, and where it should be recorded.

A `bounded-oneoff` item (or any plan-mode file) that is later **resumed in a
different session** and is still open has, by that point, become a multi-session
plan whether or not it was scoped as one — see "Retroactive mission registration"
in [docs/governance/planning-methodology.md](../governance/planning-methodology.md)
for the trigger and the registration step. This is the gap that let the 2026-08-31
stale-guard campaign run its entire multi-day execution unregistered until asked
to converge (`MT058`).

Background and worked examples (the 5 repo-meta gap reports read against this
rubric, and 4 worked `index.yaml` entries): see
`reports/skill-gaps/2026-08-17-gap-escalation-disposition-schema.md` and
`reports/skill-gaps/index.yaml`.

## Archive

Pre-refactor version:
[docs/_archive/pre-refactor/workflows/gap-escalation.md](../_archive/pre-refactor/workflows/gap-escalation.md)
