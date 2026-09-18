# Planning Evidence Bundle — MT038-2026-08-27-CI-HARDENING (planning pass only)

Companion to `C:\Users\prora\.claude\plans\critical-github-and-gitlab-rippling-crown.md`.
Written after the plan file, capturing the raw research this planning pass relied on.
This directory is gitignored (`reports/`) — local-only, not committed, per repo convention.

## Research agents run this pass (chronological)

1. GitHub Actions workflow inventory + GitLab presence check (repo A) — 17 workflows, 0 GitLab evidence.
2. Governance docs / `workflow-harden` skill discovery — S-115 confirmed, GitHub-only scope.
3. Git remotes / Docker / gh+glab CLI / env-var-name sweep — GitHub-only confirmed, GitLab-named env vars present but unrelated (no repo to use them against).
4. `aspose.org-workflows` existence/access/staleness check — confirmed accessible, cloned locally, was 101 commits behind (now 103, actively receiving commits).
5. `workflow-harden.md` skill file — full read, exact contract/scope/phases/taxonomy.
6. Deploy orchestration architecture mapping (`change-scanner.yml`, `deploy-pipeline.yml`, `deploy-status-checker.yml`, `trigger_workflows.py`, `check_status.py`, `detect_changes.py`) — trigger mechanism (scheduled polling, not event-driven), manifest state machine, concurrency model, idempotency analysis, external systems touched.
7. Historical incident ledger + `ruamel.yaml` claim verification — confirmed real (commit `3f350514`, repo B, 2026-08-26), plus 11 other dated incidents across both repos back to 2026-03-23.
8. Prior 2026-08-08 sprint reconciliation — independently verified which claimed commits actually landed (`278f3e3592`, `09304220dc`, `356acc842d`, `fe68577513`, `a652b79abf` all confirmed ancestors of current `main`), which decisions stayed open (`launch-dashboard.yml` HP-09 — still open; `content-audit.yml` — resolved 6 days later, not by that sprint; 6 citation diffs — apparently never applied).
9. Hidden-dependency + disabled-workflow audit — found the live-broken 4 SEO workflows in repo B (stale since 2026-04-16, fix drafted in repo A 2026-08-26 but never deployed to repo B), the orphaned `check_audit_results.py` path, 44 legitimately-archived workflows in `.github/workflows-disabled/` (repo B), and confirmed `--maxDeletes 0` present on all 7 site workflows.
10. Deploy-pipeline error-handling/idempotency audit — CDN purge failure invisibility, GSC swallowed-failure pattern, the `trigger_workflows.py` double-deploy edge case, permissions-block gaps, action-pinning health confirmation.
11. Direct read of `launch-dashboard.yml` + its failure log (run `32944540470`) + `launch_dashboard.py` source + `.gitignore` — root cause traced to source, not inferred.
12. HP-09 exact finding text located in `reports/sprint/workflow-harden-2026-07-18/preflight/hidden_problems.json` (JSON parse required `.venv/Scripts/python`, not bare `python`, per repo hook policy).
13. This pass's re-verification: repo A/B branch/HEAD/remote/worktree state, `.github/workflows/`+`scripts/ci/` clean-scope check (found the `check_add_bash_hook.sh` delete+untracked pair — concurrent index churn, not this plan's concern), 1,708-file dirty-tree count in repo A.
14. `taskcard_store.py`/`master_plan_index.py`/`session_identity.py`/`override_manager.py` discovery — canonical schema-5f taskcard system found and adopted; confirmed single-repo-scoped (no native cross-repo support, hence the `extra_fields.repo` tagging design in the plan).
15. Branch protection + workflow enabled-state re-verification via `gh api` — repo A blocked by GitHub plan tier (not "unprotected"); repo B genuinely unprotected; **`www.aspose.org.yml` found `disabled_manually` live**, the single most urgent finding of this pass.
16. `APPROVE_LIVE_PR`/`APPROVE_MERGE_PR` search — zero matches repo-wide, confirmed absent.
17. Mission-ID lookup (`plans/master-plan.md`) — MT037 is latest (IN_PROGRESS), MT038 proposed.
18. Exact script-path lookup for the 3 governance-checker taskcards + confirmation that `check_blog_platform_indexes.py` is `content-governance-checks.yml`'s actual completeness-check script.

## Full stale/corrected-claims table

See plan file section 4 — reproduced there as the authoritative version; not duplicated here to avoid drift between two copies.

## Verification gaps acknowledged (not silently assumed complete)

- `check_add_bash_hook.sh`'s delete+untracked pair in repo A was observed but not root-caused — attributed to concurrent-session index churn based on circumstantial evidence (1,708 other dirty files, multiple active peer sessions), not directly confirmed by inspecting another session's activity. Flagged for re-check at Gate G0/G3 execution time.
- Whether `skill-governance.yml`'s current 16-failure streak is *fully* explained by TC-A-04/05/06's targets, or has an additional independent cause, is not yet confirmed — TC-A-03 is scoped as "diagnose first," not "assume resolved."
- Repo B's `deploy_manifest.json`/`check_status.py` reconciliation-by-timestamp approach (reused in the TC-B-02 design) was read and understood, but not executed/tested this pass — its correctness under the specific failure-injection scenarios in section 8 is a G4/G6 verification task, not yet proven.
