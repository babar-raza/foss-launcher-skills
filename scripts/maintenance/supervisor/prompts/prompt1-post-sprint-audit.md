# POST-SPRINT STRICT EVIDENCE AUDIT, THREE-LEVEL ISSUE DISCOVERY, ROOT-CAUSE REVIEW, AND NEXT-STAGE RECOMMENDATION

> Prompt ID: PSL-P1
> Stage: 1 (Audit)
> Version: 1.0.0

## Mode

Audit mode.

- Do not execute new implementation work.
- Do not modify source files unless the project's audit system requires writing evidence artifacts.
- Do not exaggerate progress.
- Do not describe intent as achievement.
- Do not treat claims as facts.
- Do not accept summaries without evidence.
- Do not skip integration and system-connect-point review.

## Mission

Provide an evidence-based summary of what was actually achieved in the last sprint, then perform a strict manual and evidence-backed review of:

- what was completed
- what was partial
- what was unresolved
- what was not verified
- what was not proven
- what was integrated
- what was supposed to be integrated but was not
- what system weaknesses allowed gaps to happen

## Core Requirements

- Do not exaggerate progress.
- Do not describe intent as achievement.
- Separate completed work, partial work, and unresolved gaps.
- Distinguish between code changes, verified behavior, and assumptions.
- Focus on what was proven by direct evidence, not what was expected to happen.
- Identify missing proof explicitly.
- Identify root causes, not just symptoms.
- Identify integration/connect-point gaps.
- Identify system weaknesses that could cause recurrence.
- Produce both human-readable and machine-readable outputs.
- Recommend the next stage for the loop controller.

## Required Input Discovery

Locate and inspect the latest sprint evidence from available sources:

- final assistant response
- sprint summary
- evidence bundle
- declaration review package
- evidence-declaration.yaml
- evidence-manifest.yaml
- changed-file manifest
- taskcards
- taskcard index
- ledgers
- queue/state files
- continuation signals
- raw logs
- command logs
- test outputs
- validator outputs
- generated outputs
- sample outputs
- closeout report
- pilot proof
- current repository state
- relevant consumers and integration points

### If Evidence Bundle Is Missing

- Classify all dependent claims as UNVERIFIED.
- Produce an EVIDENCE_DEFECT issue.
- Recommend Prompt 2 if a plan update is required.
- Recommend Prompt 3 only if evidence repair can be executed safely from taskcards.

## Human-Readable Section A -- What We Achieved

List concrete outputs, changes, validations, and decisions completed during the sprint.

For each achievement, state:

- what changed
- where it changed
- whether it was fully done or partially done
- what evidence supports it
- whether behavior was verified
- whether it is integrated
- whether it is production-ready
- whether any caveats remain

Do not mix: code existence, behavior proof, integration proof, production readiness.

## Human-Readable Section B -- What This Proves

Explain what the sprint results actually demonstrate about the system, process, product, or plan.

Classify the level of proof:

- `implementation_only`
- `partial_validation`
- `focused_validation`
- `integration_validation`
- `end_to_end_proof`
- `pilot_proof`
- `no_proof_yet`

Identify:

- evidence-supported conclusions
- conclusions still unproven
- assumptions still being carried
- proof that is too narrow
- proof that is synthetic-only
- proof that lacks raw logs
- proof that lacks consumer/integration validation

## Human-Readable Section C -- Effect on the Final Outcome

Explain how the sprint changes the likely final outcome.

State whether it:

- reduced risk
- improved confidence
- uncovered deeper issues
- changed the execution path
- moved the project materially closer to the final goal
- exposed blockers
- revealed weak system machinery
- requires plan hardening
- requires re-execution

Also state:

- what still blocks the final outcome
- what remains unproven
- what must happen next

## Structured Issue Level L1 -- Sprint Execution Issues

Identify issues in the sprint's own execution. Include issues such as:

- missed task
- partially completed task
- incorrectly completed task
- unverified work
- unproven claim
- missing raw log
- missing validator output
- weak test
- synthetic-only test
- stale artifact
- missing evidence bundle
- missing declaration
- missing manifest
- misleading final summary
- taskcard not closed
- taskcard closed without evidence
- changed file not listed
- generated output not inspected
- commit/staging state unclear
- pilot claimed but not proven
- end-to-end claim without end-to-end evidence
- production-ready claim without production proof

## Structured Issue Level L2 -- Integration and Connect-Point Issues

Identify issues where sprint work was supposed to connect into the system. Include issues such as:

- implementation not consumed
- output not wired to downstream stage
- registry not updated
- state file stale
- queue not updated
- ledgers not updated
- docs not synchronized
- skill not synchronized
- prompt not synchronized
- schema not synchronized
- validator not synchronized
- CI/local gate not updated
- generated artifact not regenerated
- generated artifact not promoted
- downstream workflow still uses old path
- evidence exists but no consumer reads it
- taskcard exists but no executor consumes it
- plan updated but execution prompt not updated
- new script exists but is not registered
- new rule exists but is advisory only

## Structured Issue Level L3 -- System Weakness Issues

Identify deeper weaknesses that allowed the sprint to fall short. Include weaknesses such as:

- autonomous supervisor did not continue
- no loop controller
- no summary parser
- no quality scorer
- no reroute controller
- no fail-closed state
- validator too shallow
- evidence contract too weak
- taskcard schema too weak
- plan allowed prose-only work
- governance allowed early stop
- prompt allowed handoff instead of execution
- system did not require pilot proof
- system did not force downstream consumption check
- system accepted artifact existence as proof
- system accepted synthetic tests as production proof
- system did not block below-threshold quality
- system required human to choose next prompt
- system allowed "next prompt needed" as a final state

## Issue Record Schema

Every issue record must contain:

```yaml
issue_id: ""
issue_level: ""          # L1 | L2 | L3
title: ""
description: ""
evidence: ""
missing_evidence: ""
root_cause: ""
why_not_only_symptom: ""
affected_files: []
affected_components: []
affected_connection_points: []
severity: ""             # critical | high | medium | low
blocker: false
recurrence_risk: ""      # high | medium | low
required_fix_type: ""
requires_plan_update: false
requires_taskcard: false
requires_system_healing: false
requires_reexecution: false
requires_governance_change: false
requires_evidence_repair: false
recommended_next_stage: ""
acceptance_impact: ""
```

## Claim Classification Matrix

For every major sprint claim classify:

- `ACCEPTED_VERIFIED`
- `ACCEPTED_WITH_LIMITATIONS`
- `PARTIAL`
- `UNVERIFIED`
- `FAILED`
- `STALE`
- `MISLEADING`
- `DAMAGED_OR_REGRESSED`
- `EXTERNAL_BLOCKED`

## Required Prompt 1 Outputs

- `stage1-sprint-audit-summary.md`
- `stage1-achievement-proof-summary.md`
- `stage1-final-outcome-impact.md`
- `stage1-l1-execution-issues.yaml`
- `stage1-l2-integration-issues.yaml`
- `stage1-l3-system-weaknesses.yaml`
- `stage1-root-cause-map.md`
- `stage1-claim-classification-matrix.csv`
- `stage1-evidence-quality-verdict.md`
- `stage1-next-stage-recommendation.yaml`

## Evidence Quality Verdicts

- `STRONG`
- `ADEQUATE_WITH_LIMITATIONS`
- `WEAK`
- `INSUFFICIENT`
- `MISLEADING`

## Final Verdicts

- `SPRINT_ALL_GREEN_VERIFIED`
- `SPRINT_ACCEPTED_WITH_LIMITATIONS`
- `SPRINT_REQUIRES_PLAN_HARDENING`
- `SPRINT_REQUIRES_REEXECUTION`
- `SPRINT_REQUIRES_EVIDENCE_REPAIR`
- `SPRINT_BLOCKED_EXTERNAL`
- `SPRINT_SUMMARY_INSUFFICIENT`

## Next-Stage Recommendation Rules

- If all green and evidence is strong, recommend adversarial review then acceptance.
- If issues require plan changes, recommend Prompt 2.
- If only evidence packaging is missing and no plan changes are required, recommend Prompt 3 evidence repair lane.
- If execution defects remain, recommend Prompt 2 then Prompt 3.
- If sprint summary is missing or insufficient, recommend Prompt 1 rerun or evidence reconstruction.
- If true external blocker exists, recommend blocker packaging and stop.
