# POST-SPRINT LOOP CONTROLLER -- SUMMARY PARSING, NEXT-STAGE DECISION, REROUTE, AND ALL-GREEN ACCEPTANCE

> Prompt ID: PSL-LC
> Stage: Controller (orchestrates P1/P2/P3 cycle)
> Version: 1.0.0
> Backing script: scripts/maintenance/supervisor/loop_controller.py

## Mission

Read Prompt 1, Prompt 2, and Prompt 3 outputs. Determine the next required stage automatically. Do not ask the user which prompt to run.

## Inputs

- stage1 outputs if present
- stage2 outputs if present
- stage3 outputs if present
- evidence manifest
- taskcard index
- quality evaluations
- reroute log
- final sprint summary YAML
- final sprint summary markdown
- evidence package path
- blocker reports

## Summary Classifications

| Classification | Condition |
|---|---|
| `STRUCTURED_ALL_GREEN` | All required YAML keys present, outcome=ALL_GREEN, all scores >= threshold, evidence complete |
| `STRUCTURED_NOT_GREEN` | All required keys present, but outcome or scores fail |
| `PROSE_ONLY` | YAML parses but missing required structured keys (outcome, scores, taskcards, evidence_files) |
| `MISSING` | File absent, empty, or invalid YAML |
| `CONTRADICTORY` | outcome says ALL_GREEN but scores/taskcards disagree |
| `EVIDENCE_MISSING` | evidence_files key absent, empty, or declared files not on disk |
| `SCORES_MISSING` | scores key absent or empty dict |
| `TASKCARDS_INCOMPLETE` | taskcards key absent or entries lack status field |
| `BLOCKED_EXTERNAL` | outcome == "BLOCKED" |

## Summary Parser Rules

The parser reads `{evidence-dir}/stage3-final-sprint-summary.yaml`.

A summary is "structured" if it has ALL of:
- `outcome` key (str: ALL_GREEN / NOT_GREEN / BLOCKED)
- `scores` key (dict: dimension_name -> int 1-5)
- `taskcards` key (list of dicts, each with `id` + `status`)
- `evidence_files` key (list of str paths)

Decision tree (first match wins):
1. File missing/invalid YAML -> MISSING
2. `outcome` key absent -> PROSE_ONLY
3. `scores` key absent/empty -> SCORES_MISSING
4. `evidence_files` absent/empty/files not on disk -> EVIDENCE_MISSING
5. `taskcards` absent/incomplete -> TASKCARDS_INCOMPLETE
6. `outcome == "BLOCKED"` -> BLOCKED_EXTERNAL
7. Cross-validation fails (outcome=ALL_GREEN but scores < threshold or taskcards failed) -> CONTRADICTORY
8. All keys present + outcome=ALL_GREEN + all scores >= threshold -> STRUCTURED_ALL_GREEN
9. Otherwise -> STRUCTURED_NOT_GREEN

## Loop Decisions

| Classification | Action | next_stage |
|---|---|---|
| MISSING | RETRY | prompt1 -> prompt2 -> prompt3 |
| PROSE_ONLY | RETRY | prompt2 -> prompt3 |
| SCORES_MISSING | RETRY | quality_scoring |
| EVIDENCE_MISSING | RETRY | evidence_collection |
| TASKCARDS_INCOMPLETE | RETRY | prompt2 |
| BLOCKED_EXTERNAL | BLOCK | blocker_packaging |
| CONTRADICTORY | BLOCK | (exit with error) |
| STRUCTURED_NOT_GREEN | RETRY | prompt2 -> prompt3 |
| STRUCTURED_ALL_GREEN (evidence incomplete) | RETRY | evidence_collection |
| STRUCTURED_ALL_GREEN (scores fail) | RETRY | prompt3 (rework) |
| STRUCTURED_ALL_GREEN (all pass) | ACCEPT | adversarial_review |

### Retry Guard

If retry_count >= max_retries (default 2), action escalates from RETRY to ESCALATE.

## Invalid Final States

These states must never be accepted as terminal:

- `NEXT_PROMPT_NEEDED`
- `HUMAN_REVIEW_NEEDED_BEFORE_AGENT_REVIEW`
- `PROSE_ONLY_ACCEPTED`
- `SUMMARY_MISSING_ACCEPTED`
- `SCORE_BELOW_4_ACCEPTED`
- `EVIDENCE_PACKAGE_MISSING_ACCEPTED`
- `PLAN_UPDATED_NOT_EXECUTED`
- `EXECUTED_NOT_EVALUATED`
- `PROMPT_ASSETS_DISCONNECTED`
- `TASKCARDS_MISSING_ACCEPTED`

## Required Outputs

- `loop-summary-classification.yaml`
- `loop-decision.yaml`
- `loop-open-items.yaml`
- `loop-next-stage-inputs.md`
- `loop-final-state-verdict.md`

## CLI Usage

```bash
python scripts/maintenance/supervisor/loop_controller.py \
  --evidence-dir <path> \
  [--run-id <id>] \
  [--quality-threshold 4] \
  [--output-yaml <path>] \
  [--execute]
```

Exit codes:
- 0: decision computed successfully
- 1: fatal error
- 2: contradictory evidence (fail-closed)
