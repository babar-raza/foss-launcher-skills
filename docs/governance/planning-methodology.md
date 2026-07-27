# Planning Discipline — Mission & Taskcard Methodology

Status: Current
Audience: Agent, Operator
Last verified: 2026-07-27

## Summary

See `AGENTS.md` §17 for the governance rule. This doc binds the project-agnostic reference
framework at [docs/reference/planning-execution-state-machine.md](../reference/planning-execution-state-machine.md)
to this repo's *existing* concrete mechanisms. It does not introduce a new task-tracking system —
this repo has already converged on most of the reference framework's concepts under different
names. The purpose of this doc is to name that convergence explicitly, so an agent authoring a new
multi-step plan reaches for an existing artifact instead of inventing a parallel one (the reference
doc's own Core Principle #2: *"One controller, one task graph, one durable continuation state...
parallel ledgers create predictable failures"*).

## When this applies

Before treating any newly-authored multi-step plan as **ready to execute** — including:

- Claude Code Plan Mode output, before `ExitPlanMode` is accepted as final;
- Codex CLI's own multi-step plan authoring;
- output from `/page-plan`, `/site-plan`, `/delta-site-plan`, or `/backlog plan`;

— self-check it against the reference doc's **Planning review checklist** and **Taskcard
readiness checklist** (both near the end of
[planning-execution-state-machine.md](../reference/planning-execution-state-machine.md)).

This is a discipline check, not a new gate script — there is no CI enforcement for this section
(see "Non-goals" below). It supplements, and does not replace, `/plan-normalize` (S-91), which
governs **resuming or inheriting** an existing plan (see
[docs/workflows/mental-model-refresh.md](../workflows/mental-model-refresh.md) § Plan
Normalization). This section governs **originating** one.

## Concordance table

Generic concept from the reference doc → this repo's concrete artifact. Use the existing artifact;
do not create a differently-shaped one.

| Reference-doc concept | This repo's artifact |
| --- | --- |
| Mission contract | `MISSION_AUTHORITY.yaml` (repo root) — `mission_id`, `mission_summary`, `governing_plan_path`, `in_scope_outcomes`, `out_of_scope_items`, `mandatory_acceptance_criteria`, `mission_locked` |
| Taskcard / durable mission state / task DAG | "Schema 5f" — `reports/plan_state/{mission_id}/taskcards.jsonl`, validated by `validate_taskcard_record` in `scripts/pipeline/lib/schema_validators.py`; 15-state status enum; `evidence_refs` mandatory for any status past `IMPLEMENTED` |
| Pre-execution plan gate ("don't execute a plan blindly") | `/plan-normalize` (S-91) — classifies plan sections, verifies claims against repo state, selects exactly one next executable item |
| Stall detection / doc-vs-store contradiction | `/plan-health-watchdog` (S-113) + `scripts/ci/checks/check_taskcard_plan_parity.py` |
| Session-level task/dependency tracking, wave sequencing | `/backlog` (S-88) — `backlog/BACKLOG.md`, topologically-sorted Blocker-column DAG |
| Deliverable lifecycle (per execution run) | `refresh_run.py` state machine: `CREATED -> INPUTS_PINNED -> PLANNED -> APPLYING -> VALIDATING -> READY_TO_COMMIT -> COMMITTED`, with `BLOCKED` / `ABANDONED` |
| Claim / lease primitive | `scripts/pipeline/core/advisory_lock.py` (PID-liveness, mtime-age fallback) |
| Execution lease ("who owns this edit right now") | `scripts/pipeline/commands/governance/skill_context.py` / `reports/skill-context/ACTIVE.json` |
| Gate ordering by authority and risk | `scripts/pipeline/commands/launch/readiness_gate.py` (G-01..G-07); archived predecessor `docs/_archive/pre-refactor/governance/launch-gates.md` (L-01..L-15, H-01..H-05) |
| Dependency Authority Registry (upstream/downstream skill dependencies) | [docs/governance/dar-table.md](dar-table.md) |
| Capability classification / gap escalation for uncovered work | `AGENTS.md` §6b, [docs/workflows/gap-escalation.md](../workflows/gap-escalation.md) |

## The genuinely new rules

The following are not yet covered by anything in the concordance table above — they are the actual
gap this section closes:

1. **Self-check before execution.** Before starting execution of any newly-authored multi-step
   plan (see "When this applies"), the agent MUST check it against the reference doc's Planning
   review checklist and Taskcard readiness checklist. This is a self-administered check, not a
   separate skill invocation.
2. **One mission-contract shape.** Any plan intended to span multiple sessions or agents (a
   "mission") MUST record its mission contract in the `MISSION_AUTHORITY.yaml` shape — do not
   invent a differently-shaped mission file.
3. **No parallel taskcard system.** Do not create a second, free-form task-tracking artifact for
   multi-step work that only lives in prose. Bind new taskcards to schema 5f
   (`reports/plan_state/{mission_id}/taskcards.jsonl`) or `backlog/BACKLOG.md`, per the
   concordance table above, so `/plan-health-watchdog` and `/plan-normalize` can see it.

## Non-goals

- This doc does not replace `/plan-normalize`, `/plan-health-watchdog`, `/backlog`, or any other
  registered skill — it tells an agent which one to reach for.
- This is not a new CI-enforced gate. No script validates compliance with this section; it is
  discipline text, consistent with how most of `AGENTS.md` (e.g. §7, §8, §11) already works.
- This does not require literally creating the reference doc's YAML schemas (mission graph,
  transition event, campaign manifest, etc.) in this repo — those are illustrative of the model,
  not file formats to reproduce. Use the concordance table.

## Related

- [AGENTS.md §17](../../AGENTS.md) — governance rule
- [docs/reference/planning-execution-state-machine.md](../reference/planning-execution-state-machine.md) — full reference framework
- [docs/workflows/mental-model-refresh.md](../workflows/mental-model-refresh.md) — Plan Normalization (resuming a plan)
- [docs/registries/skills.md](../registries/skills.md) — Plan execution gate
- `MISSION_AUTHORITY.yaml` (repo root) — live example of the mission-contract shape
