---
name: blind-spot-audit
id: S-122
description: >
  Read-only, unaided (no-tooling) dual-pass review of one or more products' cloned FOSS
  repos and generated content, sealed before any system tooling runs, then a system-tooling
  pass, a manual-vs-system blind-spot comparison matrix, root-cause analysis, solution-
  options fix planning, and schema-5f taskcard emission via the registered run-bound
  blind_spot_audit_run.py state machine.
args: "--products family/platform [family/platform ...] --mission-id ID [--run-id ID] [--session-id ID]"
---

<!-- CONTRACT: registered-cli-wrapper
     purpose: measure where system tooling is blind relative to a careful unaided reading pass,
              and emit schema-5f taskcards for the gaps found
     preconditions: an open mission (MISSION_AUTHORITY.yaml shape) with a mission_id to bind taskcards into
     postcondition: run reaches TASKCARDS_BOUND, BLOCKED_UNAIDED_FIRST, or ABANDONED
     idempotent: yes — immutable per-run evidence, single global-lock ownership
     verified: 2026-08-09
-->

# S-122: Blind-Spot Audit

**Arguments**: `--products family/platform [family/platform ...] --mission-id ID`

## Why this skill exists

No skill in this repo produces a measured, provable answer to "where is our own tooling
blind" — every existing evaluator/comparator/extractor runs alone, with nothing checking its
findings against a genuinely tooling-free reading pass. This skill formalizes a mission the
operator ran once by hand, ungoverned, at
`.local/evidences/foss-manual-system-heal-v2-20260617/`: real value (a measured
human-found/system-missed rate, real root causes), and real governance gaps (its taskcards
never reached schema 5f, one card sat at `TODO` at "closeout", a blocker went untracked).
This skill's whole reason to exist is the **seal** — see below — that makes the comparison
scientifically meaningful instead of an agent's impression. Full design: plan
`typed-snuggling-peach.md`; mission `MT025-2026-08-08-FORENSIC-BLIND-SPOT-HEAL-SKILLS`.

**Effect boundary**: this skill is read-only with respect to `content/`, `scripts/`,
`knowledge/`, and `skills/`. It writes only its own run evidence
(`reports/blind_spot_audit/{run_id}/`) and schema-5f taskcard rows
(`reports/plan_state/{mission_id}/taskcards.jsonl`, via `TaskcardStore` — never a parallel
scheme). Executing the fixes it finds is **S-123 forensic-heal-sprint**'s job, a separate
skill that consumes the taskcards this one emits.

**Terminology note (AGENTS.md §7c reconciliation)**: this skill's `unaided-repo` and
`unaided-content` phases are always called **"unaided,"** never "manual review." §7c already
defines "manual review required" to mean *"invoke S-90"* — a human-judgment delegation. This
skill's unaided window is the opposite axis: an agent deliberately withholding tooling while
still exercising its own judgment. Do not describe these phases as "manual review" in any
evidence artifact or commit message; it will misleadingly read as a §7c violation.

## Official execution contract

Use only the registered control plane:

```bash
.venv/Scripts/python scripts/pipeline/commands/diagnostics/blind_spot_audit_run.py open \
  --products family/platform [family/platform ...] --mission-id ID [--run-id ID] [--session-id ID]
.venv/Scripts/python scripts/pipeline/commands/diagnostics/blind_spot_audit_run.py advance \
  --run-id ID --phase PHASE [--session-id ID] [--evidence-file PATH]
.venv/Scripts/python scripts/pipeline/commands/diagnostics/blind_spot_audit_run.py recheck \
  --run-id ID
.venv/Scripts/python scripts/pipeline/commands/diagnostics/blind_spot_audit_run.py seal \
  --run-id ID [--session-id ID] [--override-reason TEXT]
.venv/Scripts/python scripts/pipeline/commands/diagnostics/blind_spot_audit_run.py bind-taskcards \
  --run-id ID [--session-id ID]
.venv/Scripts/python scripts/pipeline/commands/diagnostics/blind_spot_audit_run.py close \
  --run-id ID
.venv/Scripts/python scripts/pipeline/commands/diagnostics/blind_spot_audit_run.py status \
  --run-id ID
.venv/Scripts/python scripts/pipeline/commands/diagnostics/blind_spot_audit_run.py abandon \
  --run-id ID --reason TEXT
```

`PHASE` (strict order, no skipping, no re-entry): `intake → scope → unaided-repo →
unaided-content → agentic-consumption → [seal] → system-review → blind-spots → root-cause →
fix-plan → [bind-taskcards]`. `seal` and `bind-taskcards` are dedicated verbs, not
`advance --phase` targets — `advance` refuses both explicitly and names the real command.
`blind-spots`, `root-cause`, and `fix-plan` require `--evidence-file PATH` (a JSON file the
agent prepares; shapes below) — `advance` validates it and refuses the transition entirely on
any error, never partially. Every mutating call requires a stable session identity
(`--session-id` or `AGENT_SESSION_ID`/`CODEX_THREAD_ID`/`CLAUDE_CODE_SESSION_ID`). One global
`ACTIVE.json` + `FileLock` prevents two sessions running a blind-spot-audit concurrently.

## The unaided-first gate (`seal`)

Four layers make "review before touching any tooling" an audited property, not a requested
one:

- **L1 — structural ordering.** `advance` refuses any `system-review`-onward phase while the
  run has never been sealed (`"sealed_at" not in manifest`, checked on every POST-window
  phase, not just the first).
- **L2 — skill-invocation ledger audit.** At `seal`, every
  `reports/skill-context/history/*.json` and `reports/skill-runs/*.json` record started
  inside the unaided window is checked against a fixed `SYSTEM_TOOLING_SKILL_IDS` set
  (every evaluator/comparator/extractor/governed-review skill, including S-34 `repo-scout` —
  letting the extractor pre-digest the FOSS repos defeats the point of an unaided read).
- **L3 — artifact-mtime forensics.** `SYSTEM_ARTIFACT_ROOTS` (`reports/audit`, `reports/
  content_eval`, `reports/gap-eval`, `reports/truth-audit`, `reports/publish-review`,
  `reports/system-heal`, `reports/sprint`, plus depth-bounded census of `runs/` and
  `knowledge/`) is censused when the unaided window opens (entering `unaided-repo`, not at
  `open`, since `intake`/`scope` may legitimately use S-92/S-93/S-94) and re-censused at
  `seal`; any new or touched file/subtree is a violation.
- **L4 — scope narrowing (operator convention, not code-enforced).** Run the unaided phases
  under a narrow `skill_context.py` scope that cannot write system-tooling outputs:
  ```bash
  PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-122 --scope "reports/blind_spot_audit/*"
  ```
  then re-open widened after `seal` succeeds. L2+L3 are the machine-independent backstops
  for exactly the case where this convention wasn't followed.

Verdict: `UNAIDED_FIRST_CLEAN | VIOLATED | UNPROVABLE` — an unreadable/absent ledger reports
**UNPROVABLE, never a silent CLEAN**; a proven violation always outranks UNPROVABLE. Non-CLEAN
moves the run to `BLOCKED_UNAIDED_FIRST`; the only exits are `abandon` or retrying
`seal --override-reason TEXT`, which seals anyway but permanently records the violation for
S-123's verdict computation to cap at `SYSTEM_HEALED_WITH_LIMITATIONS`.

## Steps

1. **`open`** — pins git `HEAD`, single-owner-locks via `ACTIVE.json`, lands on `intake`.
2. **`advance --phase scope`** — build scope (products × pages × knowledge freshness); may
   legitimately reuse `data/products.json`, S-93/S-94.
3. **`advance --phase unaided-repo`** — opens the unaided window (L3 baseline census taken
   here). Read the cloned FOSS repo(s) under `runs/.clone_cache/{repo}/` directly, with no
   tooling — not even S-34 `repo-scout`. Write a capability summary per product.
4. **`advance --phase unaided-content`** — read the generated `content/**` pages for the
   scoped products as a careful technical editor, still with no tooling. Record findings as
   `FND-{family}-{platform}-NNN` with `family`, `platform`, `page`, `issue_type` (bounded
   vocabulary — see `blind_spot_matrix.ISSUE_TYPE_VOCABULARY`; an issue outside it is
   reported, not silently dropped, but excluded from the rate calculations).
5. **`advance --phase agentic-consumption`** — judge whether the unaided artifacts and
   evidence themselves are usable by a future agent (stable IDs, evidence-block validity,
   `model.yaml` SHA integrity).
6. **`seal`** — the hard gate above. On `BLOCKED_UNAIDED_FIRST`, either `abandon` or retry
   with `--override-reason`.
7. **`advance --phase system-review`** — now, and only now, run the real system tooling
   (S-23, S-32, S-51, S-85, S-43 `gap-eval`, S-90) against the same scope. Collect
   `SFND-NNN` findings in the same shape as the unaided findings.
8. **`advance --phase blind-spots --evidence-file PATH`** — `PATH` JSON:
   `{"unaided_findings": [{finding_id, family, platform, page, issue_type, verdict?}, ...],
   "system_findings": [...]}`. Joined on `(family, platform, page, issue_type)` into
   `BOTH | UNAIDED_ONLY | SYSTEM_ONLY | CONTRADICTORY`, with a `system_recall` metric.
   Refuses if any finding is unaccounted for in the output (completeness assertion).
9. **`advance --phase root-cause --evidence-file PATH`** — `PATH` JSON:
   `{"root_causes": [{root_cause_id, layer (skill|script|prompt|validator|governance_doc|
   data), file_ref, finding_ids, why_root_cause_not_symptom, fix_direction,
   risk_if_unfixed, evidence?}, ...]}`. Reuse S-67 `diagnose-skill-failure` per finding, S-45
   `gap-report` for cross-finding synthesis. Not every finding needs a root cause yet at
   this phase (warnings, not errors, for unexplained findings).
10. **`advance --phase fix-plan --evidence-file PATH`** — `PATH` JSON:
    `{"fix_plan_items": [{title, root_cause_id, finding_ids, layer, priority (P0-P4),
    allowed_paths, forbidden_paths?, verification_commands, rollback,
    affected_content_paths?, regeneration_required?, options: [{correctness, scope,
    maintainability, risk, repeatability, verification_cost, selected}, ...]}, ...]}`. Each
    item needs **≥2 options** and **exactly one `selected: true`** — refused otherwise.
11. **`bind-taskcards`** — converts each item's selected option into a schema-5f taskcard
    (status `TODO`) and appends every card via `TaskcardStore(mission_id)` — the one
    sanctioned writer. Terminal: `TASKCARDS_BOUND`.
12. **`close`** — read-only confirmation the terminal phase was reached.

## Post-conditions

- `TASKCARDS_BOUND`: every fix-plan item is a real `TODO` row in
  `reports/plan_state/{mission_id}/taskcards.jsonl`, ready for S-123.
- `BLOCKED_UNAIDED_FIRST`: the unaided-first gate failed; nothing past `seal` has run.

## Error handling

- `open`: raises if another session's run is active and non-terminal, or if
  `--mission-id`/`--products` is missing/empty.
- `advance`: raises on out-of-order phases, on a POST-window phase before `seal`, and (for
  `blind-spots`/`root-cause`/`fix-plan`) on missing/invalid `--evidence-file` content —
  never partially writes phase evidence on a validation failure.
- `seal`: raises listing every L2/L3 violation on `VIOLATED`/`UNPROVABLE` without
  `--override-reason`; the run moves to `BLOCKED_UNAIDED_FIRST` either way.
- `bind-taskcards`: raises if any fix-plan item's shape fails schema-5f validation — no
  partial taskcard set is ever written.

## Reuse boundary (anti-proliferation)

- **S-34 `repo-scout`**: automated API-surface extraction — the tooling this skill's
  unaided-repo phase deliberately does *not* use.
- **S-90 `publish-readiness-review`**: governed, tooling-assisted page inspection — a
  different axis from this skill's unaided read (see terminology note above).
- **S-87 `system-heal`**, **S-99 `pipeline-harden`**: content/pipeline-code healing
  execution. This skill never fixes anything — it only measures and emits taskcards; S-123
  `forensic-heal-sprint` (a separate skill) consumes them and dispatches to S-87/S-99.
