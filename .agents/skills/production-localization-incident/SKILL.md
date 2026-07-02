---
name: production-localization-incident
id: S-109
description: >
  Orchestrate production localization incidents without duplicating translation or pipeline-hardening behavior.
args: "``"
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

<!-- CONTRACT: agent-executed
     purpose: production localization incident orchestration; fail-closed containment, forensics, review packets, registered skill routing, preview/deployment gates, live/CDN verification, monitoring, resume, and closure
     preconditions: incident request JSON exists; S-52, S-53, and S-99 are registered; evidence root is writable
     postcondition: incident state, evidence, taskcards, inventory, and exact next action are persisted; production mutation is blocked unless explicitly authorized with rollback state
     idempotent: yes — duplicate start is rejected; resume/status reads persisted state; closeout is gated
     verified: 2026-06-29
     id: S-109
     depends_on: [S-52, S-53, S-99]
-->

# S-109: Production Localization Incident — Contain, Investigate, Repair, Verify, and Close Localized Production Incidents

**Arguments**: `$ARGUMENTS`
**Expected format**: `start --request {request.json} [--gap-report {path}] [--allow-production] | execute --state {state.json} --request {request.json} --phase {phase} | status --state {state.json} | resume --state {state.json} | close --state {state.json}`

## Purpose

Orchestrate production localization incidents without duplicating translation or pipeline-hardening behavior. Use this skill when localized Aspose.org pages may contain partial translations, English injection, stale locale output, wrong-language fragments, template localization failures, or publication-gate bypasses requiring containment, source-to-live forensics, review packets, controlled rectification, preview/deployment gates, live/CDN verification, monitoring, idempotency, and terminal closure.

## Authority

This skill owns incident control, state, evidence, inventory, taskcards, human-review packet orchestration, and registered follow-on routing.

It does not own generic translation execution, generic translation validation, generic pipeline hardening, infrastructure credentials, final business language authority, or arbitrary publication. Route translation execution to S-52 or S-53. Route product-scoped producer hardening to S-99. Route publish-readiness inspection to S-90 where applicable.

S-109 owns bounded agent-executed language incident review: completeness, English fallback detection, protected-term handling, technical-fidelity challenge, adjudication, and confidence. Treat that review as an incident-control gate, not as final marketing or legal approval.

## Backing Command

Use the deterministic runner:

```bash
.venv/Scripts/python scripts/pipeline/commands/ops/localization_incident.py start --request {request.json} --gap-report {gap_report}
```

The runner writes state and evidence under the request's `evidence_root`, plus reports under `reports/localization/{incident_id}/`.

Execute one bounded phase at a time:

```bash
.venv/Scripts/python scripts/pipeline/commands/ops/localization_incident.py execute \
  --state {evidence_root}/state.json \
  --request {request.json} \
  --phase triage
```

Supported phases: `triage`, `containment`, `forensics`, `scope`, `blocker-challenge`, `affected-ledger`, `missing-disposition`, `review-packets`, `agent-review`, `producer-readiness`, `live-verify`, `monitor`, `monitor-scan`, `idempotency`.

## Input Contract

Request JSON must match `data/schemas/production-localization-incident-request.schema.json` and include:

- `incident_id`, `incident_title`, `detected_at`
- `reported_urls`, suspected sites/families/platforms/locales
- incident types such as `PARTIAL_TRANSLATION`, `ENGLISH_INJECTION`, or `PUBLICATION_GATE_BYPASS`
- `source_revision`, optional `production_revision`, optional `known_good_revision`
- verification requirements for live and CDN checks
- `containment_mode`, `execution_mode`
- allowed/forbidden paths, evidence root, rollback and closeout requirements

Execution modes:

- `INVESTIGATION_ONLY`
- `CONTAINMENT_ONLY`
- `DRY_RUN`
- `RECTIFICATION_PREVIEW`
- `CONTROLLED_PRODUCTION_REPAIR`
- `MONITORING_ONLY`
- `RESUME`

Fail closed if locale identity, evidence root, deployment authority, production revision, or rollback state is ambiguous.

## Output Contract

The runner emits `production_localization_incident_result` compatible JSON:

- containment state
- affected page inventory
- findings and unresolved blockers
- canonical gap IDs and taskcard IDs
- S-52/S-53/S-99 invocation records
- preview/deployment/live/CDN verification slots
- monitoring state
- continuation flag and exact next action
- terminal verdict

## State Model

Persist `state.json` with statuses:

`PROPOSED -> TRIAGED -> CONTAINMENT_ACTIVE -> FORENSICS_ACTIVE -> SCOPE_VERIFIED -> MACHINERY_REPAIR_ACTIVE -> CONTENT_RECTIFICATION_ACTIVE -> PREVIEW_REVIEW_ACTIVE -> PRODUCTION_DEPLOYMENT_ACTIVE -> LIVE_VERIFICATION_ACTIVE -> MONITORING_ACTIVE -> REAUDIT_ACTIVE -> VERIFIED -> CLOSED`

Failure states:

- `BLOCKED_EXTERNAL`
- `BLOCKED_AUTHORITY`
- `ROLLBACK_REQUIRED`
- `INVALIDATED`
- `REWORK_REQUIRED`

## Taskcards

Create one taskcard per bounded phase under `{evidence_root}/taskcards/`:

- `LOCALIZATION_INCIDENT_TRIAGE`
- `LOCALIZATION_INCIDENT_CONTAINMENT`
- `LOCALIZATION_WORKTREE_FORENSICS`
- `LOCALIZATION_COMMIT_FORENSICS`
- `LOCALIZED_PAGE_INVENTORY`
- `SEGMENT_REVIEW`
- `TRANSLATION_RECTIFICATION`
- `PIPELINE_HARDENING`
- `PREVIEW_BUILD`
- `HUMAN_REVIEW`
- `PRODUCTION_DEPLOYMENT`
- `LIVE_VERIFICATION`
- `CDN_VERIFICATION`
- `MONITORING`
- `INCIDENT_CLOSEOUT`

Every actionable finding must map to a canonical gap and at least one taskcard.

## Execution Phases

1. **Preflight**: validate request, evidence root, duplicate incident ID, dependency registration, gap report, and authority.
2. **Containment**: record affected publication/mutation lane and rollback requirements. Do not mutate production without explicit allowed state.
3. **Forensics**: capture worktree, staged/untracked, commit, source, locale, deployment, and live/CDN evidence where available.
4. **Scope**: inventory English and localized pages, classify risk, and generate review packets.
5. **Blocker challenge**: classify each blocker as agent-owned, locally actionable, repository-routable, or truly external. Do not preserve stale external blockers after evidence proves a local route.
6. **Affected ledger**: write `reports/localization/affected-localized-pages.yaml`, validate completeness, and create one page taskcard per actionable localized page.
7. **Agent review**: perform bounded multilingual incident review for completeness, language quality, technical fidelity, independent challenge, adjudication, and confidence.
8. **Missing disposition**: disposition every missing localized path as create/repair/retire/no-action with required skill routing.
9. **Root cause**: determine the first failing boundary. Invoke S-99 for product-scoped producer defects.
10. **Rectification**: invoke S-52/S-53 only for approved scoped translation work. Preserve provenance and protected terms.
11. **Preview**: build and review preview before production deployment.
12. **Production**: require rollback state, authorized batch scope, live verification, and CDN verification.
13. **Monitoring**: install a deterministic monitor command first, then route scheduler/CI integration separately.
14. **Closure**: reject report-only closure. Require live verification, CDN verification, monitoring, and second unchanged run.

## Human Authority Boundaries

Create review packets for language correctness and technical meaning. Perform bounded agent language review before claiming the incident has been linguistically triaged. Do not claim final human business approval unless a reviewer result is recorded. Real human authority is required for destructive rollback outside approved batch scope, unavailable deployment/CDN credentials, final production approval where policy requires it, or critical/high-risk wording where the agent records low confidence after repair.

## Negative Controls

Reject:

- incident with no evidence root
- incident with no locale identity
- production mutation in investigation-only mode
- deployment without preview
- deployment without rollback state
- localized changes outside allowed scope
- failed S-53 verification
- unresolved S-99 blocker
- stale production/source revisions
- missing live or CDN verification where required
- report-only closure
- second run that creates duplicate state, gaps, taskcards, or evidence

## Verification

Run:

```bash
.venv/Scripts/python -m pytest scripts/pipeline/tests/test_localization_incident.py -q
.venv/Scripts/python scripts/ci/checks/check_pipeline_registration.py
.venv/Scripts/python scripts/pipeline/commands/ops/sync_skills.py --check
```

## Initial Incident Request

For the 2026-06-29 production incident, create a request JSON under `reports/localization/production-translation-incident-request.json` with entry point `https://products.aspose.org/pdf/net/`, family `pdf`, platform `net`, suspected site `products.aspose.org`, suspected locales, incident types `PARTIAL_TRANSLATION`, `ENGLISH_INJECTION`, `TEMPLATE_LOCALIZATION_FAILURE`, and `PUBLICATION_GATE_BYPASS`, execution mode `INVESTIGATION_ONLY`, and evidence root `.local/evidences/production-localization-incident-2026-06-29`.
