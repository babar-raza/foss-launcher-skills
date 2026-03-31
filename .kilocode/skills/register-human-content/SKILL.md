---
name: register-human-content
id: S-66
description: >
  Onboard a human-authored content page into quality and provenance systems; set auto_updatable: false, attach evidence, assign grade baseline
args: "{filepath}"
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# S-66: Register Human Content — Onboard Human-Authored Pages

**Arguments**: $ARGUMENTS

## Purpose

Onboard a human-authored content page into the automated quality and provenance systems.
Marks the page as human-authored, disables automated overwrite, attaches evidence, assigns
a quality grade baseline, and emits a registration report.

## Pre-conditions

1. Knowledge bootstrap confirmed (run `/knowledge-bootstrap {family} {platform}`)
2. `scripts/pipeline/grade_writer.py` must exist
3. `scripts/pipeline/attach_evidence.py` must be available

## Steps

### Step 1: Identify product scope
Parse `{filepath}` → `content/{site}/en/{family}/{platform}/{page}.md`
Confirm `knowledge/{family}/{platform}/merged/model.yaml` exists.

### Step 2: Set provenance to human-authored
Update frontmatter in `{filepath}`:
```yaml
provenance:
  content_origin: human-authored
  last_mechanism: human-edit
  auto_updatable: false
  reviewed: true
```

### Step 3: Attach evidence
```bash
python scripts/pipeline/attach_evidence.py --files {filepath}
```
If unknown API tokens reported: fix in page first (content defects, not pipeline errors).

### Step 4: Assign quality grade baseline
```bash
python -m scripts.pipeline.content_eval evaluate --files {filepath}
python scripts/pipeline/grade_writer.py --files {filepath}
```
If grade D or F: consider S-26 (heal-page) before finalizing.

### Step 5: Run content-check gate
```bash
python scripts/pipeline/audit.py --files {filepath}
```
FAIL = API accuracy problems; fix before proceeding.

### Step 6: Emit registration report
Write to `reports/human-content/{family}-{platform}-{slug}-{date}.json`.

## Post-conditions
- `provenance.auto_updatable: false` set
- Evidence block attached
- Grade persisted in frontmatter
- Audit passes
- Registration report written

## Failure handling
| Failure | Action |
|---------|--------|
| Knowledge model missing | Run `/knowledge-bootstrap {family} {platform}` first |
| Unknown API tokens | Fix in page; retry |
| Audit FAIL | Fix content defects first |
| Grade F with FC/PC | Escalate per §8; do not protect |
| Locale variant file | Do not register here; use translator workflow |
