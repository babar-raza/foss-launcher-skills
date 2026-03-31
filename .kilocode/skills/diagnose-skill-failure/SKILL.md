---
name: diagnose-skill-failure
id: S-67
description: >
  Governed diagnostic procedure for skill or pipeline failures; classifies failure as CONFIG/DATA/CODE/GOVERNANCE/REGRESSION and routes to resolution or §8 escalation
args: "{skill-id} {error-summary}"
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# S-67: Diagnose Skill Failure — Governed Diagnostic Procedure

**Arguments**: $ARGUMENTS

## Purpose

Provides a governed diagnostic path when a registered skill fails or a pipeline step
produces unexpected output. Classifies the failure and routes to resolution or escalation.

Do NOT use to bypass a failing skill or skip safety checks.

## Pre-conditions

None.

## Steps

### Step 1: Capture failure context
Record: skill ID, failed step, exact error, command/script, input scope.

### Step 2: Classify failure type

| Class | Indicators |
|-------|-----------|
| CONFIG | Missing file, wrong path, env not set up |
| DATA | Malformed frontmatter, unknown API tokens, missing model |
| CODE | Python traceback unrelated to input data |
| GOVERNANCE | Forbidden path, override token missing, DAR not met |
| REGRESSION | Previously-passing check now fails |

### Step 3: Run targeted diagnostics by class

**CONFIG:** Check `.venv`, script existence, `knowledge/{family}/{platform}/merged/model.yaml`

**DATA:**
```bash
python scripts/pipeline/validate_frontmatter.py --files {filepath}
python scripts/pipeline/audit.py --files {filepath}
python scripts/pipeline/attach_evidence.py --files {filepath} --dry-run
```

**CODE:**
```bash
PYTHONPATH=scripts/pipeline python -m pytest scripts/pipeline/tests/ -v -k "{script-name}"
```

**GOVERNANCE:**
```bash
python scripts/pipeline/override_manager.py list
python scripts/ci/check_dar_coverage.py
python scripts/ci/sync_skills.py --check
```

**REGRESSION:**
```bash
git diff HEAD~1 -- {filepath}
git diff HEAD~1 -- knowledge/{family}/{platform}/
```

### Step 4: Attempt resolution
CONFIG/DATA: fix input and re-run. CODE: run unit tests; do not modify scripts. GOVERNANCE: obtain token or satisfy DAR. REGRESSION: fix in content via appropriate skill.

### Step 5: Emit breakage report (if unresolved)
Write to `reports/skill-breakage/{date}-{skill-id}.md` with: failure summary, classification, exact error, diagnostics run, resolution attempted, escalation status.

If GOVERNANCE or CODE and unresolved: escalate per AGENTS.md §8.

## Post-conditions
- Failure classified
- Resolution attempted for CONFIG/DATA
- Breakage report written if unresolved
- GOVERNANCE/CODE escalated per §8
