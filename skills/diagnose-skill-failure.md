---
name: diagnose-skill-failure
id: S-67
description: >
  Governed diagnostic procedure for skill or pipeline failures; classifies failure
  as CONFIG/DATA/CODE/GOVERNANCE/REGRESSION and routes to resolution or escalation.
args: "{skill-id} {error-summary}"
---

# S-67: Diagnose Skill Failure — Governed Diagnostic Procedure

**Arguments**: $ARGUMENTS
Expected format: `{skill-id} {error-summary}` — e.g. `S-26 "merge.py FAIL on words/python"`

## Purpose

When a registered skill fails, a pipeline script produces unexpected output, or a
quality check regresses unexpectedly, this skill provides a governed diagnostic path.

Use instead of ad hoc investigation. Produces a structured breakage report that routes
to escalation when the failure cannot be resolved within the skill's normal flow.

**Do NOT use this skill to bypass a failing skill or skip its safety checks.** The
goal is to understand the failure and fix its root cause, not to work around it.

## Pre-conditions

None. This skill can be invoked at any point when a skill or pipeline step fails.

> **Optional context gate** — if `scripts/skill_context.py` exists, run before step 1:
> ```bash
> python scripts/skill_context.py begin --skill S-67 --scope "*"
> ```

## Steps

### Step 1: Capture the failure context

Record exactly:
- Which skill failed (skill ID and name)
- Which step within the skill failed
- Exact error message or unexpected output
- The command or script that produced the error
- The input file(s) or product scope (family/platform)

### Step 2: Classify the failure type

| Class | Indicators | Example |
|---|---|---|
| **CONFIG** | Missing file, wrong path, environment not set up | Virtual environment not active; script not found |
| **DATA** | Bad input — malformed frontmatter, unknown API tokens, missing knowledge model | `model.yaml` not found; evidence block invalid |
| **CODE** | Script raises exception not related to input data | Python traceback from library; assertion error |
| **GOVERNANCE** | Forbidden path, override token missing, DAR precondition not met | path-guard DENY; required skill not invoked |
| **REGRESSION** | A previously-passing check now fails after a content or code change | Grade downgraded; more FAIL findings than before |

### Step 3: Run targeted diagnostics by class

**CONFIG failures:**
```bash
# Check Python environment
python --version
which python  # or: where python on Windows

# Check script existence
ls scripts/{failed-script}.py

# Check knowledge model
ls knowledge/{family}/{platform}/merged/model.yaml
```

**DATA failures:**
```bash
# Validate frontmatter (if validate_frontmatter.py exists)
python scripts/validate_frontmatter.py --files {filepath}

# Check evidence block (run ground-check skill S-23)
# Run S-23 (ground-check) on the file

# Inspect the malformed artifact directly
cat knowledge/{family}/{platform}/merged/model.yaml
```

**CODE failures:**
```bash
# Run the relevant unit tests
python -m pytest tests/ -v -k "{script-name}"

# Check for import errors
python -c "import scripts.{module}"
```

**GOVERNANCE failures:**
```bash
# Check which governance check denied the action
# Read the error message from path-guard or change-guard

# Check skill parity (if distribute.py supports --verify)
python tools/distribute.py --verify

# Check what write paths are allowed
cat AGENTS.md  # search for "Allowed Write Paths"
```

**REGRESSION failures:**
```bash
# Check what changed in content
git diff HEAD~1 -- {filepath}

# Check what changed in knowledge
git diff HEAD~1 -- knowledge/{family}/{platform}/

# Check what changed in scripts
git diff HEAD~1 -- scripts/
```

### Step 4: Attempt resolution

For **CONFIG** and **DATA** failures: fix the configuration or input data and re-run
the failed skill.

For **CODE** failures: run unit tests to determine if this is a known bug or an
environment issue. Do not modify the script to work around the failure — that requires
a separate code change with human review.

For **GOVERNANCE** failures: satisfy the governance precondition before proceeding.
Do not skip governance checks.

For **REGRESSION** failures: determine whether the regression is in the content
(acceptable to fix via the appropriate skill) or in the pipeline scripts (requires
human review).

### Step 5: Emit breakage report if unresolved

Write to `reports/skill-breakage/{YYYY-MM-DD}-{skill-id}.md`:

```markdown
# Skill Breakage Report

**Skill:** {skill-id} ({skill-name})
**Date:** {ISO date}
**Reported by:** {agent or human}

## Failure summary
{One sentence: what failed, where, with what input}

## Classification
{CONFIG | DATA | CODE | GOVERNANCE | REGRESSION}

## Exact error
\`\`\`
{verbatim error output}
\`\`\`

## Diagnostics run
{list of diagnostic commands and their output}

## Resolution attempted
{what was tried; why it did not resolve}

## Escalation
{RESOLVED | ESCALATED_TO_HUMAN | DEFERRED}
```

If classification is GOVERNANCE or CODE and cannot be resolved: escalate to human
review. Do not continue with the original skill until the breakage is resolved.

> **Optional context close** — if `scripts/skill_context.py` exists, run after the last step:
> ```bash
> python scripts/skill_context.py end --skill S-67 --status completed
> ```

## Post-conditions

- Failure classified into one of the five classes
- Resolution attempted for CONFIG and DATA failures
- Breakage report written to `reports/skill-breakage/` if unresolved
- Escalation routed to human review for GOVERNANCE and CODE failures

## Failure handling

| Failure | Action |
|---|---|
| Cannot determine class | Default to CODE; emit breakage report; escalate |
| Resolution attempt makes things worse | Revert with `git checkout -- {filepath}`; escalate |
| Skill that failed has no unit tests | Note in breakage report; escalate as CODE |
| Failure is in a governance-protected file | Do not attempt to fix; escalate as GOVERNANCE |

## When NOT to use this skill

- When a skill completes normally but you disagree with its output (use the skill's
  own review/heal workflow instead)
- When investigating a content quality issue unrelated to skill execution (use S-25
  eval-page)
- When updating a knowledge model (use S-12 knowledge-diff → S-14 knowledge-update)
