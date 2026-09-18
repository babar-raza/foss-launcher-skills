# Disabled-vs-Running Anomaly — Resolved

**Mission:** MT069-2026-09-16-GHA-MINUTES-REARCHITECTURE
**Taskcard:** MT069-TC-02-DISABLED-VS-RUNNING-ANOMALY
**Date:** 2026-09-16

## Finding

`gh workflow list --repo Aspose/aspose.org --all` shows all 20 file-defined workflows in
`.github/workflows/*.yml` reporting `state: disabled_manually`. `gh run list --repo
Aspose/aspose.org --limit 15` shows several of the same workflows (Eval Rerun Consistency,
LLMs Output Regeneration, Content Governance Checks, Backlink Compliance Watch, aspose.com
Targets Watch, Package Publish Watch, Maven Publish Watcher) with successful completed runs
as recent as 2026-09-14 — two days before this session (today: 2026-09-16). The only
workflow GitHub reports `active` is its own synthetic Dependabot "Dependency Graph" entry,
not one of the 20 files.

## Resolution

**Confirmed directly with the user in this session (2026-09-16): this was an intentional
action.** The user manually disabled all 20 workflows themselves as an emergency stopgap in
direct reaction to the GitHub Actions-minutes cost problem that motivated this mission. This
is not an unexplained anomaly, a GitHub-side bug, or a concurrent-session accident — it is
the deliberate baseline state this mission was commissioned to address.

## Consequences applied to Phase A

1. **No workflow is treated as "currently healthy" or "currently unhealthy" based on its
   disabled state.** Health/importance/failure-rate analysis (TC-05, TC-06) uses historical
   run data from before the disable, not current live state.
2. **Every push(main) gate is presently not enforcing anything.** `content-governance-checks.yml`,
   `skill-governance.yml`, `metrics-governance.yml`, and every other push-triggered gate in
   this repo are disabled — commits to `main` are currently ungated. Restoring correct
   gating *without* restoring the prior cost is treated as a co-equal mission deliverable
   (recorded in `MISSION_AUTHORITY.yaml`'s `mission_summary` and `out_of_scope_items` —
   re-enabling any specific workflow stays a per-workflow Phase B decision, not a side
   effect of this investigation).
3. **Live usage currently reads as ~zero for everything.** TC-04's usage/billing collection
   must reconstruct minutes from historical run/job data (before the mass-disable), and must
   separately confirm this repo's Actions run-history retention window so that historical
   reconstruction can actually reach back far enough.
4. **No workflow will be re-enabled by this mission.** Re-enabling, migrating, or retiring
   each workflow remains an individual, evidence-backed Phase B decision per
   `MISSION_AUTHORITY.yaml`'s `out_of_scope_items`.

## Evidence

- `gh workflow list --repo Aspose/aspose.org --all` output (captured in this session,
  reproduced in `reports/plan_state/MT069-2026-09-16-GHA-MINUTES-REARCHITECTURE/inventory/workflows_inventory.json`
  → `global_facts.all_workflows_currently_state`).
- `gh run list --repo Aspose/aspose.org --limit 15` output (this session).
- Direct user confirmation via `AskUserQuestion`, this session, 2026-09-16 — answer to
  "All 20 workflows in aspose.org currently show as manually disabled... What's the story
  here?" → "I disabled them myself recently."
