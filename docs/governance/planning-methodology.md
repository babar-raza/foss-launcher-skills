---
# Governance child document
# Authored fresh for this repo (NOT copied from aspose.org) as the
# repo-specific binding layer for ../reference/planning-execution-state-machine.md
# Source: 2026-08-29 sync from aspose.org -- see docs/parity/source-anchors.yaml
# for what WAS ported verbatim (the reference doc itself, confirmed
# project-agnostic) versus what is original to this repo (this binding).
---

# Planning Methodology -- Concordance for This Repo

[../reference/planning-execution-state-machine.md](../reference/planning-execution-state-machine.md)
is a generic, project-agnostic reference model for turning a goal into an
evidence-backed plan and coordinating agents through a durable execution
state machine. It explicitly says not to create its literal schemas
(taskcard YAML, mission graph YAML, etc.) as new files -- a project should
map the model onto whatever tracking artifacts it already has. This doc is
that mapping for THIS repo.

## Concordance table

| Generic model concept | This repo's equivalent | Honest gap |
|---|---|---|
| Vision / product intent | `README.md`, `CHANGELOG.md` `[Unreleased]` | -- |
| Current master plan and decisions | `TASK_BACKLOG.md` (dated Workstream sections), `docs/parity/README.md` (current-state block) | No single "master plan" doc; decisions live across both |
| Normative requirements | `skills/registry.yaml`, `.governance/schemas/capability.schema.json` contracts | Covers *skills*, not every kind of work item |
| Executable taskcard DAG | `TASK_BACKLOG.md` rows (`ID`/`Task`/`Owner`/`Status`/`Acceptance` columns per Workstream) | **See "What this is not" below** |
| Durable claims and transitions | `docs/parity/source-anchors.yaml` (source-provenance claims), `.governance/generated/*.yaml` (drift verdicts) | No CAS-protected concurrent-write ledger (see below) |
| Evidence and independently verified outcomes | pytest output, `.governance/generated/drift-report.yaml`, `.governance/generated/source-drift-report.yaml`, a Workstream row's `Acceptance` column | -- |
| Mission-task state vs. deliverable lifecycle state (two separate state machines) | `TASK_BACKLOG.md`'s single `Status` column conflates both | **See "What this is not" below** |

## What this is not

Be honest about where this repo's planning mechanism is thinner than the
generic model, rather than claiming a concordance that doesn't fully hold:

- **No dependency-ordered DAG.** `TASK_BACKLOG.md` rows are grouped by
  Workstream, not linked by an explicit "blocked-by" graph. Ordering within
  a workstream is positional (table row order), not machine-computed.
- **No concurrency-safe, compare-and-swap ledger.** aspose.org built exactly
  this (`taskcard_store.py` + `master_plan_index.py`, both FileLock-guarded
  with row-level CAS) after getting burned by concurrent-session write
  races. This repo has not needed that yet -- `TASK_BACKLOG.md` is a plain
  markdown file, edited directly. If this repo starts being worked by
  multiple concurrent agent sessions the way aspose.org is, that gap
  becomes real; it is tracked as a deferred item in `TASK_BACKLOG.md`
  (Workstream SYNC-2026-08-29) rather than solved preemptively here.
- **Mission-task state and deliverable-lifecycle state are conflated.** A
  single `Status` column (e.g. "✅ DONE") in `TASK_BACKLOG.md` does not
  distinguish "the implementation task is closed" from "the resulting
  capability has been independently verified in production use" -- exactly
  the distinction the generic model insists on keeping separate. Reading a
  row's `Acceptance` column is currently the only way to tell which sense
  of "done" applies, and that's a matter of the row author's diligence, not
  a structural guarantee.

## When to use this doc

Before creating any new plan-tracking artifact in this repo, check this
table first. If an existing artifact already covers the need, extend it
rather than inventing a parallel one -- the doc-sprawl problem this
concordance approach is meant to avoid is exactly what happened to
aspose.org's own `docs/parity/` history before this sync (eight files
across two migration phases, no single current-state marker; see
`docs/parity/README.md`'s "Current State" section for how this repo
avoids repeating that).
