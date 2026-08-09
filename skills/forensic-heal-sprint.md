---
name: forensic-heal-sprint
id: S-123
description: >
  Consumes a mission's schema-5f taskcards (typically emitted by S-122 blind-spot-audit)
  and drives them through system-heal, content-regen, verify, harden, reverify, a 7-link
  pilot chain, 12 named adversarial probes, and computed (never asserted) dual verdicts,
  appending one tracked row to docs/governance/forensic-heal-history.md on close.
args: "--mission-id ID [--task-ids ID [ID ...]]"
---

<!-- CONTRACT: registered-cli-wrapper
     purpose: drive a mission's bound taskcards through the full heal-verify-harden-pilot-
              adversarial-close lifecycle and emit a durable, computed verdict
     preconditions: taskcards already bound for mission_id (typically via S-122 bind-taskcards)
     postcondition: every in-scope taskcard reaches CLOSED (or an explicit exception status),
                    a computed verdict is recorded, one tracked history row is appended
     idempotent: yes -- state is entirely TaskcardStore's; re-running status/gate/verdict
                 computation never mutates anything by itself
     verified: 2026-08-09
-->

# S-123: Forensic Heal Sprint

**Arguments**: `--mission-id ID [--task-ids ID [ID ...]]`

## Why this skill exists

S-122 `blind-spot-audit` measures where system tooling is blind and emits taskcards for
the gaps found — it never fixes anything. This skill is what actually drives those fixes
to closure, with two properties nothing else in this repo provides in combination: (1) a
mechanically enforced **system-before-content** ordering (fix the machinery before
regenerating affected content, never the reverse), and (2) a **computed, never asserted**
final verdict, so `SYSTEM_HEALED_READY_FOR_NEXT_LAUNCH` can only be true if every input
that would make it true actually is. Full design: plan `typed-snuggling-peach.md`; mission
`MT025-2026-08-08-FORENSIC-BLIND-SPOT-HEAL-SKILLS`.

**No independent state.** Unlike S-122, this skill has no manifest, no `run_id`, no
`ACTIVE.json`. Its entire state lives in `TaskcardStore` (schema 5f) — recomputed fresh
from `reports/plan_state/{mission_id}/taskcards.jsonl` on every call, never cached or
stored separately, per AGENTS.md §17's prohibition on parallel trackers. Its only
mutations are CAS-protected taskcard status rows and append-only rows in the one tracked
`docs/governance/forensic-heal-history.md` ledger.

## Official execution contract

```bash
.venv/Scripts/python scripts/pipeline/commands/governance/forensic_heal_sprint_run.py status \
  --mission-id ID [--task-ids ID [ID ...]]
.venv/Scripts/python scripts/pipeline/commands/governance/forensic_heal_sprint_run.py gate \
  --mission-id ID [--task-ids ID [ID ...]] [--fail-on-block]
.venv/Scripts/python scripts/pipeline/commands/governance/forensic_heal_sprint_run.py advance-taskcard \
  --mission-id ID --task-id ID --expected-status STATUS --new-status STATUS --evidence PATH [PATH ...] [--session-id ID]
.venv/Scripts/python scripts/pipeline/commands/governance/forensic_heal_sprint_run.py pilot-check \
  --chain-file PATH
.venv/Scripts/python scripts/pipeline/commands/governance/forensic_heal_sprint_run.py adversarial-review \
  --evidence-file PATH --sealing-session-id ID [--reviewer-session-id ID] [--prior-dispositions-file PATH]
.venv/Scripts/python scripts/pipeline/commands/governance/forensic_heal_sprint_run.py compute-verdict \
  --mission-id ID --gate-passed true|false --pilot-resolved true|false --adversarial-review-file PATH \
  [--unaided-first-override-file PATH] [--task-ids ID [ID ...]]
.venv/Scripts/python scripts/pipeline/commands/governance/forensic_heal_sprint_run.py close \
  --mission-id ID --products family/platform [family/platform ...] --gate-passed true|false \
  --pilot-resolved true|false --adversarial-review-file PATH --unaided-first-verdict VERDICT \
  [--system-recall FLOAT] [--unaided-first-override-file PATH] [--task-ids ID [ID ...]]
```

## Steps

1. **`status`** — derived sprint-state: the MINIMUM progress rank across in-scope
   schema-5f taskcards. Any card in `BLOCKED_EXTERNAL`/`BLOCKED_LOCAL`/`REWORK_REQUIRED`
   forces the aggregate directly to that exception status (`BLOCKED_EXTERNAL` dominant if
   more than one is present); `SUPERSEDED`/`OUT_OF_SCOPE` cards are excluded, not counted.

2. **System healing** (dispatch to S-99 `pipeline-harden` for pipeline code, S-67
   `diagnose-skill-failure`/direct edits for skills/prompts/validators/governance docs —
   not this skill's own code path). Advance each system-layer taskcard
   (`layer` ∈ `script`/`prompt`/`validator`/`governance_doc`/`skill`) through
   `advance-taskcard` up to `IMPLEMENTED`.

3. **`gate --fail-on-block`** — **the system-before-content gate**, the one load-bearing
   new invariant this skill enforces. Refuses (exit 1, lists every blocking card) unless
   every in-scope system-layer taskcard has reached `IMPLEMENTED`. A `data`-layer taskcard
   never blocks this gate. Do not proceed to content regeneration while this fails.

4. **Content regeneration** (dispatch to S-87 `system-heal`, S-62 `batch-reference`,
   `refresh-product`, S-20/S-21 — this skill never authors content itself). Advance each
   taskcard's status accordingly; record `system_heal_evidence_at` /
   `content_regen_evidence_at` / `before_hash` / `after_hash` fields (via `--evidence`
   extras on `advance-taskcard`) — these feed A-09/A-10 below.

5. **Verification / hardening / reverification** (dispatch to S-23/S-51/S-32, S-99, and
   the mission's own `pytest`) — advance taskcards through `FOCUSED_VERIFIED` →
   `INTEGRATION_VERIFIED` → `END_TO_END_VERIFIED`.

6. **`pilot-check --chain-file PATH`** — `PATH` JSON: `{unaided_finding_id, root_cause_id,
   task_id, system_fix_diff_ref, regen_command, verification_before_hash,
   verification_after_hash, agentic_consumption_recheck_passed}`. All 7 links must resolve
   — an identical before/after hash pair does **not** count as verified. Advance the
   piloted card(s) to `PILOT_PROVEN` once resolved.

7. **`adversarial-review --evidence-file PATH --sealing-session-id ID`** — **must run
   under a session distinct from whichever session drove steps 2-6** (refused otherwise,
   independence enforced not requested — the S-116 "fresh context" pattern made
   mechanical). `PATH` JSON: one key per probe ID `A-01`..`A-12` (see
   `adversarial_probes.py` docstrings for each probe's exact evidence shape). Re-run after
   remediating any `BLOCKER`, passing `--prior-dispositions-file` (the first run's
   `{probe_id: disposition}` map) so a fixed probe reports `REPAIRED`, not a fresh
   `DISPROVEN_WITH_EVIDENCE` that erases the fact it needed fixing. Advance taskcards to
   `INDEPENDENTLY_REVIEWED` once `any_blocker` is `false`.

8. **`compute-verdict`** — computes `human_readiness_verdict`, `agentic_consumption_verdict`,
   and `final_verdict` from the mission's real current `status`, the gate result, the pilot
   result, and the adversarial-review result. **Never pass a verdict as an asserted
   field anywhere** — there is no code path in this skill that accepts one.
   `BLOCKED_EXTERNAL` always outranks every other signal; any adversarial `BLOCKER`, a
   failed gate, or a `BLOCKED_LOCAL`/`REWORK_REQUIRED` taskcard forces
   `SYSTEM_NOT_READY_REWORK_REQUIRED`; an unaided-first override (from S-122's `seal
   --override-reason`), an unresolved pilot chain, a `REPAIRED` probe, or a non-`CLOSED`
   sprint aggregate all cap the outcome at `*_WITH_LIMITATIONS`.

9. **`close`** — recomputes the verdict and appends one row to the tracked
   `docs/governance/forensic-heal-history.md` ledger **regardless of what the verdict is**
   — a failing sprint is still a real, tracked outcome, never hidden. Advance every
   in-scope taskcard to `CLOSED` (via `advance-taskcard`) before or alongside this call.

## Post-conditions

- Every in-scope taskcard is `CLOSED` (or an explicitly exempted exception status).
- One new row exists in `docs/governance/forensic-heal-history.md` with a verdict that is
  a pure function of the recorded gate/pilot/adversarial/sprint-state inputs.

## Error handling

- `status`/`gate`: raise if the mission has no taskcards at all, or if an explicit
  `--task-ids` selection references an unknown task_id.
- `advance-taskcard`: CAS-protected — a stale `--expected-status` is refused with the
  actual current status and who last recorded it, never silently overwritten.
- `adversarial-review`: raises if `--reviewer-session-id` (or the resolved session
  identity) equals `--sealing-session-id`.
- `close`: does not suppress or special-case a `SYSTEM_NOT_READY_REWORK_REQUIRED` or
  `BLOCKED_EXTERNAL` outcome — it is written to the ledger exactly like a passing one.

## Reuse boundary (anti-proliferation)

- **S-87 `system-heal`**: the actual content-healing execution this skill dispatches to
  in step 4 — never reimplemented here.
- **S-99 `pipeline-harden`**: the actual pipeline-code hardening execution this skill
  dispatches to in steps 2 and 5 — never reimplemented here.
- **S-116 `seo-review`**: the fresh-context independent-review pattern step 7's session-
  independence enforcement is modeled on.
- **S-122 `blind-spot-audit`**: the upstream skill that typically produces this skill's
  input taskcards. This skill never performs an unaided review itself.
