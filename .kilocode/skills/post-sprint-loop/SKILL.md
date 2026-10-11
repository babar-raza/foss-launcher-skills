---
name: post-sprint-loop
id: S-103
description: >
  Run the persisted post-sprint autonomy loop through P1 audit, P2 plan hardening, and P3 controlled execution.
args: "`[--sprint-id <id>]` (only needed on first run; auto-detected from state thereafter)"
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

<!-- CONTRACT: agent-executed
     purpose: execute the correct post-sprint review stage (P1/P2/P3) based on persisted state,
              validate outputs, classify the result, and loop until ACCEPTED, BLOCKED, or ESCALATED
     preconditions: sprint_loop.py is present; .supervisor/state/ is writable; .local/evidences/ is writable
     postcondition: sprint state advances one stage, or terminal state reached with evidence bundle
     idempotent: yes — re-running on a completed stage re-validates and re-decides without side-effects
     verified: 2026-06-15
     backing_script: scripts/maintenance/supervisor/sprint_loop.py
-->

# S-103: Post-Sprint Autonomy Loop

**Arguments**: `[--sprint-id <id>]` (only needed on first run; auto-detected from state thereafter)

Execute the next stage of the post-sprint autonomy loop based on current state.

## Purpose

Run the persisted post-sprint autonomy loop through P1 audit, P2 plan hardening, and P3 controlled execution. Validate outputs, repair common structure issues, classify the result, and advance state until ACCEPTED, BLOCKED, or ESCALATED.

## Instructions

1. First, run this command to check the current loop state:

```bash
.venv/Scripts/python scripts/maintenance/supervisor/sprint_loop.py status
```

2. Based on the state:

### If no state exists

- Ask the user for a sprint ID, or auto-generate one using today's date.
- Run:

```bash
.venv/Scripts/python scripts/maintenance/supervisor/sprint_loop.py init --sprint-id <sprint-id>
```

### If stage = P1

- Read `scripts/maintenance/supervisor/prompts/prompt1-post-sprint-audit.md`.
- Inject templates:

```bash
.venv/Scripts/python scripts/maintenance/supervisor/sprint_loop.py inject-template P1
```

- Execute the audit per the prompt instructions.
- Write all outputs to the evidence directory shown in state.
- Validate and decide:

```bash
.venv/Scripts/python scripts/maintenance/supervisor/sprint_loop.py validate P1 --repair
.venv/Scripts/python scripts/maintenance/supervisor/sprint_loop.py decide
```

### If stage = P2

- Read `scripts/maintenance/supervisor/prompts/prompt2-plan-hardening.md`.
- Inject templates:

```bash
.venv/Scripts/python scripts/maintenance/supervisor/sprint_loop.py inject-template P2
```

- Read P1 outputs from the evidence directory.
- Execute plan hardening per the prompt instructions.
- Write all outputs to the evidence directory.
- Validate and decide:

```bash
.venv/Scripts/python scripts/maintenance/supervisor/sprint_loop.py validate P2 --repair
.venv/Scripts/python scripts/maintenance/supervisor/sprint_loop.py decide
```

### If stage = P3

- Read `scripts/maintenance/supervisor/prompts/prompt3-controlled-execution.md`.
- Inject templates:

```bash
.venv/Scripts/python scripts/maintenance/supervisor/sprint_loop.py inject-template P3
```

- Read P1 and P2 outputs from the evidence directory.
- Execute controlled execution per the prompt instructions.
- Write all outputs to the evidence directory.
- Validate and decide:

```bash
.venv/Scripts/python scripts/maintenance/supervisor/sprint_loop.py validate P3 --repair
.venv/Scripts/python scripts/maintenance/supervisor/sprint_loop.py decide
```

### If stage = ACCEPTED

- Report completion.
- Run:

```bash
.venv/Scripts/python scripts/maintenance/supervisor/sprint_loop.py bundle
```

### If stage = BLOCKED

- Report the blocker details from state.
- Stop until the blocker is resolved.

### If stage = ESCALATED

- Report what failed and why.
- Stop for human intervention.

## Key Rules

- Always write outputs to the evidence directory shown in state.
- Always run `validate --repair` before `decide`.
- Never skip the validate and decide steps after producing outputs.
- If validation fails, fix the issues and re-run validation before deciding.
- Do not manually edit loop state; `decide` updates it.
