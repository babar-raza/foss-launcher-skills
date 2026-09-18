## Mission: MT069-2026-09-16-GHA-MINUTES-REARCHITECTURE
> Investigation/plan file: `C:/Users/prora/.claude/plans/mission-audit-re-architect-swift-dongarra.md`
> Governing plan: `plans/from_backlog/2026-09-16-gha-minutes-rearchitecture.md`
> Status (updated 2026-09-18): **OPEN. PHASE A COMPLETE; PHASE B PARTIALLY EXECUTED.**
> Authoritative current state = the governing plan's "Plan File Hardening" section
> (H1-H14): graded statuses, the 19 hardening cards `HC-01..HC-19` (ledger ids
> `MT069-HC-nn-<SLUG>`), gates, evidence contract, closeout criteria, true blockers, and
> the execution loop. Ledger snapshot: `TC-01..TC-15` `IMPLEMENTED` (TC-12 closed
> 2026-09-18); `PHB-01/02/04/06/07` `IMPLEMENTED`, `PHB-05` `IN_PROGRESS`, `PHB-03`
> `IN_PROGRESS` (was `TODO`; code committed, not wired or proven), `PHB-08` `TODO`.
> **Not yet claimable:** any cost saving, or that a self-hosted job has run — both need
> `HC-02`. Superseded 2026-09-17 status (kept for the record): *"OPEN, PHASE A COMPLETE
> (TC-12 closeout in progress); Phase B seeded and authorized but not started."*
> Mission contract: root `MISSION_AUTHORITY.yaml` was bound to this mission 2026-09-16
> (override token `20260916-162212-MISSION_AUTHORITY-yaml`, since consumed against commit
> `68f45c4186`). **The root slot was later taken over by
> `MT071-2026-09-17-GOVERNANCE-DURABILITY-HARDENING`** (2026-09-17) — this mission's own
> pending contract content was preserved in that same commit before the takeover, per
> `MISSION_AUTHORITY.yaml`'s own "escalate, do not auto-force" rule (satisfied: the
> takeover was escalated to the user, not silently forced). This mission's own taskcard
> work is unaffected by the root-slot change — see the archived snapshot below, which
> remains this mission's authoritative contract record regardless of who currently holds
> the root pointer.
> Durable taskcards: `reports/plan_state/MT069-2026-09-16-GHA-MINUTES-REARCHITECTURE/taskcards.jsonl`
> Archived contract snapshot: `reports/plan_state/MT069-2026-09-16-GHA-MINUTES-REARCHITECTURE/mission_authority.yaml`
> Independent review: `reports/plan_state/MT069-2026-09-16-GHA-MINUTES-REARCHITECTURE/review/independent_review.md`
> (`TC-11`, 2026-09-17 — 7 real findings, all corrected; see that file for detail)

### Context

The user asked for a full investigation, planning, and (later, separately-gated)
execution sprint to reduce GitHub Actions minute consumption for the private
`Aspose/aspose.org` repo, which is using a substantial share of the Aspose org's included
Actions allowance and affecting other private repos. The brief specifies 19 stages across
two phases: Phase A (discovery, usage/billing measurement, per-workflow destination
decisions, execution-ready taskcards) and Phase B (controlled migration execution),
with Phase B explicitly gated behind Phase A being complete and independently reviewed.

### What was found (read-only recon, this session)

- 20 workflow files in `.github/workflows/*.yml`, all GitHub-hosted, zero matrix
  strategies, zero composite actions, zero `workflow_call` reusable workflows.
- **All 20 currently report `state: disabled_manually`** via the GitHub API, despite
  several having successful runs as recent as 2026-09-14. **User confirmed (2026-09-16)
  this was their own intentional emergency cost stopgap** — not an anomaly to
  investigate further, but the baseline fact TC-02 documents. Consequence: every
  push(main) gate is currently not enforcing anything; restoring correct gating without
  restoring the cost is a mission deliverable, not a side effect.
- `Aspose/aspose.org-workflows` is a real, **public** sibling repo already used as a
  proven "Option B" pattern: it is the actual Hugo build+deploy engine for every
  subdomain, and already hosts 5 SEO-pipeline workflow templates that check out
  `Aspose/aspose.org` via a scoped token, do work, and push results back via PR (never
  auto-commit).
- S-115 `workflow-harden` already owns static correctness/security/hygiene review of
  `.github/workflows/**` + `scripts/ci/**` (including CI-weight/caching), but explicitly
  disclaims cost/billing measurement, self-hosted-runner migration, and public-repo
  migration — this mission's actual capability-gap scope, filed as a `bounded-oneoff`
  gap-escalation report rather than a new skill.
- Real overlap risk: `MT066-2026-09-09-PACKAGE-INSTALL-RECONCILIATION` is open with a
  `READY` taskcard targeting a PR against `Aspose/aspose.org-workflows`'s deploy-trigger
  logic — a different subsystem of the same repo. Mitigated by inheriting the existing
  repo-wide norm (also declared by MT062/MT066) that any `aspose.org-workflows` PR merge
  is a standing human-authority boundary.
- Suspected top cost driver (to confirm with real usage data): `content-governance-checks.yml`
  (full Hugo build, ~30 steps) has no `concurrency: cancel-in-progress` guard against
  ~266 `content/` commits in the first 16 days of September alone — a cheap,
  `/workflow-harden`-eligible fix independent of any migration.

### Human decisions resolved (2026-09-16)

1. Disabled-workflow mass-disable: confirmed intentional user action.
2. Org-level billing access: user will pull the Billing UI export themselves rather than
   granting broader token scope.
3. Self-hosted runner candidate: this session's own Windows 11 Pro dev machine.
4. Proceed now: user chose "register the mission and start Phase A now."

### Addendum (2026-09-18): real usage data + Phase B authorization

- User supplied the org's real Actions usage metrics export (2026-09-01 through
  2026-09-18): 1,494 total minutes, 561 job runs. Top 3 workflows =
  75.7% of total: `content-governance-checks.yml` (546 min/36.5%), `llms-generation.yml`
  (259 min/17.3% — newly surfaced, not previously flagged), `skill-governance.yml`
  (326 min/21.8% combined — its Windows job costs *more* than its Linux job, reversing
  an earlier assumption). Full table and analysis in the governing plan's "Technical
  findings" section.
- User explicitly authorized seeding Phase B taskcards (`MT069-PHB-01` through
  `MT069-PHB-08`) ahead of Phase A's own completion, conditioned on personal supervision:
  a stop gate applies after every `PHB-*` taskcard — no auto-chaining to the next one
  without the user's explicit go-ahead. Recorded in `MISSION_AUTHORITY.yaml`'s
  `human_authority_boundaries` and `conflicts_found`, under override token
  `20260917-053350-MISSION_AUTHORITY-yaml`. All 8 seeded with real Phase A prerequisites
  as dependencies (e.g. `PHB-01` depends on `TC-10`) — none are actually startable yet.

### What was built (this session)

- Mission registered: `mission_authority.py allocate` → `MT069-2026-09-16-GHA-MINUTES-REARCHITECTURE`,
  `activate` (succeeded without `--force`, MT068 incumbent was unlocked), root
  `MISSION_AUTHORITY.yaml` hand-edited under override token
  `20260916-162212-MISSION_AUTHORITY-yaml`, `open` archived the snapshot.
- Phase A taskcards seeded (TC-01 through TC-15, later extended past the original 13) at
  `reports/plan_state/MT069-2026-09-16-GHA-MINUTES-REARCHITECTURE/taskcards.jsonl`, plus
  Phase B (`PHB-01..08`, seeded but not started).

### Phase A closeout (2026-09-17)

- Full inventory, real usage/billing measurement (user-supplied export), failure-signature
  analysis, importance ratings, destination decisions, threat assessment, self-hosted and
  public-migration designs, cost-telemetry proposal, and 20 per-workflow dossiers all
  complete — see the governing plan's "Durable artifact locations" for the full file list.
- **Real CI defects found and fixed, not just documented**: `TC-05`'s failure-signature
  analysis surfaced two genuine production defects behind the top-2 workflows' bad
  failure rates (a latent comparison bug in `check_platform_capabilities.py` causing a
  100% false-positive failure rate for 12 days; a missing pre-commit enforcement layer
  for `check_evaluator_version_bump.py` causing a real 49% failure rate). Both root-caused
  and fixed (`TC-14`, `TC-15`) with new regression tests, not worked around.
- **Independent review (`TC-11`) found and fixed 7 more real issues** in this mission's
  own prior work — including a genuine fail-open gap in `TC-15`'s own new pre-commit gate,
  found the same day it was added. See `review/independent_review.md` for full detail;
  nothing here is swept under the rug.
- **Known, currently-open item**: the concurrency-guard fixes on the top-3 cost-driver
  workflows (`content-governance-checks.yml`, `llms-generation.yml`,
  `skill-governance.yml`) and the `TC-14`/`TC-15` CI-checker fixes are real, tested, and
  correct, but as of this closeout are still **uncommitted working-tree edits** — not yet
  durable. Committing them was outside `TC-12`'s original file scope (governance/plan
  files only); this is flagged explicitly rather than silently left implicit.
  **[RESOLVED 2026-09-18: committed in `d795f669e6`. Committed is not the same as
  proven — none of these has executed in CI since; see `HC-02`.]**

### Deliberately out of scope, filed not fixed

- Phase B execution (actual migration/canary waves) — separately gated.
- Any change to `Aspose/aspose.org-workflows`'s deploy-trigger logic (MT066's territory).
- Registering or bringing online any self-hosted runner (design-only this mission).
- Secret rotation of anything found during the threat assessment (recommendation only).
- Re-enabling any of the 20 currently-disabled workflows (a Phase B decision per workflow).

**[SUPERSEDED 2026-09-18 for the first, third and last bullets: Phase B was authorised and
executed (9 public templates, two self-hosted runners registered — one wrongly scoped, then
fixed). The standing rule that no private workflow is enabled without an explicit human
go-ahead still applies; the user's 2026-09-18 instruction "do everything from HC-01 to
HC-19" is recorded in the plan's H14 as the go-ahead for `HC-02` only, as that card is
written.]**

### Rollout

Phase A only. No production workflow, secret, or runner configuration changes are made by
this mission. Any `.github/workflows/*.yml` edits (e.g. the `content-governance-checks.yml`
concurrency fix) are delegated to `/workflow-harden` per the existing governed skill
boundary, not made ad hoc by this mission.
