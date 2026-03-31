---
name: knowledge-bootstrap
description: >
  Shared pre-condition gate that detects and resolves knowledge state before
  any content or validation command proceeds.
args: "{family} {platform}"
---

# Knowledge Bootstrap — Shared Pre-condition Gate

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}` — e.g. `3d python`

## Purpose

Single reusable command that detects and resolves knowledge state before any content or validation
command proceeds. Outputs a structured status line that calling commands act on.

## Output Protocol

This command always prints exactly one of the following as its final output line:

| Status | Meaning |
|---|---|
| `KNOWLEDGE: READY` | Knowledge exists, is current, and has no blocking issues |
| `KNOWLEDGE: BOOTSTRAPPED` | Was absent (first-time setup); ran /repo-scout + /truth-merge; now ready |
| `KNOWLEDGE: REFRESHED` | Was stale; ran refresh_knowledge.py; now current |
| `KNOWLEDGE: WARN:conflicts` | Has unresolved merge conflicts (listed above); proceeding with caution |
| `KNOWLEDGE: STOP:partial` | Directory exists but merged/ is missing — human action required; halted |

## Steps

1. **Parse arguments**: Extract `{family}` and `{platform}` from $ARGUMENTS.

2. **Check index.json existence**:

   a. `knowledge/{family}/{platform}/merged/index.json` **exists** → go to step 3.

   b. File **missing AND** `knowledge/{family}/{platform}/` directory **does not exist**
      (first-time setup):
      - Announce: "Knowledge not found for {family}/{platform} — running first-time bootstrap."
      - Invoke `/repo-scout {family} {platform}`
      - Invoke `/truth-merge {family} {platform}`
      - Output: `KNOWLEDGE: BOOTSTRAPPED`
      - Stop here (calling command continues from this status).

   c. File **missing BUT** `knowledge/{family}/{platform}/` directory **exists**
      (partial or interrupted state):
      - Output: `KNOWLEDGE: STOP:partial`
      - Print: "knowledge/{family}/{platform}/merged/ is missing or incomplete.
        This may indicate an interrupted bootstrap. Run /repo-scout and /truth-merge manually
        to rebuild before retrying."
      - Halt — do not proceed further.

3. **Check staleness**: Read `knowledge/{family}/{platform}/merged/model.yaml` or `index.json`:
   - If `stale_since` is not null OR `stale: true`:
     - Announce: "Knowledge for {family}/{platform} is stale — refreshing."
     - Run: `python scripts/pipeline/refresh_knowledge.py {family} {platform}`
     - Reload index.json.
     - Output: `KNOWLEDGE: REFRESHED`
     - Stop here (calling command continues from this status).

4. **Check conflicts**: Read `index.json` → `has_conflicts`:
   - If `true`:
     - Print the contents of `knowledge/{family}/{platform}/merged/merge_conflicts.md`
     - Output: `KNOWLEDGE: WARN:conflicts`
     - Stop here (calling command continues from this status).

5. **All clear**:
   - Output: `KNOWLEDGE: READY`

## How Calling Commands Use This

**Generation commands** (new-*, page-plan, page-draft) — add as pre-condition step 1:
```
1. Run `/knowledge-bootstrap {family} {platform}` and check status:
   - `STOP:partial` → halt (see printed message)
   - `REFRESHED` → STOP: "Knowledge was refreshed from upstream changes. Run /knowledge-diff
     to review what changed before generating content, then re-run this command."
   - `READY`, `BOOTSTRAPPED`, or `WARN:conflicts` → continue
```

**Validation/audit commands** (content-audit, change-guard, truth-audit, faq-generate,
batch-eval-fix, batch-remediate, cross-platform) — add as pre-condition step 1:
```
1. Run `/knowledge-bootstrap {family} {platform}` and check status:
   - `STOP:partial` → halt (see printed message)
   - Any other status (`READY`, `BOOTSTRAPPED`, `REFRESHED`, `WARN:conflicts`) → continue
```
