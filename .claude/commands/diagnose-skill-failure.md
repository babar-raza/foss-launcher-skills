<!-- CONTRACT: agent-executed
     purpose: governed diagnostic for skill/pipeline failures with structured classification
     preconditions: error message or unexpected output from a failed skill
     postcondition: failure classified (CONFIG/DATA/CODE/GOVERNANCE/REGRESSION); resolution path identified or escalated
     idempotent: yes — same failure input produces same classification and diagnostic steps
     verified: 2026-04-11
-->
---
name: diagnose-skill-failure
description: >
  Governed diagnostic procedure for skill or pipeline failures; classifies failure as CONFIG/DATA/CODE/GOVERNANCE/REGRESSION and routes to resolution or §8 escalation
args: "{skill-id} {error-summary}"
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# S-67: Diagnose Skill Failure — Governed Diagnostic Procedure

**Arguments**: $ARGUMENTS
Expected format: `{skill-id} {error-summary}` — e.g., `S-26 "audit.py FAIL on cells/python"`

## Purpose

When a registered skill fails, a pipeline script produces unexpected output, or a quality
check regresses unexpectedly, this skill provides a governed diagnostic path.

Use instead of ad hoc investigation. Produces a structured breakage report that routes to
AGENTS.md §8 escalation when the failure cannot be resolved within the skill's normal flow.

Do NOT use this skill to bypass a failing skill or skip its safety checks. The goal is to
understand the failure and fix its root cause, not to work around it.

## Pre-conditions

None. This skill can be invoked at any point when a skill or pipeline step fails.

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
|-------|-----------|---------|
| **CONFIG** | Missing file, wrong path, environment not set up | `.venv` not active; script not found |
| **DATA** | Bad input — malformed frontmatter, unknown API tokens, missing knowledge model | `model.yaml` not found; provenance block invalid |
| **CODE** | Script raises exception not related to input data | Python traceback from library; assertion error |
| **GOVERNANCE** | Forbidden path, override token missing or expired, DAR precondition not met | `override_manager.py` DENY; DAR entry missing |
| **REGRESSION** | A previously-passing check now fails after a content or code change | Grade downgraded; audit.py findings increased |

### Step 3: Run targeted diagnostics by class

**CONFIG failures:**
```bash
# Check Python environment
.venv/Scripts/python --version   # Windows
.venv/bin/python --version        # Unix

# Check script existence
ls scripts/pipeline/{failed-script}.py

# Check knowledge model
ls knowledge/{family}/{platform}/merged/model.yaml
```

**DATA failures:**
```bash
# Validate frontmatter structure
.venv/Scripts/python scripts/pipeline/validate_frontmatter.py --files {filepath}

# Check evidence block
.venv/Scripts/python scripts/pipeline/audit.py --files {filepath}

# Check for unknown API tokens
.venv/Scripts/python scripts/pipeline/attach_evidence.py --files {filepath} --dry-run
```

**CODE failures:**
```bash
# Run the script's own unit tests
PYTHONPATH=scripts/pipeline .venv/Scripts/python -m pytest scripts/pipeline/tests/ -v -k "{script-name}"

# Check for import errors
.venv/Scripts/python -c "import scripts.pipeline.{module}"
```

**GOVERNANCE failures:**
```bash
# Check override token status
.venv/Scripts/python scripts/pipeline/override_manager.py list

# Check DAR coverage
.venv/Scripts/python scripts/ci/check_dar_coverage.py

# Check skill sync parity
.venv/Scripts/python scripts/ci/sync_skills.py --check
```

**REGRESSION failures:**
```bash
# Check grade trajectory
.venv/Scripts/python scripts/pipeline/grade_writer.py --files {filepath} --check-only

# Check what changed
git diff HEAD~1 -- {filepath}
git diff HEAD~1 -- knowledge/{family}/{platform}/
```

### Step 4: Attempt resolution

For CONFIG and DATA failures: fix the configuration or input data and re-run the failed skill.

For CODE failures: run the script's unit tests to determine if this is a known bug or an
environment issue. Do not modify the script to work around the failure — that requires a
separate code change with human review.

For GOVERNANCE failures: obtain the required override token or satisfy the DAR precondition
before proceeding. Do not skip governance checks.

For REGRESSION failures: determine whether the regression is in the content (acceptable to
fix via the appropriate skill) or in the pipeline scripts (requires human review).

### Step 5: Emit breakage report

If the failure cannot be resolved via Steps 3–4, write to
`reports/skill-breakage/{date}-{skill-id}.md`:

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
```
{verbatim error output}
```

## Diagnostics run
{list of diagnostic commands and their output}

## Resolution attempted
{what was tried; why it did not resolve}

## Escalation
{RESOLVED | ESCALATED_TO_HUMAN | DEFERRED}
```

If classification is GOVERNANCE or CODE and cannot be resolved: escalate per AGENTS.md §8.
Do not continue with the original skill until the breakage is resolved.

## Post-conditions

- Failure classified into one of the five classes
- Resolution attempted for CONFIG and DATA failures
- Breakage report written to `reports/skill-breakage/` if unresolved
- Escalation routed to AGENTS.md §8 for GOVERNANCE and CODE failures

## Failure handling

| Failure | Action |
|---------|--------|
| Cannot determine class | Default to CODE; emit breakage report; escalate |
| Resolution attempt makes things worse | Revert with `git checkout -- {filepath}`; escalate |
| Skill that failed has no unit tests | Note in breakage report; escalate as CODE |
| Failure is in a forbidden-path file | Do not attempt to fix; escalate as GOVERNANCE |

## When NOT to use this skill

- When a skill completes normally but you disagree with its output (use the skill's own
  review/heal workflow instead)
- When investigating a content quality issue unrelated to skill execution (use S-25 eval-page)
- When updating a knowledge model (use S-12 knowledge-diff → S-14 knowledge-update)
