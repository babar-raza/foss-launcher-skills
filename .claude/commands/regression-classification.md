---
name: regression-classification
id: S-114
description: >
  Classify every grade regression in a refresh as JUSTIFIED or UNJUSTIFIED with a cited evidence source, writing the complete input list (never a sample) so the classification cannot be silently lost.
---

> Cross-skill references like `/content-eval` refer to sibling skills in this directory.

# S-114: Regression Classification — Cited JUSTIFIED/UNJUSTIFIED Verdicts

<!-- CONTRACT
purpose: For each grade delta in a refresh, classify JUSTIFIED (legitimate) vs UNJUSTIFIED (pipeline-defect regression) with a citation
inputs: a product/platform set; current grades (content_eval, read-only) + a prior grade baseline
outputs: reports/regression_classification/*.json — a COMPLETE, durably-persisted list, one verdict + citation per item
preconditions:
  - content_eval is available (deterministic, rule-based grading — no LLM in grading itself)
postcondition: every input item is written with a verdict and a cited grade_reason; UNJUSTIFIED items route to remediation
forbidden_paths: read-only classification; never edits pages (use --write-grade elsewhere, not here); routes remediation through the governed chain
deterministic_or_llm: hybrid — deterministic evidence gathering; LLM-assisted judgment MUST cite its evidence
idempotent: yes (read-only; re-running reproduces the same list from the same grades)
evidence: the classification JSON (with citation_grade_reasons per item)
stop_conditions: an item that cannot be classified with a citation escalates to human governance review
downstream: page-update/body-refresh (remediate UNJUSTIFIED); backlog (one item per UNJUSTIFIED)
verified: '2026-07-17'
-->

## Purpose

Formalize "classify a grade regression as JUSTIFIED/UNJUSTIFIED with a cited evidence source" as a
repeatable skill. Generalizes what `TC-W11-001.C7` needed. **Design rule (why the original 74-item
list was lost): always write EVERY input item to the output file, never a representative sample** —
non-persistence is what let the original snapshot become unrecoverable (plan RPR-A-01 design note).

## When to use

- After any refresh that produces a grade delta on existing pages.
- To reconcile an inherited, unrecoverable regression snapshot with a fresh, complete comparison.

## Steps

1. **Gather current grades (read-only)**:
   ```bash
   PYTHONPATH="scripts/pipeline;scripts/pipeline/lib" .venv/Scripts/python -m content_eval \
     grade-summary --product {family} {platform} --json
   ```
   Do **not** use `--write-grade` here (that mutates frontmatter; classification is read-only).

2. **Compare against a prior baseline**: diff current grades against each page's prior grade
   (frontmatter history / `evidence.model_sha`-matched git history). Where the prior state has
   moved and is unrecoverable, treat the current low-grade set as the actionable universe and say so.

3. **Classify each item with a citation**: JUSTIFIED = the grade legitimately reflects current
   evidence; UNJUSTIFIED = the drop is attributable to a pipeline defect (e.g. dead-fallback
   templated prose, evidence-thinning). Cite the `content_eval` `grade_reasons` category driving the
   grade. `consumer_usefulness`-driven C grades on hand/LLM prose are UNJUSTIFIED_CANDIDATE
   (remediable by re-running through the fixed body-refresh engine).

4. **Persist the COMPLETE list** to `reports/regression_classification/<name>.json` and file one
   backlog item per UNJUSTIFIED entry. Reference pages (deterministic batch_reference path) are a
   separate S-62 concern — classify them as a group, not folded into body-refresh remediation.

## Output

- `reports/regression_classification/*.json` — complete, one verdict + citation per input item.

## Notes

- `content_eval` grading is 100% deterministic (no LLM) — the classification's non-determinism, if
  any, is confined to the optional judgment step, which must cite evidence.
- Real example: RPR-A-01 fresh comparison found 0 D/F grades and 5 `consumer_usefulness`-driven C
  pages — see `reports/regression_classification/RPR-A-01-fresh-regression-classification.json`.

## LLM Metrics Obligation

If this skill invokes `llm.professionalize.com` directly or through `LLMRouter`,
the run carries a **metrics obligation** (METRICS-PLAN-001, `AGENTS.md §15`):

- All professionalize calls must use `ProfessionalizeClient`, `LLMRouter`, or a
  registered adapter entry in `metrics_callsite_registry.yaml`.
- Each run must capture per-call `MetricsEvent` records and aggregate them into a
  validated `MetricsRow` via `RunMetrics`.
- Default mode is **dry-run**. Live posting requires explicit owner approval and
  `AGENT_METRICS_ENDPOINT` / `AGENT_METRICS_TOKEN` set locally.
- Non-professionalize calls (Gemini, Ollama, M2M) are excluded from
  `token_usage` and `api_calls_count`.
- Metrics failures must not crash or block the parent pipeline job.
