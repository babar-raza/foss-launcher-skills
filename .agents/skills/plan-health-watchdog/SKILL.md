---
name: plan-health-watchdog
id: S-113
description: >
  Detect stalled P0 work and doc claims contradicted by repo state by querying the structured taskcard store (schema 5f) and running the plan-markdown parity check — the detector that would have caught dazzling-strolling-shell's silent abandonment.
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# S-113: Plan Health Watchdog — Structured Stall Detection

<!-- CONTRACT
purpose: Detect stalled P0 taskcards and plan-prose that contradicts the structured store, via field comparison not prose scanning
inputs: reports/plan_state/{mission_id}/taskcards.jsonl (schema 5f); the plan markdown; a staleness threshold (business days)
outputs: a stall report (tasks past threshold in non-terminal status) + parity result (markdown vs store contradictions)
preconditions:
  - a taskcards.jsonl exists for the mission (schema 5f); if absent, the mission is untracked — flag that itself
postcondition: stalled/contradicted tasks surfaced with recorded_at ages; exit non-zero on contradiction
forbidden_paths: read-only; never edits the plan, taskcards, or content
deterministic_or_llm: deterministic detection; optional LLM-assisted "does this doc claim still hold" judgment (must cite evidence)
idempotent: yes (read-only)
evidence: the stall report; check_taskcard_plan_parity output
stop_conditions: a P0 task past the staleness threshold, or a markdown-vs-store contradiction
downstream: backlog (files a stall item); plan-normalize (S-91)
verified: '2026-07-17'
-->

## Purpose

Make "is this plan's prose still true, and is any P0 silently stuck?" a machine-checkable question.
`dazzling-strolling-shell` failed because `TC-W11-001.C7: TODO` lived only as prose nothing scanned;
it drifted 5+ days before a silent revert (plan §2.5 SW-4). This watchdog queries the **structured**
`taskcards.jsonl` (schema 5f) `recorded_at`/`status` fields — a reliable field comparison, not a
fragile regex over markdown that a future session's phrasing could defeat.

## When to use

- At session start, and before any *new* plan claims a problem space an existing plan still owns.
- Periodically (nightly) to surface P0 tasks that have gone quiet.

## Steps

1. **Parity — does the plan prose contradict the store?**
   ```bash
   .venv/Scripts/python scripts/ci/checks/check_taskcard_plan_parity.py --plan-file <plan.md> \
     --taskcards reports/plan_state/<mission>/taskcards.jsonl
   ```
   Exit 1 on any contradiction (markdown claims DONE while the store says TODO, or vice versa).
   Silence in the markdown is not a contradiction (the store is the source of truth).

2. **Stall query — any non-terminal task past the threshold?**
   For each row, compare `recorded_at` against a staleness threshold (default 5 business days); flag
   any whose `status` is not terminal (CLOSED / *_VERIFIED / PILOT_PROVEN / INDEPENDENTLY_REVIEWED /
   SUPERSEDED / OUT_OF_SCOPE). A P0 stuck at the same status past the threshold is the target signal.

3. **Optional judgment**: for a doc claiming a fix is "live", an LLM may confirm whether repo state
   still supports the claim — but it MUST cite the file/line evidence, never assert unsupported.

## Output

- A stall report: task_id, status, `recorded_at` age, evidence_refs.
- The parity verdict (contradictions, if any).

## Notes

- Backing artifacts: `reports/plan_state/{mission_id}/taskcards.jsonl` (schema 5f,
  `validate_taskcard_record`), `scripts/ci/checks/check_taskcard_plan_parity.py` (RPR-G-04).
- A status past IMPLEMENTED with empty `evidence_refs` is itself a schema violation — evidence-free
  progress claims cannot be recorded, closing the exact drift this skill watches for.

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
