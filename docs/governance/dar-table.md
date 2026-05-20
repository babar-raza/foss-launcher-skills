# Dependency Activation Rule (DAR) Table — foss-launcher

**Source**: Adapted from aspose.org `docs/governance/dar-table.md`
**Adapted**: 2026-05-15 (PAR-013 GV-005)
**IDs**: foss-launcher IDs (see `docs/id-mapping.md` for aspose.org cross-reference)

---

## Skill-First Execution Mandate

Every agent must treat the skill system as the **default and required** execution mechanism.

1. **Before starting any task**, identify which registered skill(s) in `skills/registry.yaml` cover it.
2. **Invoke matching skills** in defined order. Do not perform equivalent work through inline reasoning.
3. **Activate upstream dependencies automatically.** If a skill requires a precondition, invoke it first.
4. **Do not invent workflows.** If no skill covers the requirement, file a gap escalation report.

## Dependency Activation Rule (DAR) Table

Agents must activate the upstream skill if it has not already been confirmed as passing in
the current session. "Passing" means: non-STOP status returned in this conversation, no
knowledge-modifying skill has run since, and less than one hour has elapsed.

| Downstream skill | Required upstream | Trigger condition |
|-----------------|------------------|------------------|
| `/page-plan` (S-18) | S-49 `/knowledge-bootstrap` | Always |
| `/page-draft` (S-19) | S-49 `/knowledge-bootstrap` | Always |
| `/page-draft` (S-19) | S-18 `/page-plan` | Plan not in session context |
| `/page-update` (S-20) | S-12 `/knowledge-diff` + S-14 `/knowledge-update` | `stale_since` not null |
| `/page-enhance` (S-21) | S-25 `/eval-page` or S-17 `/rubric-align` | Eval not in session context |
| `/heal-page` (S-26) | S-25 `/eval-page` | Eval not in session context |
| `/ground-check` (S-23) | S-49 `/knowledge-bootstrap` | Always |
| `/truth-merge` (S-35) | S-34 `/repo-scout` | Scout output absent |
| `/batch-remediate` (S-40) | S-49 `/knowledge-bootstrap` | Always |
| `/batch-eval-fix` (S-41) | S-49 `/knowledge-bootstrap` | Always |
| `/faq-generate` (S-22) | S-49 `/knowledge-bootstrap` | Always |
| `/new-docs-page` (S-51) | S-49 `/knowledge-bootstrap` | Always |
| `/new-blog-post` (S-52) | S-49 `/knowledge-bootstrap` | Always |
| `/new-kb-howto` (S-53) | S-49 `/knowledge-bootstrap` | Always |
| `/new-kb-faq` (S-54) | S-49 `/knowledge-bootstrap` | Always |
| `/new-reference-page` (S-55) | S-49 `/knowledge-bootstrap` | Always |
| `/new-products-page` (S-66) | S-49 `/knowledge-bootstrap` | Always |
| `/batch-reference` (S-67) | S-49 `/knowledge-bootstrap` | Always |
| `/change-guard` (S-33) | S-49 `/knowledge-bootstrap` | Always |
| `/content-audit` (S-32) | S-49 `/knowledge-bootstrap` | Always |
| `/site-plan` (S-57) | S-49 `/knowledge-bootstrap` | Always |
| `/family-sync` (S-58) | S-49 `/knowledge-bootstrap` | Always |
| `/launch-product` (S-38) | S-57 `/site-plan` | Always (produces slug manifest) |
| `/gap-apply` (S-65) | S-63 `/gap-plan` | Plan not in session context |
| `/new-docs-index` (S-75) | S-49 `/knowledge-bootstrap` | Always |
| `/new-kb-index` (S-74) | S-49 `/knowledge-bootstrap` | Always |
| `/new-reference-index` (S-76) | S-49 `/knowledge-bootstrap` | Always |
| `/register-human-content` (S-71) | S-49 `/knowledge-bootstrap` | Always |
| `/evidence-repair` (S-77) | S-12 `/knowledge-diff` + S-14 `/knowledge-update` | `stale_since` not null |
| `/manual-edit` (S-78) | S-12 `/knowledge-diff` + S-14 `/knowledge-update` | `stale_since` not null |
| `/evidence-enhance` (S-83) | S-12 `/knowledge-diff` + S-14 `/knowledge-update` | `stale_since` not null |
| `/delta-site-plan` (S-87) | S-14 `/knowledge-update` | Always (knowledge_delta.json must exist) |
| `/page-retire` (S-88) | S-87 `/delta-site-plan` | When retiring from plan |
| `/refresh-product` (S-84) | S-12 `/knowledge-diff` | Always (auto-invokes S-14, S-87, S-88 in sequence) |
| `/truth-audit-content` (S-90) | S-49 `/knowledge-bootstrap` | Always |
| `/system-heal` (S-93) | S-62 `/gap-eval` | Always (Phase 1 invokes gap-eval --no-llm) |
| `/system-heal` (S-93) | S-49 `/knowledge-bootstrap` | Always (knowledge must not be stale) |
| `/publish-readiness-review` (S-95) | S-49 `/knowledge-bootstrap` | Always |
| `/publish-readiness-review` (S-95) | S-25 `/eval-page` | Grades must be current |
| `/backlog harvest` (S-98) | `report_extract.py` | Always |
| `/discovery-triage` (S-104) | S-102 `/repo-patrol` | When routing patrol findings |
| `/discovery-triage` (S-104) | S-103 `/change-sweep` | When routing sweep findings |
| `/section-enhance` (S-105) | S-12 `/knowledge-diff` + S-14 `/knowledge-update` | When `stale_since` is not null |
| `/content-enrich` (S-108) | S-49 `/knowledge-bootstrap` | Always (knowledge artifacts must exist) |
| `/content-enrich` (S-108) | S-57 `/site-plan` | Always (site plan must exist) |
| Any content write | S-01 `/path-guard` | Always (final gate) |

If the upstream skill returns `STOP` or `DENY`, halt immediately and report.
Do not continue to the downstream skill.

## Capability Classification

Before starting any novel task, classify capability:

| State | Definition | Required action |
|-------|-----------|----------------|
| **FULL** | Every step covered by a registered skill | Invoke the skill chain |
| **PARTIAL** | Some steps covered; others not | Execute covered steps; file gap escalation for uncovered |
| **NONE** | No registered skill covers this requirement | File gap escalation immediately; await human decision |
| **BROKEN** | Required skill exists but fails | Capture failure; file breakage report; do not bypass |

### Gap escalation report format

Save to `reports/skill-gaps/{YYYY-MM-DD}-{task-slug}.md`:

```
SKILL GAP ESCALATION
Task: {what was requested}
Capability state: PARTIAL | NONE
Skills invoked (completed): [list]
Uncovered requirement: {precise description}
Impact: {what the user won't get until this gap is filled}

ENHANCEMENT PLAN
  Title: {short name for the missing skill}
  Proposed skill ID: {next available S-xx}
  Input: {what the skill would receive}
  Output: {what the skill would produce}
  Skill file location: skills/{proposed-name}.md
  Depends on: {upstream skills}
  Estimated complexity: LOW | MEDIUM | HIGH
```

### Broken skill report format

Save to `reports/skill-breakage/{YYYY-MM-DD}-{skill-id}.md`:

```
SKILL BREAKAGE REPORT
Skill: {ID and name}
Invocation: {exact command attempted}
Expected output: {spec says it should produce}
Actual output / error: {verbatim failure output}
Impact: {what tasks are blocked}
Suggested diagnosis: {most likely cause}
```

## DAR Maintenance

When a skill is added, removed, renamed, or split, update this table.
Add a row using this template:

```
| `/skill-name` (S-XX) | S-YY `/upstream-skill` | Trigger condition (Always | specific condition) |
```

Steps:
1. Add the row to the table in the correct logical position.
2. Ensure the downstream skill's `## Pre-conditions` section documents the same dependency.
3. Verify the skill file precondition text and the DAR row are aligned.
