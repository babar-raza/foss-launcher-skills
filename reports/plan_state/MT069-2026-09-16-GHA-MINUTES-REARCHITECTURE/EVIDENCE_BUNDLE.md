# Evidence Bundle: MT069-2026-09-16-GHA-MINUTES-REARCHITECTURE (Phase A)

**Local root (this machine only — `reports/` is gitignored by repo policy):**
`D:\onedrive\Documents\GitHub\aspose.org\reports\plan_state\MT069-2026-09-16-GHA-MINUTES-REARCHITECTURE\`

**Mission**: GitHub Actions Audit, Re-Architecture, Migration & Stabilization —
`aspose.org`. **Phase**: A (investigation → execution-ready plan), complete as of
2026-09-17. **Governing plan**:
`D:\onedrive\Documents\GitHub\aspose.org\plans\from_backlog\2026-09-16-gha-minutes-rearchitecture.md`.

## Governance

| Artifact | Absolute path |
|---|---|
| Taskcard ledger | `D:\onedrive\Documents\GitHub\aspose.org\reports\plan_state\MT069-2026-09-16-GHA-MINUTES-REARCHITECTURE\taskcards.jsonl` |
| Archived mission-contract snapshot | `D:\onedrive\Documents\GitHub\aspose.org\reports\plan_state\MT069-2026-09-16-GHA-MINUTES-REARCHITECTURE\mission_authority.yaml` |
| Mission narrative | `D:\onedrive\Documents\GitHub\aspose.org\plans\missions\MT069-2026-09-16-GHA-MINUTES-REARCHITECTURE.md` |
| Master-plan index entry | `D:\onedrive\Documents\GitHub\aspose.org\plans\master-plan.md` (row for this mission) |
| Governing plan | `D:\onedrive\Documents\GitHub\aspose.org\plans\from_backlog\2026-09-16-gha-minutes-rearchitecture.md` |

**Note on the root `MISSION_AUTHORITY.yaml`**: this mission's own pending contract
content was durably preserved via commit `68f45c4186` before the root slot was taken
over by `MT071-2026-09-17-GOVERNANCE-DURABILITY-HARDENING` on 2026-09-17. The override
token `20260916-162212-MISSION_AUTHORITY-yaml` is already consumed against that commit
(`reports/overrides/archived/20260916-162212-MISSION_AUTHORITY-yaml.json`). This
mission's `TC-12` closeout therefore does **not** touch the current root
`MISSION_AUTHORITY.yaml` (it now holds MT071's contract, not this mission's) — this
mission's own taskcard work is governed by its own archived snapshot above, which
remains valid regardless of who currently holds the root pointer, per the plan's own
pre-written contingency for this exact situation.

## Inventory and disposition (TC-01–TC-03)

| Artifact | Absolute path |
|---|---|
| Structured workflow inventory | `...\inventory\workflows_inventory.json` |
| Disabled-vs-running anomaly write-up | `...\inventory\disabled_vs_running_anomaly.md` |
| `/workflow-harden` evidence bundle (TC-03) | `D:\onedrive\Documents\GitHub\aspose.org\reports\sprint\workflow-harden-2026-09-17\` |

*(`...` = `D:\onedrive\Documents\GitHub\aspose.org\reports\plan_state\MT069-2026-09-16-GHA-MINUTES-REARCHITECTURE\`, same for all rows below.)*

## Usage, failure, and importance analysis (TC-04–TC-06)

| Artifact | Absolute path |
|---|---|
| Real usage dataset (user-supplied export) | `...\usage\usage_dataset.json` |
| Billing reconciliation | `...\usage\billing_reconciliation.md` |
| Failure-signature analysis | `...\analysis\failure_signatures.json` |
| Importance matrix | `...\analysis\importance_matrix.json` |

## CI defect remediation (TC-14, TC-15 — branched off TC-05's findings)

| Artifact | Absolute path |
|---|---|
| TC-14 fix evidence (platform-capabilities checker bug) | `...\ci_defect_remediation\TC-14_platform_capabilities_fix.md` |
| TC-15 fix evidence (evaluator-version-bump shift-left + TC-11 followup fail-open fix) | `...\ci_defect_remediation\TC-15_evaluator_version_bump_shift_left.md` |
| Code changed (still uncommitted — see "Open items" below) | `scripts/ci/checks/check_platform_capabilities.py`, `scripts/ci/tests/test_check_platform_capabilities.py`, `scripts/ci/checks/check_evaluator_version_bump.py`, `scripts/pre-commit-audit.sh`, `scripts/ci/tests/test_check_evaluator_version_bump.py` (new), `scripts/ci/hooks/simulate_pr_checks.sh`, `docs/development/evaluator-changes.md` |

## Destination decisions and designs (TC-07–TC-09, TC-13)

| Artifact | Absolute path |
|---|---|
| Destination decision matrix | `...\analysis\destination_decision_matrix.json` |
| Threat assessment | `...\analysis\threat_assessment.md` |
| Self-hosted runner architecture | `...\design\self_hosted_architecture.md` |
| Public-repo migration boundary | `...\design\public_execution_boundary.md` |
| Cost-telemetry proposal | `...\design\cost_telemetry_proposal.md` |
| Second gap-escalation report (`recurring-candidate`) | `reports\skill-gaps\2026-09-17-gha-cost-and-ci-health-telemetry.md` |

## Per-workflow dossiers (TC-10) — 20 of 20 workflows covered

`...\dossiers\{act-pipeline, aspose-com-targets-watch, backlink-compliance-watch,
ci-eval-consistency, content-audit, content-governance-checks, cross-repo-index-sync,
example-verification-tests, extraction-pipeline, install-literal-sweep,
launch-dashboard, llms-generation, maven-publish-watcher, metrics-governance,
package-publish-watch, reference-index-structure, seo-analysis, seo-tests,
skill-governance, upstream-monitor}.md`

## Independent review (TC-11)

| Artifact | Absolute path |
|---|---|
| Independent review report | `...\review\independent_review.md` |

7 real findings, all corrected in-place across the artifacts above (not just logged).
See the report for full detail and verification of each.

## Verification checklist (per the plan's "Single-go execution gate sequence")

- [x] Every workflow (20) has a dossier with a cited destination decision — none left at
  `INSUFFICIENT_EVIDENCE` without a stated reason (2 genuinely provisional:
  `install-literal-sweep.yml`'s migration decision pending an open product decision plus
  no real-run track record yet; the auto-commit→PR-gated question for 4 watcher bots).
- [x] Every destination recommending public or self-hosted execution cites a completed
  threat assessment naming secrets/credentials/data classes exposed (`analysis/threat_assessment.md`).
- [x] Independent review completed with no open `CONFIRMED` findings (`TC-11`, all 7 fixed).
- [x] `TC-03` cites the `/workflow-harden` evidence bundle
  (`reports/sprint/workflow-harden-2026-09-17/`) rather than re-deriving its results.
- [x] MT066's status was re-checked before `TC-09` finalized (`design/public_execution_boundary.md`).
- [x] `check_plan_taskcard_completeness.py` passes: 15 execution-order steps ≤ 23 distinct
  taskcards.

## Open items carried forward (not closed by Phase A, by design)

1. **Concurrency-guard fixes and CI-checker fixes are real but uncommitted.** All files
   listed under "CI defect remediation" above, plus `.github/workflows/
   content-governance-checks.yml`, `llms-generation.yml`, `skill-governance.yml`, are
   currently uncommitted working-tree edits (`git status --porcelain` shows `M`). This is
   a real, open precondition for `PHB-07`'s self-hosted cutover — flagged explicitly, not
   silently assumed satisfied. Committing these was outside `TC-12`'s own file scope
   (governance/plan files only) and needs an explicit decision on scope/timing.
2. **`llms-generation.yml` needs a real redesign**, not a destination decision alone —
   see `dossiers/llms-generation.md` §12-13. Not implemented in Phase A.
3. **`install-literal-sweep.yml`'s actual operability** is still unobserved (only ever
   had one possible firing, timing unclear whether it landed before the mass-disable) —
   confirm once workflows are re-enabled.
4. **UPDATE (2026-09-18, superseded same day)**: `upstream-monitor.yml`'s believed
   "PAT gap" (issue #94) reproduced identically post-migration, as expected at the
   time. **CORRECTED later the same day**: this was never a PAT gap. Real cause
   (direct source read + live repro): `clone_exists()` is a pure filesystem check
   against the gitignored `runs/.clone_cache/`, never present on a fresh checkout,
   zero token involvement. Fixed in `Aspose/aspose.org` commit `72821fbb4a`; the
   already-migrated public copy picks up the fix automatically on its next run
   since it checks out `Aspose/aspose.org` fresh each time. Issue #94 should be
   closed as a misdiagnosis.
   `launch-dashboard.yml`'s original "missing pip install" theory was disproved, but a
   deeper, real defect was found instead (its inputs are gitignored local state, never
   available in any fresh checkout) — still `REQUIRES_REDESIGN`, for the corrected
   reason. See `dossiers/launch-dashboard.md` for the full two-pass correction history.
5. **Docker Desktop licensing** for the self-hosted runner design — resolved by
   construction 2026-09-17 (`PHB-07`): the runner uses this machine's existing Docker
   Desktop instance, not a new install, so no new licensing exposure was introduced.
6. **`AGENTS.md` §9a's dead link** — human action item, not agent-executable.
7. **Phase B (`PHB-01..08`)** — seeded and authorized, not started. Stop-gate applies
   after every taskcard per the user's standing supervision requirement.
