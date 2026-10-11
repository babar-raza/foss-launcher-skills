# S-112: Triage Verdict Gate — Deterministic Commit Precondition

<!-- CONTRACT
purpose: Real CLI + exit code over triage findings; a hard precondition for S-76 commit and post_refresh_verify Check 9
inputs: family, platform (+ optional --files); reads knowledge artifacts and page bodies
outputs: reports/refresh_state/{family}/{platform}/triage_verdict.yaml; exit 0 (clean) / 1 (stale prose, BLOCK) / 2 (knowledge absent, non-blocking SKIP)
preconditions:
  - knowledge/{family}/{platform}/merged/ present for a meaningful verdict (else exit 2 SKIP)
postcondition: triage_verdict.yaml written; a CONFIRMED verdict (or explicit human override) required before commit
forbidden_paths: read-only over content; never edits pages, evidence, or knowledge
deterministic_or_llm: fully deterministic (no LLM)
idempotent: yes (read-only)
evidence: triage_verdict.yaml; post_refresh_verify Check 9 output
stop_conditions: exit 1 (stale prose references to modified/removed APIs) blocks the commit
downstream: S-76 commit (gated); post_refresh_verify --verify Check 9
verified: '2026-07-17'
-->

## Purpose

Turn S-92 triage-confirm's findings into a real, blocking gate. Before RPR-F-03 the backing files
had **no CLI at all** — the documented invocation silently no-op'd and exited 0 (plan §2.3). This
skill owns the deterministic verdict and its exit code; S-92 `triage-confirm` remains the
agent-facing wrapper that interprets it.

## When to use

- As the final quality precondition before `S-76 commit` on any refresh.
- Automatically, as Check 9 inside `post_refresh_verify.py --verify`.

## Steps

1. **Run the gate**:
   ```bash
   PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/lib/triage_confirm.py {family} {platform} [--files ...] [--json]
   ```
   Exit 0 = clean; exit 1 = stale prose references to modified/removed APIs (BLOCK); exit 2 =
   knowledge artifacts absent (non-blocking SKIP).

2. **Read the verdict**: `reports/refresh_state/{family}/{platform}/triage_verdict.yaml`.

3. **Gate the commit**: `S-76 commit` may proceed only on a CONFIRMED verdict or an explicit,
   logged human override. `post_refresh_verify.py --verify` invokes this as Check 9 and BLOCKs on
   exit 1 (mirrors the Check 4 / stale_detect subprocess pattern).

## Output

- `reports/refresh_state/{family}/{platform}/triage_verdict.yaml` — the machine-readable verdict.
- A non-zero exit code that a caller (commit gate, `--verify`) treats as blocking.

## Notes

- Backing code: `scripts/pipeline/lib/triage_confirm.py`, `reconcile_triage.py` (both now have real
  `argparse`/`__main__`), wired into `post_refresh_verify.py` Check 9 (RPR-F-03).
- `reconcile_triage.py` wires 2 of 3 reconciliation sources via CLI; the `page_spec` dimension
  remains available via direct library call (documented simplification).
- Distinct from S-92: S-92 is the agent wrapper; S-112 is the deterministic exit-code enforcement.

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
