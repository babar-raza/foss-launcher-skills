<!-- CONTRACT: agent-executed
     purpose: execute the correct post-sprint review stage (P1/P2/P3) based on persisted state,
              validate outputs, classify the result, and loop until ACCEPTED, BLOCKED, or ESCALATED
     preconditions: sprint_loop.py is present; .supervisor/state/ is writable; .local/evidences/ is writable
     postcondition: sprint state advances one stage, or terminal state reached with evidence bundle
     idempotent: yes — re-running on a completed stage re-validates and re-decides without side-effects
     verified: 2026-06-15
     backing_script: scripts/maintenance/supervisor/sprint_loop.py
-->
---
name: post-sprint-loop
id: S-103
description: >
  Post-sprint autonomy loop. Reads persisted loop state, injects templates for the current
  stage (P1/P2/P3), executes the appropriate prompt, validates outputs (with auto-repair),
  classifies the result via loop_controller, and advances state. Loops until ACCEPTED,
  BLOCKED, or ESCALATED. Replaces manual Prompt 1 → 2 → 3 handoff.
args: "[--sprint-id <id>]"
---

# S-103: Post-Sprint Autonomy Loop

**Arguments**: `[--sprint-id <id>]` (only needed on first run; auto-detected from state thereafter)

Execute the next stage of the post-sprint autonomy loop based on current state.

## Instructions

1. First, run this command to check the current loop state:
```
.venv/Scripts/python scripts/maintenance/supervisor/sprint_loop.py status
```

2. Based on the state:

### If no state exists (first run):
- Ask the user for a sprint ID, or auto-generate one using today's date
- Run: `.venv/Scripts/python scripts/maintenance/supervisor/sprint_loop.py init --sprint-id <sprint-id>`

### If stage = P1 (Post-Sprint Audit):
- Read the prompt file: `scripts/maintenance/supervisor/prompts/prompt1-post-sprint-audit.md`
- Inject templates: `.venv/Scripts/python scripts/maintenance/supervisor/sprint_loop.py inject-template P1`
- Execute the audit per the prompt instructions
- Write ALL outputs to the evidence directory shown in state
- After completion, validate and decide:
  ```
  .venv/Scripts/python scripts/maintenance/supervisor/sprint_loop.py validate P1 --repair
  .venv/Scripts/python scripts/maintenance/supervisor/sprint_loop.py decide
  ```

### If stage = P2 (Plan Hardening):
- Read the prompt file: `scripts/maintenance/supervisor/prompts/prompt2-plan-hardening.md`
- Inject templates: `.venv/Scripts/python scripts/maintenance/supervisor/sprint_loop.py inject-template P2`
- Read the stage 1 outputs from the evidence directory for context
- Execute the plan hardening per the prompt instructions
- Write ALL outputs to the evidence directory
- After completion, validate and decide:
  ```
  .venv/Scripts/python scripts/maintenance/supervisor/sprint_loop.py validate P2 --repair
  .venv/Scripts/python scripts/maintenance/supervisor/sprint_loop.py decide
  ```

### If stage = P3 (Controlled Execution):
- Read the prompt file: `scripts/maintenance/supervisor/prompts/prompt3-controlled-execution.md`
- Inject templates: `.venv/Scripts/python scripts/maintenance/supervisor/sprint_loop.py inject-template P3`
- Read the stage 1 and stage 2 outputs from the evidence directory for context
- Execute the controlled execution per the prompt instructions
- Write ALL outputs to the evidence directory
- After completion, validate and decide:
  ```
  .venv/Scripts/python scripts/maintenance/supervisor/sprint_loop.py validate P3 --repair
  .venv/Scripts/python scripts/maintenance/supervisor/sprint_loop.py decide
  ```

### If stage = ACCEPTED:
- The loop is complete. Report success.
- Run: `.venv/Scripts/python scripts/maintenance/supervisor/sprint_loop.py bundle`

### If stage = BLOCKED:
- Report the blocker details from the state file
- The loop cannot proceed until the blocker is resolved

### If stage = ESCALATED:
- The loop has exhausted retries. Report what failed and why.
- Human intervention is required.

## Key Rules
- ALWAYS write outputs to the evidence directory (shown in state, under `.local/evidences/<sprint-id>/`)
- ALWAYS run `validate --repair` before `decide` to catch and fix common output issues
- NEVER skip the validate+decide step after producing outputs
- If validate fails, fix the issues and re-run validate before decide
- The decide step updates state automatically — do not manually edit the state file
