---
# Governance child document — extracted from AGENTS.md
# Source: AGENTS.md §6a
# Plan: delightful-wondering-hartmanis (TC-03)
# Extracted: 2026-04-28
---

## 6a. Skill-First Execution Mandate

### Rule

Every agent operating on this repo must treat the skill system as the **default and required** execution mechanism. This rule has the same enforcement weight as path-guard (§4) and evidence requirements (§5).

### What "skill-first" means in practice

1. **Before starting any task**, identify which registered skill(s) in §12 cover it.
2. **Invoke matching skills** in the order defined by §6 chains. Do not perform equivalent
   work through inline reasoning, shell one-liners, or ad hoc prompting when a skill exists.
3. **Activate upstream dependencies automatically.** If a skill you need requires a
   precondition (e.g., `/knowledge-bootstrap` before `/page-draft`), you must invoke that
   precondition skill first — even if the user's request did not mention it.
4. **Do not invent workflows.** If no skill covers the requirement, follow §6b (gap
   escalation). Do not design a one-off process and execute it.

### Dependency Activation Rule (DAR)

Agents must activate the upstream skill if it has not already been confirmed as passing in the current session. "Passing" means: the upstream skill returned a non-STOP status in this conversation, no knowledge-modifying skill has run since, and less than one hour has elapsed.

| Downstream skill | Required upstream | Trigger condition |
|-----------------|------------------|------------------|
| `/page-plan` (S-18) | `/knowledge-bootstrap` | Always |
| `/page-draft` (S-19) | `/knowledge-bootstrap` | Always |
| `/page-draft` (S-19) | `/page-plan` (S-18) | Plan not in session context |
| `/page-update` (S-20) | S-12 `/knowledge-diff` + S-14 `/knowledge-update` | `stale_since` not null |
| `/page-enhance` (S-21) | S-25 `/eval-page` or S-17 `/rubric-align` (either satisfies — choice of [S-25, S-17]) | Eval not in session context |
| `/heal-page` (S-26) | S-25 `/eval-page` | Eval not in session context |
| `/content-check` (S-23) | `/knowledge-bootstrap` | Always |
| `/truth-merge` (S-35) | S-34 `/repo-scout` | Scout output absent |
| `/batch-remediate` (S-40) | `/knowledge-bootstrap` | Always |
| `/batch-eval-fix` (S-41) | `/knowledge-bootstrap` | Always |
| `/faq-generate` (S-22) | `/knowledge-bootstrap` | Always |
| `/new-docs-page` (S-56) | `/knowledge-bootstrap` | Always |
| `/new-blog-post` (S-57) | `/knowledge-bootstrap` | Always |
| `/new-kb-howto` (S-58) | `/knowledge-bootstrap` | Always |
| `/new-kb-faq` (S-59) | `/knowledge-bootstrap` | Always |
| `/new-reference-page` (S-60) | `/knowledge-bootstrap` | Always |
| `/new-products-page` (S-61) | `/knowledge-bootstrap` | Always |
| `/batch-reference` (S-62) | `/knowledge-bootstrap` | Always |
| `/change-guard` (S-33) | `/knowledge-bootstrap` | Always |
| `/content-audit` (S-32) | `/knowledge-bootstrap` | Always |
| `/site-plan` (S-47) | `/knowledge-bootstrap` | Always |
| `/family-sync` (S-48) | `/knowledge-bootstrap` | Always |
| `/launch-product` (S-49) | S-47 `/site-plan` | Always (Stage 0.5 — must run before Stage 1; produces slug manifest) |
| `/gap-apply` (S-46) | S-44 `/gap-plan` | Plan not in session context |
| `/new-docs-index` (S-70) | `/knowledge-bootstrap` | Always |
| `/new-kb-index` (S-69) | `/knowledge-bootstrap` | Always |
| `/new-reference-index` (S-71) | `/knowledge-bootstrap` | Always |
| `/register-human-content` (S-66) | `/knowledge-bootstrap` | Always |
| `/evidence-repair` (S-72) | S-12 `/knowledge-diff` + S-14 `/knowledge-update` | `stale_since` not null |
| `/manual-edit` (S-73) | S-12 `/knowledge-diff` + S-14 `/knowledge-update` | `stale_since` not null |
| `/evidence-enhance` (S-78) | S-12 `/knowledge-diff` + S-14 `/knowledge-update` | `stale_since` not null |
| `/delta-site-plan` (S-82) | S-14 `/knowledge-update` | Always (knowledge_delta.json must exist) |
| `/page-retire` (S-83) | S-82 `/delta-site-plan` | When retiring from plan; or explicit operator path |
| `/refresh-product` (S-84) | S-12 `/knowledge-diff` | Always (auto-invokes S-14, S-82, S-83 in sequence) |
| `/truth-audit-content` (S-85) | S-54 `/knowledge-bootstrap` | Always |
| `/system-heal` (S-87) | S-43 `/gap-eval` | Always (Phase 1 invokes gap-eval --no-llm) |
| `/system-heal` (S-87) | S-54 `/knowledge-bootstrap` | Always (knowledge must not be stale before healing) |
| `/publish-readiness-review` (S-90) | S-54 `/knowledge-bootstrap` | Always (knowledge must not be stale before inspection) |
| `/publish-readiness-review` (S-90) | S-25 `/eval-page` or content_eval | Grades must be current at EVALUATOR_LOGIC_VERSION |
| `/backlog harvest` (S-88) | `report_extract.py` | Always (extracts open items from reports) |
| `/backlog harvest` (S-88) | `harvest_ledger.py` | Always (tracks harvest state and dedup) |
| `/discovery-triage` (S-95) | S-93 `/repo-patrol` | When routing patrol findings (patrol_report.json must exist from current or prior session) |
| `/discovery-triage` (S-95) | S-94 `/change-sweep` | When routing sweep findings (sweep_report.json must exist from current or prior session) |
| `/section-enhance` (S-96) | S-12 `/knowledge-diff` + S-14 `/knowledge-update` | When `stale_since` is not null in `knowledge/{family}/{platform}/merged/model.yaml` |
| `/content-enrich` (S-98) | S-54 `/knowledge-bootstrap` | Always (knowledge artifacts must exist) |
| `/content-enrich` (S-98) | S-47 `/site-plan` | Always (site plan must exist for cluster extraction) |
| Any content write | S-01 `/path-guard` | Always (final gate) |

If the upstream skill returns `STOP` or `DENY`, halt immediately and report. Do not continue to the downstream skill.

**DAR scope**: The DAR table lists skills that require an upstream dependency to be activated *before* they can begin. Orchestrator skills that invoke upstream dependencies as part of their own internal pipeline (e.g., `launch-product` invoking bootstrap as Stage 0, `knowledge-update` managing the full refresh chain) are not listed — they manage their own dependency chain. The test is: "Does this skill require someone else to have already run the upstream skill?" If yes → DAR entry. If the skill runs the upstream itself internally → no DAR entry.

**DAR maintenance**: When a skill is added, removed, renamed, or split, update this table. Run `python scripts/ci/checks/check_dar_coverage.py` to verify alignment between the DAR table and skill file preconditions.

**Adding a DAR entry** — use this template:

```
| `/skill-name` (S-XX) | S-YY `/upstream-skill` | Trigger condition (Always | specific condition) |
```

Steps:
1. Add the row to the table above in the correct alphabetical/logical position.
2. Ensure the downstream skill's `## Pre-conditions` section documents the same dependency.
3. Run `python scripts/ci/checks/check_dar_coverage.py` — must exit 0.
4. If the CI check fails, the skill file precondition text and the DAR row are misaligned — fix both.

## 6b. Capability Classification and Gap Escalation

Before starting any task that is not a direct invocation of a single registered skill, the agent must classify its capability level and act accordingly.

### Capability states (choose exactly one)

| State | Definition | Required action |
|-------|-----------|----------------|
| **FULL** | Every step of the requirement is covered by a registered skill in §12 | Invoke the skill chain; no gap report needed |
| **PARTIAL** | Some steps are covered; others are not | Execute skill-covered steps; produce gap escalation report for uncovered steps; do not perform uncovered steps through ad hoc work |
| **NONE** | No registered skill covers this requirement | Do not start work; produce gap escalation report immediately; await human decision |
| **BROKEN** | A required skill exists but fails when invoked | Invoke it, capture failure output; produce breakage report; do not bypass; await human decision |

### Classification output

When starting a novel, multi-part, or ambiguous request, state:

```
CAPABILITY ASSESSMENT — {brief task description}
State: FULL | PARTIAL | NONE | BROKEN
Skill(s) covering this task: [list skill IDs and names, or "none"]
Gap (if PARTIAL or NONE): [describe what is not covered]
Broken skill (if BROKEN): [skill ID, invocation attempted, error observed]
Planned action: [what you will do next]
```

For requests that are direct invocations of a single skill or a predefined §6 chain, this output is implicit — you do not need to print it.

### Gap escalation report format

When state is PARTIAL or NONE, produce this report after completing any skill-covered work, and save to `reports/skill-gaps/{YYYY-MM-DD}-{task-slug}.md`:

```
SKILL GAP ESCALATION
Task: {what was requested}
Capability state: PARTIAL | NONE
Skills invoked (completed): [list]
Uncovered requirement: {precise description}
Impact: {what the user won't get until this gap is filled}

ENHANCEMENT PLAN
  Title: {short name for the missing skill}
  Proposed skill ID: {next available S-xx or descriptive name}
  Input: {what the skill would receive}
  Output: {what the skill would produce}
  Skill file location: skills/{proposed-name}.md
  Depends on: {upstream skills it would call}
  Estimated complexity: LOW | MEDIUM | HIGH
  Workaround available: YES | NO
  If YES — workaround description: {only if it can be done safely without fabrication}
```

### Broken skill report format

When state is BROKEN, save to `reports/skill-breakage/{YYYY-MM-DD}-{skill-id}.md`:

```
SKILL BREAKAGE REPORT
Skill: {ID and name}
Invocation: {exact command or invocation attempted}
Expected output: {what the skill's spec says it should produce}
Actual output / error: {verbatim failure output}
Impact: {what tasks are blocked until this is fixed}
Suggested diagnosis: {most likely cause based on the error}
```

### Novel requirement protocol

If the requirement does not match any task type in §6:

1. Classify capability (FULL / PARTIAL / NONE) — for truly novel requirements this will
   usually be PARTIAL or NONE.
2. If PARTIAL: execute skill-covered steps, then produce gap escalation report.
3. If NONE: produce gap escalation report immediately. Do not attempt the work.
4. Do not design a new workflow and execute it inline — this is prohibited by §11.
5. Fill in the "Enhancement Plan" section of the gap escalation report fully. This is the
   mechanism by which the skill system grows to cover new requirements.

### Anti-workaround mandate (added 2026-04-07)

Before creating any new `.py` file anywhere in the repository, or before writing any
inline loop, shell hack, or ad hoc Python in bash to work around a missing pipeline step,
you MUST:

1. **Check for an existing script** — look in `scripts/pipeline/` for a script that covers
   the need. If one exists but is broken or incomplete, classify as BROKEN and file a
   breakage report (§6b). Fix the script; do not invent a parallel workaround.
2. **Check for an existing skill** — if the task maps to a registered skill (§12), invoke it.
   If the skill fails, classify as BROKEN. Do not bypass with ad hoc code.
3. **If the capability is truly absent** — classify as NONE, produce a gap escalation report
   immediately, and add the missing script or skill in the correct layer with CONTRACT comment,
   tests, and docs before using it. Do not execute ad hoc work pending the addition.
4. **If a workaround is unavoidable** — mark it explicitly as TEMPORARY in a comment, create
   a tracked remediation item (gap escalation report at `reports/skill-gaps/`), and include
   the exit criteria for when the workaround becomes unnecessary.
5. **Reverify after every fix** — after adding or repairing a capability, re-run the original
   failing scenario to prove the workaround is no longer needed. The sprint is not complete
   until every former ad hoc step is replaced by its durable system path.

Specific failures this rule prevents (Healing Sprint 2026-04-07):
- Inline Python batch loops in bash → use `scripts/pipeline/commands/content/batch_reference.py` (S-62)
- PYTHONPATH prefix hacks → use `scripts/pipeline/commands/content/run_content_eval.py` wrapper
- Manual `stale_since` edits → `refresh_knowledge.py` clears it automatically after refresh
- Dropping args from skill invocations → read the actual CLI first; fix spec if it drifts
- On-the-fly kind filter rewrites → check `_CLASS_TYPES` in `extraction/tree_helpers.py`

### Defect classification during validation (added 2026-04-16)

When a validation run (pilot rerun, E2E evaluation, benchmark) surfaces an error or crash,
classify it **before** routing. Apply this decision tree:

```
1. Does the failing code path exist in any file modified by the current track?
   YES → Track regression. Block closure until fixed.
   NO  → Go to step 2.

2. Does git blame show the failing line was introduced by a track commit?
   YES → Track regression (latent, activated by new conditions).
   NO  → Go to step 3.

3. Is the error triggered by test data/fixtures created by the track?
   YES → Track test design issue. Fix fixture, re-validate.
   NO  → Pre-existing defect. Route to owner track (standalone ED-* item
         or appropriate backlog track). Do NOT block current track closure.
```

Record the classification in this format (inline or in a report):

```
DEFECT CLASSIFICATION
  Error: {type} at {file}:{line}
  Triggering page: {path}
  Classification: regression | latent-regression | test-design | pre-existing
  Evidence: {git blame hash + date, file inventory check}
  Routed to: {item ID or "current track"}
  Blocks closure: yes | no
```

Pre-existing defects never contaminate the validating track's closure decision. See also:
`test_benchmark_no_unhandled_exceptions` in `test_human_likeness.py` (G-3 guardrail) which
prevents pre-existing crashes from silently corrupting benchmark results.

---

## Metrics Obligation

Pipeline workflows using `llm.professionalize.com` carry a metrics obligation. Decision records
that approve new professionalize call sites must note the corresponding `metrics_callsite_registry.yaml`
entry and the `AGENT_METRICS` capture method. See `AGENTS.md §15`.
