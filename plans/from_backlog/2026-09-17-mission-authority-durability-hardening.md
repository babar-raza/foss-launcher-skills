# Mission-Authority Durability Hardening — Track A of MT066's resolution plan

> Created: 2026-09-17
> Source: first-principles production assessment of MT066-2026-09-09-PACKAGE-INSTALL-RECONCILIATION, executed as a
> separate mission (MT071) since this scope is general-purpose governance infrastructure, not package-install-specific.
> Full plan (both Track A and Track B, plus the Supervisor/Lane-agent execution schema): a local Claude Code plan file
> at `C:/Users/prora/.claude/plans/melodic-pondering-cray.md` — this document is the committed, repo-durable copy of
> Track A only, per GOV-02 (register at mission-open time with a real repo path, not a local-only plan cache path).
> Status: OPEN, IN PROGRESS

## Context

A deep assessment of mission MT066 found a systemic governance gap, independent of MT066's own content-migration
backlog: the root `MISSION_AUTHORITY.yaml` slot is (by its own tooling's module docstring) "a narrative pointer, not
an execution lock." Missions can force-take-over the slot from a `mission_locked: true`, `_archive_status: open`
incumbent with nothing more than a 15-character reason string, and nothing durably records what happens to the
incumbent's remaining work. `mission_authority.py list` shows at least 9 missions (MT025, MT028, MT037, MT058,
MT059, MT062, MT064, plus 3 readme-refresh-track missions, MT066 itself) simultaneously `[open]` today, with no
automatic staleness detection anywhere in the repo. Compounding this, the entire durable mission/taskcard ledger
(`reports/plan_state/**`) is git-ignored and exists only on whichever single machine last touched it — invisible to
concurrent sessions, unrecoverable if that machine's state is lost.

## Goals

1. `reports/plan_state/**` becomes git-tracked, with every embedded local-machine absolute path redacted first.
2. An open mission with no taskcard activity for 7+ days surfaces automatically at session start, without a human
   having to think to check.
3. Force-taking-over the root mission slot from a locked/open incumbent requires recording a disposition for the
   incumbent's remaining work, closing the exact mechanism that left MT066 (and the 8 others above) dangling.

## Taskcards

Full taskcard detail (source excerpts, root cause, scope, dependencies, acceptance checks, evidence, rollback, stop
conditions) lives in the master plan file (`melodic-pondering-cray.md` §5, `TC-GOV-01`/`TC-GOV-02`/`TC-GOV-03`) and
in this mission's own durable ledger at `reports/plan_state/MT071-2026-09-17-GOVERNANCE-DURABILITY-HARDENING/taskcards.jsonl`
(schema 5f, the actual source of truth for live status). Summary:

- **TC-GOV-01** — Redact-then-track `reports/plan_state/**` (3 children: new `whole_subtree` git-tracking-policy
  type, a redaction script, applying the policy + doctrine-doc update).
- **TC-GOV-02** — Automated stale-mission detector wired into session start (2 children: a 4th liveness-report
  store, wiring into the existing session-start print block). Depends on TC-GOV-01.
- **TC-GOV-03** — Require a disposition on forced root-slot takeover (2 children: `--disposition` flag on
  `cmd_activate`, test coverage). Independent of TC-GOV-01/02.

## Execution mechanism

This mission is executed under the Supervisor/Lane-agent schema defined in the master plan's §14 (adapted from
`repository-presenter`'s own production supervision system) — see that file for the spawn recipe, lane definitions,
concurrency caps, correction ladder, and the explicit decision to defer a GitHub-Actions-based dead-man switch until
after MT069's cost redesign lands.

## Backlog Cross-Reference

This mission's root-slot takeover from `MT069-2026-09-16-GHA-MINUTES-REARCHITECTURE` follows the same disjoint-file-
scope precedent MT068 recorded taking over from MT066 itself (commit `9a2b6068c7`).
