---
name: llms-stale
id: S-LG-05
description: >
  Skill description pending
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# S-LG-05: llms-stale — Detect Stale LLMs Outputs

## Description

Compares source .md sha256 hashes against the provenance manifest to detect
outputs that are stale (source changed since last generation), missing (output
deleted), or newly appeared since manifest was built. Exit 1 if any issues found.

## Contract

**Backing script**: `scripts/generator/detect_stale_llms.py`
**Manifest**: `reports/agent-consumption/provenance-manifest.json` (local only, auto-managed)
**Output**: `reports/agent-consumption/stale-report.json` (local only)

## Steps

### Option A: Check only (for CI gate)

```bash
.venv/Scripts/python scripts/generator/detect_stale_llms.py --check-only
```

Exit 0 = clean. Exit 1 = stale or missing outputs detected.

### Option B: Update manifest after regeneration

```bash
.venv/Scripts/python scripts/generator/detect_stale_llms.py \
  --llms-output llms-output \
  --content content \
  --update-manifest
```

### Option C: Update + check in one pass

```bash
.venv/Scripts/python scripts/generator/detect_stale_llms.py \
  --llms-output llms-output \
  --content content \
  --update-manifest --check-only
```

## Interpreting Results

| Status | Meaning | Fix |
|--------|---------|-----|
| STALE | Source .md hash changed since manifest | Run `/llms-generate` |
| MISSING | Output .txt was deleted | Run `/llms-generate` for that domain |

## Workflow Sequence

After content changes:
1. Source .md changes → STALE detected by this skill
2. Run `/llms-generate` → outputs regenerated
3. Run this skill with `--update-manifest` → manifest updated
4. Run `--check-only` → exit 0 confirmed

## Related Skills

- `/llms-generate` — regenerate to fix stale outputs
- `/llms-coverage` — check structural presence of outputs
- `/llms-fidelity` — check content quality of outputs

## Metrics Obligation

This skill does not invoke LLM endpoints directly. No metrics obligation applies (METRICS-PLAN-001). It performs hash comparison against existing outputs only.
