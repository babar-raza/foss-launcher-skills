---
name: llms-generate
id: S-LG-01
description: >
  Skill description pending
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# S-LG-01: llms-generate — Regenerate All LLMs Outputs

## Description

Regenerates all llms-output/ .txt files and llms.txt indexes for all 5 subdomains
using hierarchical mode. Produces per-page headers (Product/Platform/Page Type/Canonical URL)
and nested {family}/{platform}/llms.txt indexes alongside the flat llms.txt.

## Contract

**Backing script**: `scripts/generator/llms-generator.py`
**Mode**: hierarchical (root llms.txt + per-product llms.txt + per-page .txt)
**Output**: `llms-output/` (gitignored; deployed at build time via aspose.org-workflows)

## Steps

1. Run generator for all 5 subdomains:
   ```bash
   .venv/Scripts/python scripts/generator/llms-generator.py \
     --input content \
     --output llms-output \
     --all-subdomains \
     --mode hierarchical \
     --mapping scripts/generator/mapping.json \
     --clean-output
   ```

2. Verify outputs exist (spot-check):
   ```bash
   ls llms-output/reference.aspose.org/llms.txt
   ls llms-output/reference.aspose.org/pdf/net/llms.txt
   head -10 llms-output/kb.aspose.org/pdf/net/how-to-extract-text-dotnet.txt
   ```

3. Update provenance manifest:
   ```bash
   .venv/Scripts/python scripts/generator/detect_stale_llms.py \
     --llms-output llms-output --content content --update-manifest
   ```

## Verification

- Root llms.txt: < 200 lines per site
- Per-product llms.txt: <= 500 lines
- Per-page .txt files: start with 6-line YAML header block
- Run `/llms-stale` to confirm 0 STALE, 0 MISSING

## Idempotency

Running twice produces identical output (deterministic walk order + sorted file lists).
Verify: `find llms-output/ -name "*.txt" | sort | xargs sha256sum > /tmp/r1.sha`
then rerun and `diff /tmp/r1.sha /tmp/r2.sha` → empty diff.

## Related Skills

- `/llms-stale` — detect stale outputs after source changes
- `/llms-coverage` — audit coverage gap between content and outputs
- `/llms-fidelity` — audit content fidelity (source vs output comparison)
- `/llms-verify` — verify live HTTP endpoints after deployment

## Metrics Obligation

This skill invokes the `llms-generate` pipeline which calls LLM endpoints to produce text outputs. The run carries a **metrics obligation** (METRICS-PLAN-001, `AGENTS.md §15`):

- All LLM calls must use `LLMRouter` or a registered adapter in `metrics_callsite_registry.yaml`.
- Per-call `MetricsEvent` records must be captured and aggregated via `RunMetrics`.
- Metrics failures must not crash or block the parent pipeline job.
