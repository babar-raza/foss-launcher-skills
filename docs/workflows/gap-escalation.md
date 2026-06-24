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

## Archive

Pre-refactor version:
[docs/_archive/pre-refactor/workflows/gap-escalation.md](../_archive/pre-refactor/workflows/gap-escalation.md)
