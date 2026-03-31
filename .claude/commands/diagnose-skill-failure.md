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

Do NOT use this skill to bypass a failing skill or skip its safety checks.

## Pre-conditions

None.

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
.venv/Scripts/python --version   # Windows
.venv/bin/python --version        # Unix
ls scripts/pipeline/{failed-script}.py
ls knowledge/{family}/{platform}/merged/model.yaml
```

**DATA failures:**
```bash
python scripts/pipeline/validate_frontmatter.py --files {filepath}
python scripts/pipeline/audit.py --files {filepath}
python scripts/pipeline/attach_evidence.py --files {filepath} --dry-run
```

**CODE failures:**
```bash
PYTHONPATH=scripts/pipeline python -m pytest scripts/pipeline/tests/ -v -k "{script-name}"
```

**GOVERNANCE failures:**
```bash
python scripts/pipeline/override_manager.py list
python scripts/ci/check_dar_coverage.py
python scripts/ci/sync_skills.py --check
```

**REGRESSION failures:**
```bash
git diff HEAD~1 -- {filepath}
git diff HEAD~1 -- knowledge/{family}/{platform}/
```

### Step 4: Attempt resolution

- CONFIG/DATA: fix the configuration or input data and re-run the failed skill
- CODE: run unit tests; do not modify scripts to work around failures
- GOVERNANCE: obtain override token or satisfy DAR precondition
- REGRESSION: determine if regression is in content (fix via skill) or pipeline scripts (escalate)

### Step 5: Emit breakage report (if unresolved)

Write to `reports/skill-breakage/{date}-{skill-id}.md`:

```markdown
# Skill Breakage Report
**Skill:** {skill-id} ({skill-name})
**Date:** {ISO date}
**Classification:** {CONFIG|DATA|CODE|GOVERNANCE|REGRESSION}

## Failure summary
## Exact error
## Diagnostics run
## Resolution attempted
## Escalation: {RESOLVED|ESCALATED_TO_HUMAN|DEFERRED}
```

If GOVERNANCE or CODE and unresolved: escalate per AGENTS.md §8.

## Post-conditions

- Failure classified
- Resolution attempted for CONFIG/DATA
- Breakage report in `reports/skill-breakage/` if unresolved
- GOVERNANCE/CODE escalated per §8

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Failure resolved; root cause identified and fixed |
| 1 | Failure unresolved; breakage report emitted; escalation required |
