# S-72: Diagnose Skill Failure — Governed Diagnostic Procedure

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
| **CONFIG** | Missing file, wrong path, environment not set up | Python not found; script not found; `CONTENT_REPO_PATH` unset |
| **DATA** | Bad input — malformed frontmatter, unknown API tokens, missing knowledge model | `model.yaml` not found; evidence block invalid |
| **CODE** | Script raises exception not related to input data | Python traceback from library; assertion error |
| **GOVERNANCE** | Forbidden path, missing registry entry, internal skill invoked directly | `path-guard` DENY; skill not in registry |
| **REGRESSION** | A previously-passing check now fails after a content or code change | Grade downgraded; audit.py findings increased |

### Step 3: Run targeted diagnostics by class

**CONFIG failures:**
```bash
# Check Python version
python --version

# Check script existence
ls scripts/pipeline/{failed-script}.py

# Check knowledge model
ls knowledge/{family}/{platform}/merged/model.yaml

# Check CONTENT_REPO_PATH is set
python scripts/check_setup.py
```

**DATA failures:**
```bash
# Check evidence block
python scripts/pipeline/commands/content/audit.py --files {filepath}

# Validate frontmatter structure
python -c "import yaml; yaml.safe_load(open('{filepath}').read())"
```

**CODE failures:**
```bash
# Run the script's own unit tests
python -m pytest tests/ -v -k "{script-name}"

# Check for import errors
python -c "import scripts.pipeline.{module}"
```

**GOVERNANCE failures:**
```bash
# Check skill registry
python scripts/validate_skills.py

# Check sync status
python scripts/sync_commands.py --check
python scripts/sync_agents.py --check
```

**REGRESSION failures:**
```bash
# Check what changed
git diff HEAD~1 -- {filepath}
git diff HEAD~1 -- knowledge/{family}/{platform}/

# Re-run eval
python scripts/pipeline/content_eval/__main__.py --files {filepath}
```

### Step 4: Attempt resolution

For CONFIG and DATA failures: fix the configuration or input data and re-run the failed skill.

For CODE failures: run the script's unit tests to determine if this is a known bug or an
environment issue. Do not modify the script to work around the failure — that requires a
separate code change with human review.

For GOVERNANCE failures: satisfy the registry/sync/path-guard precondition before proceeding.
Do not skip governance checks.

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
{verbatim error output}

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
