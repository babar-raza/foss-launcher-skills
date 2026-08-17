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

This is mostly a discipline check, not a full CI-enforced gate (see "Non-goals" below) — with one
exception: the single mechanically-checkable rule from "The genuinely new rules" below (don't
invent a parallel mission/taskcard tracker) is captured on every plan-file `Write`/`Edit` and,
once burn-in completes, gated at `ExitPlanMode` — see `scripts/ci/checks/check_plan_origination.py`
and `scripts/ci/hooks/check_plan_origination_gate_hook.sh`. It supplements, and does not replace, `/plan-normalize` (S-91), which
governs **resuming or inheriting** an existing plan (see
[docs/workflows/mental-model-refresh.md](../workflows/mental-model-refresh.md) § Plan
Normalization). This section governs **originating** one.

## Concordance table

Generic concept from the reference doc → this repo's concrete artifact. Use the existing artifact;
do not create a differently-shaped one.

| Reference-doc concept | This repo's artifact |
| --- | --- |
| Mission contract | `MISSION_AUTHORITY.yaml` (repo root) — `mission_id`, `mission_summary`, `governing_plan_path`, `in_scope_outcomes`, `out_of_scope_items`, `mandatory_acceptance_criteria`, `mission_locked`. Root file is the current/active projection only (single mutable slot); `scripts/pipeline/commands/governance/mission_authority.py open --mission-id {id}` validates it and archives a durable, immutable snapshot to `reports/plan_state/{mission_id}/mission_authority.yaml` — use `mission_authority.py list` to see every known mission (open and closed), not just the current one. `governing_plan_path` is validated for *presence* only — no code anywhere reads or resolves its value, so it can point at a dead/local path without being caught (confirmed via repo usability/operability audit, 2026-08-16); `plans/master-plan.md`'s per-mission table row is upserted by `scripts/pipeline/lib/master_plan_index.py` (`upsert_mission_row()`, library-only, no CLI, and it does not scaffold a brand-new index — the table must already exist) |
| Taskcard / durable mission state / task DAG | "Schema 5f" — `reports/plan_state/{mission_id}/taskcards.jsonl`, written via `scripts/pipeline/lib/taskcard_store.py` (`TaskcardStore.append()`/`update_taskcard_status()`, library-only, no CLI), validated by `validate_taskcard_record` in `scripts/pipeline/lib/schema_validators.py`; 15-state status enum; `evidence_refs` mandatory for any status past `IMPLEMENTED` |
| Pre-execution plan gate ("don't execute a plan blindly") | `/plan-normalize` (S-91) — classifies plan sections, verifies claims against repo state, selects exactly one next executable item |
| Stall detection / doc-vs-store contradiction | `/plan-health-watchdog` (S-113) + `scripts/ci/checks/check_taskcard_plan_parity.py` |
| Session-level task/dependency tracking, wave sequencing | `/backlog` (S-88) — `backlog/BACKLOG.md`, topologically-sorted Blocker-column DAG |
| Deliverable lifecycle (per execution run) | `refresh_run.py` state machine: `CREATED -> INPUTS_PINNED -> PLANNED -> APPLYING -> VALIDATING -> READY_TO_COMMIT -> COMMITTED`, with `BLOCKED` / `ABANDONED` |
| Claim / lease primitive | `scripts/pipeline/lib/advisory_lock.py` (PID-liveness, mtime-age fallback) |
| Execution lease ("who owns this edit right now") | `scripts/pipeline/commands/governance/skill_context.py` / `reports/skill-context/ACTIVE.json`, session identity established via `scripts/pipeline/lib/session_identity.py` |
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
4. **Plan/taskcard completeness (added 2026-08-17, MT023 silent step-drop assessment).** A plan
   that carries an explicit `## Execution order` numbered-step section is only "ready to execute"
   once `scripts/ci/checks/check_plan_taskcard_completeness.py --plan-file <plan.md> --taskcards
   <mission>/taskcards.jsonl` reports full coverage (step count ≤ distinct taskcard count), or
   each excess step carries an explicit `<!-- NOT-TRACKED: reason -->` opt-out. This closes a gap
   `check_taskcard_plan_parity.py` deliberately does not cover: that tool treats an untagged step
   as silence, never a contradiction (correct for *its* purpose), so a step that was never given a
   taskcard row at all — the actual failure mode found live (a 9-step plan produced only 6
   taskcards; the dropped step named a mission, `MT023-...`, that was never registered anywhere in
   the repo) — was invisible to every existing detector. Agent-invoked via `/plan-health-watchdog`,
   same as the parity check, for the same structural reason (plan files live outside the repo, so
   this cannot be a CI gate).
5. **Eager pause declaration for mid-session context switches.** When execution diverges from the
   active plan/taskcard to handle unplanned, higher-priority work, call
   `TaskcardStore.pause_taskcard(task_id, reason=..., recorded_by=...)` for the deferred item
   *before* proceeding — it auto-creates the row (`create_if_missing=True` by default) if the
   step never had one, so this works even for a step that was only ever plan-prose. This is
   deliberately cheap (one call, no full `MISSION_AUTHORITY.yaml`/convergence-binding ceremony
   required) so it doesn't get skipped under the same time pressure that caused the original
   incident — separating fast, mandatory intent-capture from rich, deferred mission binding (do
   that later, only once actually resuming the work). The new `PAUSED` taskcard status (schema 5f,
   `scripts/pipeline/lib/schema_validators.py`) is non-terminal — still visible to
   `/plan-health-watchdog`'s stall query once it crosses the normal staleness threshold — but
   distinct from `BLOCKED_*`: blocked means "can't proceed", paused means "chose not to proceed
   yet". Requires a non-empty `pause_reason`, the same way verified statuses require
   `evidence_refs` — a paused card with no stated reason is indistinguishable from a silently
   dropped one.

Items 4-5 close a documented, recurring failure class, not a one-off: three independent
same-day incidents (2026-08-06) share the same shape — planned/discovered work that was never
written to any tracked artifact until asked about or noticed retroactively (see
`backlog/BACKLOG.md` row `ASPOSE-COM-TARGETS-STATUS-001`, and the `.supervisor/schemas/` addition
commit `1e310b978c`'s own forensic finding that MT019/MT020 each produced only a fraction of their
declared stage artifacts while self-reporting full conformance). Both existing detectors
(`/plan-health-watchdog`'s stall query, `/plan-normalize`'s resume gate) are calibrated to
multi-day staleness (5 business days / 7 days) and are structurally blind to same-session
abandonment — items 4-5 do not touch those thresholds; they add a same-session-capable layer
alongside them.

**Not yet implemented** (tracked in `backlog/BACKLOG.md`, not silently deferred): an automatic
same-session/turn-boundary reconciliation check (comparing taskcards touched this session against
same-session commits, to catch a card stuck non-terminal while real work continued — the
`TC-MEDIA-02`-stuck-at-13:17-while-commits-kept-landing-until-17:28 shape from the same incident),
and a `/session-start` briefing item that queries `reports/plan_state/*/taskcards.jsonl`
mechanically instead of relying solely on hand-written `HANDOFF.md`/`BACKLOG.md` prose (which was
independently found to already be several days stale). See `backlog/BACKLOG.md` for the tracked
row.

## Non-goals

- This doc does not replace `/plan-normalize`, `/plan-health-watchdog`, `/backlog`, or any other
  registered skill — it tells an agent which one to reach for.
- This is not a broad new CI-enforced gate over the whole Planning Review Checklist / Taskcard
  Readiness Checklist — the source reference doc itself warns against turning those checklists
  into a rigid regex gate (high false-positive risk). Most of this section remains discipline
  text, consistent with how most of `AGENTS.md` (e.g. §7, §8, §11) already works. The one
  exception is the narrow, mechanically-checkable "no parallel tracker" rule below, which is
  gated (see "When this applies").
- This does not require literally creating the reference doc's YAML schemas (mission graph,
  transition event, campaign manifest, etc.) in this repo — those are illustrative of the model,
  not file formats to reproduce. Use the concordance table.

## Related

- [AGENTS.md §17](../../AGENTS.md) — governance rule
- [docs/reference/planning-execution-state-machine.md](../reference/planning-execution-state-machine.md) — full reference framework
- [docs/workflows/mental-model-refresh.md](../workflows/mental-model-refresh.md) — Plan Normalization (resuming a plan)
- [docs/registries/skills.md](../registries/skills.md) — Plan execution gate
- `MISSION_AUTHORITY.yaml` (repo root) — live example of the mission-contract shape
