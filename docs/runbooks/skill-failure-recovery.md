# Runbook: Skill Failure Recovery

**Version:** 1.0
**Last updated:** 2026-06-11
**Severity tiers:** P1 (pipeline blocked), P2 (degraded output), P3 (non-critical)

---

## Overview

This runbook covers recovery procedures when one or more skills fail during content generation or maintenance pipelines.

---

## Diagnosis

### Step 1: Identify the failing skill

```bash
# Check the most recent run outcome log
python -c "
from scripts.pipeline.commands.ops.run_outcome_log import read_outcomes
entries = read_outcomes(last_n=20)
for e in entries:
    if e.get('status') in ('failure', 'exhausted'):
        print(e)
"
```

Or check CI logs in `.github/workflows/` for the failing job step.

### Step 2: Classify the failure

| Symptom | Likely Cause | Severity |
|---------|-------------|---------|
| `FileNotFoundError: model.yaml` | Knowledge model missing or stale | P1 |
| `ValueError: path not in allowlist` | Wrong write path specified | P2 |
| `requests.Timeout` | Network connectivity to aspose.com | P2 |
| `JSONDecodeError` | Corrupted output from previous skill | P2 |
| `ImportError: No module named transformers` | Optional ML dependencies not installed | P3 |

---

## Recovery Procedures

### RC-A: Knowledge Model Missing (P1)

**When:** Skill S-19, S-20, S-21, S-25 fail with missing `model.yaml`

```bash
# Identify missing knowledge model
ls knowledge/<family>/<platform>/

# If model.yaml missing, run knowledge workflow
python apply.py --skill S-34 --family <family> --platform <platform>
python apply.py --skill S-35 --family <family> --platform <platform>
python apply.py --skill S-14 --family <family> --platform <platform>

# Then retry the failing skill
python apply.py --skill <S-ID> --family <family> --platform <platform>
```

### RC-B: Stale Knowledge Model (P1)

**When:** `model.yaml` has `stale_since != null`

```bash
# Check stale status
python -c "
import yaml
with open('knowledge/<family>/<platform>/model.yaml') as f:
    m = yaml.safe_load(f)
print('stale_since:', m.get('stale_since'))
"

# Run stale detection and update workflow
python apply.py --skill S-12 --family <family>
python apply.py --skill S-14 --family <family> --platform <platform>
```

### RC-C: Path Guard Violation (P2)

**When:** Skill fails with `DENY: path not in allowlist`

1. Check `docs/BYPASS_REGISTRY.md` for the correct write path.
2. If the write path is legitimately needed, request an override token from a maintainer.
3. Do **not** use `ROOT_WRITE_AUTHORIZED=1` without maintainer approval.

### RC-D: Network Timeout (P2)

**When:** Skills S-39, S-34 fail with network timeouts

```bash
# Test connectivity
curl -I https://releases.aspose.com/ --max-time 10

# If network is available, retry with adaptive retry
python apply.py --skill S-39 --retry 3
```

### RC-E: Exhausted Retries (P2)

**When:** `adaptive_retry.py` reports `status: exhausted`

The fallback suggestion in the result dict identifies the next skill to try:

```python
# Check the fallback
result = retry_skill("S-21", ...)
if result["status"] == "exhausted":
    fallback = result["fallback_suggested"]  # e.g., "S-26"
    print(f"Run {fallback} instead")
```

---

## Escalation

If recovery procedures do not resolve the failure within 2 attempts:

1. Open a backlog item in `backlog/` with `severity: P1` or `P2`.
2. Check `TASK_BACKLOG.md` for known open issues related to the failing skill.
3. Ping the maintainer listed in `CODEOWNERS` for the affected path.

---

## Related Skills

- S-72 (diagnose-skill-failure) — Automated diagnostic procedure
- S-77 (evidence-repair) — Fix evidence frontmatter for blocked pages
- S-78 (manual-edit) — Operator-directed targeted content edit
