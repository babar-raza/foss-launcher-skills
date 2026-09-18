# Public-Repo Execution Boundary Design

**Mission:** MT069-2026-09-16-GHA-MINUTES-REARCHITECTURE
**Taskcard:** MT069-TC-09-PUBLIC-EXECUTION-BOUNDARY-DESIGN
**Date:** 2026-09-17
**Status:** Design only — no template deployed, no PR opened.

## Formal gate check (required before this design finalizes)

Re-ran `mission_authority.py list` and read
`reports/plan_state/MT066-2026-09-09-PACKAGE-INSTALL-RECONCILIATION/taskcards.jsonl`
directly, 2026-09-17. **Result**: `MT066-2026-09-09-PACKAGE-INSTALL-RECONCILIATION` is
still `open`; its taskcard `PKGINSTALL-DEPLOY-TRIGGER-3LAYER-FIX` is still `READY`
(queued, not started), with `allowed_paths` scoped to
`scripts/ci/checks/verify_deploy_trigger.py` and
`Aspose/aspose.org-workflows:scripts/deploy/detect_changes.py` — confirmed a different
subsystem of `Aspose/aspose.org-workflows` than anything this design touches (the SEO
templates directory and any new canary workflow templates under
`Aspose/aspose.org-workflows/.github/workflows/`). No overlap. Re-check this again
immediately before any real PR opens in Phase B, not just once here.

## Roster (3 tiers)

| Tier | Workflows | Real cost share | What's needed |
|---|---|---:|---|
| Clean — move as-is | `aspose-com-targets-watch.yml`, `backlink-compliance-watch.yml`, `seo-analysis.yml` (rename first) | ~2.9% combined | Reuse the proven SEO-template pattern as-is |
| Needs a product decision | `upstream-monitor.yml`, `maven-publish-watcher.yml`, `install-literal-sweep.yml`, `package-publish-watch.yml` | ~3.2% combined | User's still-open auto-commit→PR-gated decision (see Human Decisions) |
| Partial split | `ci-eval-consistency.yml`, `launch-dashboard.yml` | ~2.8% combined | File split (push/PR leg stays private, schedule leg can move), not a pure copy |

**Not candidates**: `content-governance-checks.yml`, `skill-governance.yml` (self-host
targets, see `TC-08`), `content-audit.yml` (dead), and the remaining push/PR-gated
workflows (all need native required-check integration a workflow in another repo
cannot provide).

**Two workflows excluded from migration entirely pending a correctness fix**:
`upstream-monitor.yml` and `launch-dashboard.yml` are `REQUIRES_REDESIGN` per
`analysis/destination_decision_matrix.json` (93%/100% failure rates, root-caused by
`TC-05`) — `launch-dashboard.yml`'s cause (missing `pip install`, HP-11) is fixed-ready
pending source verification; `upstream-monitor.yml`'s cause (HP-05, a documented PAT
gap) needs a human decision. Neither should be migrated while broken — relocating a
broken workflow doesn't fix it.

## Mechanism (reuses the proven SEO-template pattern — nothing new to invent)

1. Copy the workflow into a new local template directory,
   `scripts/ci/deployed-workflows/` (parallel to `scripts/seo/workflows/`), pointing
   `actions/checkout@v4` at `repository: Aspose/aspose.org` with the token already
   present in `Aspose/aspose.org-workflows` (`REPO_TOKEN`/`GH_TOKEN`) — no new secret.
2. Hand-copy-deploy into `Aspose/aspose.org-workflows/.github/workflows/`, matching
   today's SEO-template convention.
3. Extend `scripts/ci/checks/check_workflow_drift.py`'s coverage to the new template
   directory.
4. Flip the private original's trigger to `workflow_dispatch`-only (currently a no-op
   since all 20 are disabled) — a pure YAML edit, does not enable anything (Hard
   Constraint).
5. Clean-tier workflows keep read+report behavior unchanged; needs-decision-tier
   workflows switch from auto-commit to opening a branch + PR, mirroring the SEO
   workflows exactly — never auto-commit from the public side.
6. Prove attribution before trusting it (see Canary below).

## Threat assessment — see `analysis/threat_assessment.md`

Already produced by `TC-07`; not duplicated here. Summary: no new secret exposure
found for the clean tier (reuses the already-deployed `REPO_TOKEN`); one open item on
`seo-analysis.yml`'s public artifact upload needing content review; the four
`contents: write` auto-commit bots need the user's product decision before any public
threat-model re-examination is meaningful.

## Canary

`aspose-com-targets-watch.yml` — daily cadence, read+report-only permissions,
structurally incapable of corrupting the repo, no cross-repo secrets beyond the
checkout token already proven. Deploy a template copy, extend the drift checker, run
5-7 daily cycles, prove attribution three ways (runs land publicly, stop appearing
privately, billing trend flat/down for that slot).

**The actual execution of this migration (including how attribution is proven durably,
not as a one-time manual check) is governed by the migration-run state machine designed
in the Phase B section of the governing plan** — this design document is the Phase A
input to that machine's `TEMPLATE_BUILT`/`CANARY_DEPLOYED` states, not a replacement for
it.

## Order

`aspose-com-targets-watch.yml` (canary) → `backlink-compliance-watch.yml` →
`seo-analysis.yml` (after rename) → the 4 watcher bots, pending the user's decision →
the 2 partial-split workflows last. Each migration proven individually before the next
starts — never migrate several at once.

## What this taskcard does NOT do

- No template deployed to `Aspose/aspose.org-workflows`.
- No PR opened against that repo (human-authority boundary, inherited repo-wide norm).
- No workflow trigger changed.

This is `MT069-PHB-04`/`PHB-05`/`PHB-06`'s design input for eventual Phase B execution.
