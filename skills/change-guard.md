---
name: change-guard
id: S-33
description: >
  Pre-write gate that validates proposed content changes against verified
  knowledge. Rejects writes that contradict known facts.
args: "{family} {platform} \"{proposed-text}\""
---

# S-33: Change Guard — Pre-Write Knowledge Gate

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform} "{proposed-text}"`

## Purpose
Pre-write gate that validates proposed content changes against verified knowledge before they are written. Rejects writes that contradict known facts.

## Pre-conditions
1. **Knowledge bootstrap**: Run `/knowledge-bootstrap {family} {platform}` and check status:
   - `STOP:partial` → halt (see printed message)
   - Any other status (`READY`, `BOOTSTRAPPED`, `REFRESHED`, `WARN:conflicts`) → continue

## Steps

### Step 1: Run deterministic guard script

Run the Python script first to get a reproducible PASS/WARN/DENY decision:

```bash
# Inline text:
python scripts/pipeline/commands/diagnostics/change_guard.py {family} {platform} "proposed text here"

# From a file:
python scripts/pipeline/commands/diagnostics/change_guard.py {family} {platform} --file path/to/draft.md

# From stdin:
echo "proposed text" | python scripts/pipeline/commands/diagnostics/change_guard.py {family} {platform} --stdin

# JSON output:
python scripts/pipeline/commands/diagnostics/change_guard.py {family} {platform} "proposed text" --json
```

The script checks each sentence for:
- **Forbidden claim matches** (token overlap >= 0.7) -> DENY
- **API reference accuracy** (backtick refs checked against api_surface.json) -> DENY if wrong
- **Format direction consistency** (import/export claims vs formats.json) -> DENY if contradicts

Exit codes: 0 = PASS, 1 = WARN, 2 = DENY

### Step 2: Act on the decision

- **If DENY (exit code 2)**: Do NOT write the proposed content. The script identified a contradiction with verified knowledge. Fix the text to remove the contradiction, then re-run the guard.
- **If WARN (exit code 1)**: The text has no direct evidence backing but no contradiction was found. Proceed with caution — consider adding evidence citations or qualifying language.
- **If PASS (exit code 0)**: The text is consistent with verified knowledge. Safe to proceed with the write.

### Step 3: For DENY results, diagnose and fix

Review the issues list in the script output:
1. `forbidden_claim` — rewrite to avoid the forbidden claim
2. `api_reference` — fix the API reference to match the actual API surface
3. `format_direction` — correct the import/export direction claim

Re-run the guard after fixes to confirm PASS.

## Output
```
PASS: Proposed text is consistent with verified knowledge
WARN: No direct evidence found, but no contradiction detected
DENY: Proposed text contradicts known facts — must be revised
```

## Post-conditions
- Decision is logged
- DENY decisions must be resolved before content is written
