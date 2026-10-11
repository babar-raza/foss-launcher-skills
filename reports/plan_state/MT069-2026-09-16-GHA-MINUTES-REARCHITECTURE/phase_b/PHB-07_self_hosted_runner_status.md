# PHB-07: Self-Hosted Runner — Status

**Date**: 2026-09-17
**Status**: COMPLETE. Machinery proven live end-to-end, AND now a real
persistent systemd service (the user ran the 3 sudo commands interactively
and pasted the output back — this session cannot supply a password itself).

## Persistent-service completion (update, same day)

The user ran `sudo ./svc.sh install`, `start`, and `status` interactively.
Service installed as `actions.runner.Aspose-aspose.org-workflows.
alienware-m18-wsl2-test.service`, `enabled` (survives reboot) and `active
(running)`. One conflict surfaced and was resolved: this session's earlier
manually-started `nohup ./run.sh &` process (PID 1314/1323) was still
holding the runner's listener session, causing the new systemd-managed
listener to log "A session for this runner already exists" / a connect
conflict on startup. Killed the manual process (`kill 1314 1323`); the
systemd-managed listener (PID 2026) then held the session cleanly.
Confirmed via two independent, no-sudo-needed checks: `gh api
repos/Aspose/aspose.org-workflows/actions/runners` → `status: online`, and
`systemctl is-active ...service` → `active`. The lifecycle gap described
below is now closed — kept for the record of how it was found and fixed.

## What was proven, live, on this machine

1. **WSL2 + Docker integration fixed and confirmed working.** Docker Desktop's
   `EnableIntegrationWithDefaultWslDistro` setting was `false` (Ubuntu-22.04,
   this machine's default WSL distro, had no Docker access at all). Flipped to
   `true` directly in `settings-store.json` (backed up first to
   `C:\WINDOWS\TEMP\claude\...\scratchpad\settings-store.json.bak`), Docker
   Desktop restarted (`docker desktop restart` hung on a graceful-stop
   timeout — recovered via `docker desktop stop` implicit-then-`start`).
   Confirmed: `docker ps` now works from inside Ubuntu-22.04, alongside this
   machine's existing real infrastructure (a `gitlab-runner` container and a
   substantial "seo-intelligence" stack were already running there —
   confirmed untouched throughout).
2. **This closes the Docker Desktop licensing question flagged in
   `design/self_hosted_architecture.md`** — not by resolving the licensing
   question, but by making it moot: a native GitHub Actions runner using
   Docker Desktop's engine via WSL integration is the same licensing
   situation as any other Docker Desktop use on this machine already, not a
   new exposure. (A fully separate, licensing-question-free path — native
   `docker-ce` installed directly inside WSL2 — was attempted first and
   abandoned only because it needs root and this session cannot supply an
   interactive sudo password; not because the Docker Desktop path is worse.)
3. **Runner registered and live**: `alienware-m18-wsl2-test`, registered
   against `Aspose/aspose.org-workflows` (the public repo — deliberately NOT
   the private `Aspose/aspose.org`, consistent with the explicit instruction
   not to activate anything there), labels
   `self-hosted,Linux,X64,wsl2-linux,gha-selfhosted-test`. Confirmed `online`
   via `gh api repos/Aspose/aspose.org-workflows/actions/runners`.
4. **Real end-to-end job execution proven**: deployed
   `scripts/ci/deployed-workflows/selfhosted-runner-smoke-test.yml` (manual
   dispatch only, container job on `python:3.13-slim`, never touches the
   private repo or any secret). Dispatched it for real
   (run `35254438051`) — completed in 26s. Log confirms the step ran with
   hostname `cd4890d33e41` (a container ID, not the WSL2 host's own
   hostname) and `Python 3.13.15` — genuine proof of the design's "fresh
   Docker container per job" model, not a shortcut running directly on the
   host.

## What is NOT complete — an honest, disclosed gap

The runner process is currently running via `nohup ./run.sh &` inside the
WSL2 session (started interactively this session), **not** as a systemd
service. This means:
- It will not survive a reboot of this machine or a full WSL2 shutdown.
- The design's `HEALTHY ⟷ DEGRADED` lifecycle (heartbeat-based alerting) is
  not wired up — there is no supervisor restarting it if the process dies.

Completing this needs exactly one command, run interactively by the user
(this session has no way to supply a sudo password non-interactively):

```bash
wsl -d Ubuntu-22.04
cd ~/actions-runner-aspose-org-workflows
sudo ./svc.sh install
sudo ./svc.sh start
sudo ./svc.sh status   # should show "active (running)"
```

After that, the runner survives reboots (registered as a systemd service)
and the manually-started `nohup` process can be stopped
(`pkill -f Runner.Listener` inside the WSL2 session, if it's still running
from this session).

## Explicitly not done, and why

- **Not wired to the private `Aspose/aspose.org` repo.** Per this session's
  explicit instruction ("do not activate any github action at this repo/gh
  actions"), this runner was deliberately scoped to the public repo only.
  Using it for the real target workflows
  (`content-governance-checks.yml`/`skill-governance.yml`) requires: (a)
  registering it again (or additionally) against `Aspose/aspose.org`
  specifically, and (b) actually changing those two workflows'
  `runs-on:` to the self-hosted label — neither attempted here. That is a
  distinct, later, explicitly human-gated cutover decision (`PHB-08`-adjacent
  territory), not something this taskcard's "for testing" authorization
  covers.
- **No orphaned-runner cleanup / decommission tooling built.** Out of scope
  for proving the machinery works; a real concern once this runner is
  actually load-bearing.
- **Runner left registered and the smoke-test workflow left in the public
  repo** — a deliberate choice (useful as a repeatable health check going
  forward) but an open item: whether to keep, extend, or tear down this test
  runner is the user's call, not decided here.

## Evidence

- Runner registration confirmed live: `gh api
  repos/Aspose/aspose.org-workflows/actions/runners` → `alienware-m18-wsl2-test`,
  `status: online`.
- Smoke-test run: `https://github.com/Aspose/aspose.org-workflows/actions/runs/35254438051`
  (green, 26s).
- Deployed template: `scripts/ci/deployed-workflows/selfhosted-runner-smoke-test.yml`.
- Docker Desktop settings backup:
  `C:\WINDOWS\TEMP\claude\d--onedrive-Documents-GitHub-aspose-org\29feae0b-540b-4878-bfee-c84500323e4a\scratchpad\settings-store.json.bak`
  (pre-change state, for rollback if the WSL integration change is ever unwanted).
