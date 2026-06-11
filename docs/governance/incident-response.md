# Incident Response Plan

## Severity Levels

| Level | Name | Description | Response Time | Examples |
|-------|------|-------------|---------------|----------|
| SEV1 | Critical | Data loss or knowledge corruption | Immediate | Knowledge model overwritten, evidence files deleted |
| SEV2 | Major | Content corruption or incorrect publication | < 4 hours | Wrong API names in published docs, broken evidence links |
| SEV3 | Minor | Skill failure or pipeline error | < 24 hours | S-21 page-enhance fails, CI job timeout |
| SEV4 | Cosmetic | Formatting or non-functional issue | Best effort | Typo in generated page, style inconsistency |

## Escalation Paths

Tied to AGENTS.md autonomy tiers:

| Tier | Action | Who Handles |
|------|--------|-------------|
| AUTO | Automatic retry via adaptive_retry.py | Agent |
| WARN | Log warning to reports/ops.log, continue | Agent + Operator review |
| BLOCK | Halt pipeline, require operator confirmation | Operator |
| HUMAN-ONLY | Full stop, require human authority | Human maintainer |

## Recovery Procedures

### SEV1 -- Data Loss
1. Immediate: Stop all agent operations
2. Assess: Check reports/ops.log for last successful state
3. Recover: Use git reflog to find last known-good commit
4. Verify: Run S-72 (diagnose-skill-failure) to identify root cause
5. Restore: If knowledge model corrupted, re-run S-12 + S-14

### SEV2 -- Content Corruption
1. Rollback: Use S-60 (launch-rollback) to revert affected content
2. Diagnose: Run S-72 to classify failure
3. Fix: Apply targeted fix based on classification
4. Verify: Run S-25 (eval-page) on affected pages

### SEV3 -- Skill Failure
1. Retry: System attempts automatic retry via adaptive_retry.py (max 3)
2. Log: Failure recorded in reports/run_outcomes.jsonl
3. Diagnose: Operator runs S-72 with failure context
4. Route: Fix routed to appropriate skill based on diagnosis

### SEV4 -- Cosmetic
1. Log: Record in session notes
2. Fix: Address in next maintenance cycle

## Postmortem Template

After any SEV1 or SEV2 incident:
- Date, Severity, Duration
- Timeline of events
- Root cause analysis
- Remediation actions taken
- Prevention measures added
- Affected artifacts listed

## Audit Trail

All operations are logged to:
- reports/ops.log -- JSONL append-only log (via scripts/ops_log.py)
- reports/run_outcomes.jsonl -- Skill execution outcomes (via scripts/pipeline/commands/ops/run_outcome_log.py)
- reports/skill-runs/ -- Per-run skill invocation records (via scripts/pipeline/skill_run_manager.py)
