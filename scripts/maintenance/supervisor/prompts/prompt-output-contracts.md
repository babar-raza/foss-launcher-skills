# PROMPT OUTPUT CONTRACTS -- REQUIRED OUTPUTS FOR EACH STAGE

> Prompt ID: PSL-OC
> Version: 1.0.0

## Stage 1 (Prompt 1 -- Post-Sprint Audit) Required Outputs

| File | Format | Required |
|------|--------|----------|
| `stage1-sprint-audit-summary.md` | Markdown | yes |
| `stage1-achievement-proof-summary.md` | Markdown | yes |
| `stage1-final-outcome-impact.md` | Markdown | yes |
| `stage1-l1-execution-issues.yaml` | YAML (list of issue records) | yes |
| `stage1-l2-integration-issues.yaml` | YAML (list of issue records) | yes |
| `stage1-l3-system-weaknesses.yaml` | YAML (list of issue records) | yes |
| `stage1-root-cause-map.md` | Markdown | yes |
| `stage1-claim-classification-matrix.csv` | CSV | yes |
| `stage1-evidence-quality-verdict.md` | Markdown | yes |
| `stage1-next-stage-recommendation.yaml` | YAML | yes |

### stage1-next-stage-recommendation.yaml Schema

```yaml
verdict: ""              # One of the Stage 1 Final Verdicts
evidence_quality: ""     # STRONG | ADEQUATE_WITH_LIMITATIONS | WEAK | INSUFFICIENT | MISLEADING
recommended_next: ""     # prompt2 | prompt3_evidence_repair | adversarial_review | blocker_packaging | prompt1_rerun
issues_requiring_plan_update: 0
issues_requiring_reexecution: 0
issues_requiring_evidence_repair: 0
external_blockers: 0
```

## Stage 2 (Prompt 2 -- Plan Hardening) Required Outputs

| File | Format | Required |
|------|--------|----------|
| `stage2-input-interpretation.md` | Markdown | yes |
| `stage2-issues-extracted-from-stage1.md` | Markdown | yes |
| `stage2-plan-gap-analysis.md` | Markdown | yes |
| `stage2-master-plan-delta.md` | Markdown | yes |
| `stage2-enhanced-master-plan.md` | Markdown | yes |
| `stage2-taskcard-index.yaml` | YAML | yes |
| `stage2-taskcards/*.yaml` | YAML (one per taskcard) | yes |
| `stage2-execution-dag.yaml` | YAML | yes |
| `stage2-lane-ownership-map.yaml` | YAML | yes |
| `stage2-gate-model.md` | Markdown | yes |
| `stage2-verification-matrix.md` | Markdown | yes |
| `stage2-evidence-contract.md` | Markdown | yes |
| `stage2-quality-scoring-rubric.md` | Markdown | yes |
| `stage2-reroute-rules.md` | Markdown | yes |
| `stage2-anti-overclaim-rules.md` | Markdown | yes |
| `stage2-ready-for-execution-verdict.yaml` | YAML | yes |

### stage2-ready-for-execution-verdict.yaml Schema

```yaml
verdict: ""              # One of the Stage 2 Final Verdicts
taskcard_count: 0
taskcards_ready: 0
taskcards_blocked: 0
plan_context: ""         # full | partial | missing
audit_plan_match: true
```

## Stage 3 (Prompt 3 -- Controlled Execution) Required Outputs

| File | Format | Required |
|------|--------|----------|
| `stage3-preflight-state.md` | Markdown | yes |
| `stage3-execution-log.md` | Markdown | yes |
| `stage3-lane-status.yaml` | YAML | yes |
| `stage3-taskcard-status.yaml` | YAML | yes |
| `stage3-verification-results.md` | Markdown | yes |
| `stage3-quality-evaluations.yaml` | YAML | yes |
| `stage3-reroute-log.yaml` | YAML | yes |
| `stage3-evidence-manifest.yaml` | YAML | yes |
| `stage3-final-sprint-summary.yaml` | YAML | yes |
| `stage3-final-sprint-summary.md` | Markdown | yes |
| `stage3-self-review-l1-execution-issues.yaml` | YAML | yes |
| `stage3-self-review-l2-integration-issues.yaml` | YAML | yes |
| `stage3-self-review-l3-system-weaknesses.yaml` | YAML | yes |
| `declaration-review-package-<run_id>.zip` | ZIP | yes |

### stage3-final-sprint-summary.yaml Schema

```yaml
outcome: ""              # ALL_GREEN | NOT_GREEN | BLOCKED
scores:                  # dict: dimension_name -> int (1-5)
  requirement_correctness: 0
  implementation_correctness: 0
  integration_completeness: 0
  pipeline_compatibility: 0
  governance_compliance: 0
  evidence_completeness: 0
  test_coverage: 0
  validator_coverage: 0
  repeatability: 0
  idempotency: 0
  downstream_consumer_readiness: 0
  agentic_consumption_quality: 0
  rollback_safety_quality: 0
  documentation_sync_quality: 0
  production_readiness: 0
taskcards:               # list of {id, status}
  - id: ""
    status: ""           # ACCEPTED | REROUTED | BLOCKED_EXTERNAL
evidence_files: []       # list of file paths (relative to evidence dir)
retry_count: 0
verdict: ""              # One of the Stage 3 Final Verdicts
```

## Loop Controller Required Outputs

| File | Format | Required |
|------|--------|----------|
| `loop-summary-classification.yaml` | YAML | yes |
| `loop-decision.yaml` | YAML | yes |
| `loop-open-items.yaml` | YAML | yes |
| `loop-next-stage-inputs.md` | Markdown | yes |
| `loop-final-state-verdict.md` | Markdown | yes |

### loop-decision.yaml Schema

```yaml
loop_decision:
  classification: ""     # One of the 9 LoopClassification values
  action: ""             # ACCEPT | RETRY | BLOCK | ESCALATE
  reason: ""
  next_stage: ""         # prompt1 | prompt2 | prompt3 | adversarial_review | evidence_collection | quality_scoring | blocker_packaging | null
  retry_count: 0
  max_retries: 2
  evidence_dir: ""
  timestamp: ""
quality_scores: {}       # dimension -> score (if available)
evidence_bundle:
  declared: 0
  found: 0
  missing: []
warnings: []
```

## Validation Rules

1. Every required output must exist as a non-empty file.
2. Every YAML output must parse without errors.
3. Every issue record must have all required fields (see stage1-issue-model-schema.yaml).
4. Every taskcard must have all required fields (see stage2-taskcard-contract.yaml).
5. The stage3-final-sprint-summary.yaml must have all four required top-level keys.
6. Evidence files listed in evidence_files must exist on disk.
7. Scores must be integers 1-5.
8. Taskcard statuses must be valid per the taskcard state machine.
