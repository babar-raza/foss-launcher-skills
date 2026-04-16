# S-10: Project Phase Store — Track Generation Phase State

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform} [get|set {phase}]`

## Purpose
Track the current generation phase for a product. Reads or writes a phase marker to `reports/phase_state.json` so that downstream skills know which stage the product is in (e.g., knowledge-bootstrap, initial-generation, maintenance, enhancement).

## Pre-conditions
1. `reports/` directory exists (create if missing)
2. Arguments contain at least `{family}` and `{platform}`

## Steps

> **Skill context gate** — run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/skill_context.py begin --skill S-10 --scope "*"
> ```


1. **Parse arguments**: Extract `{family}`, `{platform}`, and optional `[get|set {phase}]` from $ARGUMENTS.
   - If no action specified, default to `get`.

2. **Load state file**: Read `reports/phase_state.json` if it exists. Initialize as empty `{}` if missing.

3. **Get phase** (if action is `get`):
   - Look up key `"{family}/{platform}"` in the state file
   - Print current phase and timestamp, or `"none"` if not set
   - Valid phases: `bootstrap`, `scout`, `merge`, `plan`, `draft`, `review`, `enhance`, `heal`, `maintenance`, `complete`

4. **Set phase** (if action is `set {phase}`):
   - Validate that `{phase}` is one of the valid phases listed above
   - Update `reports/phase_state.json` with:
     ```json
     {
       "{family}/{platform}": {
         "phase": "{phase}",
         "updated_at": "YYYY-MM-DDTHH:MM:SS",
         "updated_by": "agent"
       }
     }
     ```
   - Write the file back

5. **Report**: Print the current phase state for the product.

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/skill_context.py end --skill S-10 --status completed
> ```

## Post-conditions
- `reports/phase_state.json` exists and is valid JSON
- If `set` was used, the product's phase is updated with a timestamp
- Phase value is one of the valid phases

## Error handling
- If an invalid phase name is given, list valid phases and abort
- If the state file is corrupted JSON, back it up and reinitialize
