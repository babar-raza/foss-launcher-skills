<!-- CONTRACT: agent-executed
     purpose: run post-sprint autonomy loop controller to classify sprint outcome and decide next stage
     preconditions: active session; evidence directory exists with stage3 outputs
     postcondition: loop decision emitted (ACCEPT / RETRY / BLOCK / ESCALATE) with evidence validation
     idempotent: yes — same evidence dir produces same classification
     verified: 2026-06-15
-->
# S-103: Sprint Loop — Post-Sprint Autonomy Loop Controller

**Arguments**: $ARGUMENTS
Expected format:
```
{evidence-dir} [--quality-threshold N] [--run-id ID]
```

| Parameter | Required | Values |
|-----------|----------|--------|
| `{evidence-dir}` | Yes | Path to directory containing `stage3-final-sprint-summary.yaml` and evidence files |
| `--quality-threshold` | No | Minimum score per dimension (1-5, default: 4) |
| `--run-id` | No | Run identifier (default: auto-generated timestamp) |

## Purpose

Replaces the manual inspect-and-decide cycle after Prompt 3 execution. Reads the stage 3
summary YAML, classifies the sprint outcome, validates the evidence bundle, checks quality
scores against threshold, and produces a loop decision.

## Pre-conditions

1. Evidence directory exists and contains `stage3-final-sprint-summary.yaml`
2. Summary YAML was produced by Prompt 3 (controlled execution)
3. Session is active

## Steps

1. **Parse** — Read `{evidence-dir}/stage3-final-sprint-summary.yaml`
2. **Classify** — Determine classification (one of 9 states):
   - `STRUCTURED_ALL_GREEN` — all keys present, outcome=ALL_GREEN, scores >= threshold
   - `STRUCTURED_NOT_GREEN` — structured but outcome or scores fail
   - `PROSE_ONLY` — YAML parses but missing required structured keys
   - `MISSING` — file absent, empty, or invalid YAML
   - `CONTRADICTORY` — outcome says ALL_GREEN but scores/taskcards disagree
   - `EVIDENCE_MISSING` — evidence_files key absent or files not on disk
   - `SCORES_MISSING` — scores key absent or empty
   - `TASKCARDS_INCOMPLETE` — taskcards key absent or entries lack status
   - `BLOCKED_EXTERNAL` — outcome == "BLOCKED"
3. **Validate evidence** — Check all declared evidence files exist on disk
4. **Check scores** — Verify all quality dimension scores >= threshold (default 4)
5. **Decide** — Map classification + checks to action:
   - `ACCEPT` — only when STRUCTURED_ALL_GREEN + evidence complete + scores pass
   - `RETRY` — re-run indicated stage(s); next_stage provided
   - `BLOCK` — contradictory evidence or external blocker (requires human)
   - `ESCALATE` — retry limit exceeded (default max: 2)
6. **Emit** — Write loop decision to `reports/supervisor/loop-decision-{run_id}.yaml`

## Post-conditions

- Loop decision YAML written to `reports/supervisor/`
- Exit code: 0 (decision computed), 1 (fatal error), 2 (contradictory evidence)
- Fail-closed: only STRUCTURED_ALL_GREEN with passing evidence + scores produces ACCEPT

## Backing Script

```
scripts/maintenance/supervisor/loop_controller.py --evidence-dir {evidence-dir} --execute
```

## Error Handling

- Missing evidence directory → exit 1 (FATAL_ERROR)
- Invalid YAML → classification MISSING → RETRY from prompt1
- Contradictory evidence → BLOCK + exit 2

## Related Assets

- Prompts: `scripts/maintenance/supervisor/prompts/prompt{1,2,3}-*.md`
- Schemas: `scripts/maintenance/supervisor/schemas/*.yaml`
- Tests: `scripts/maintenance/supervisor/tests/test_loop_controller.py`
- Registry: `scripts/maintenance/supervisor/prompts/prompt-registry.yaml`
