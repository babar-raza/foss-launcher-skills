# Self-Hosted GitHub Actions Runner Setup

Status: Current
Audience: Operator
Canonical reference: `scripts/ci/setup-self-hosted-runner.sh`
Last code-backed audit: 2026-09-18

This org runs two independent self-hosted runners on the maintainer's own dev
machine (a Windows 11 Pro box running WSL2). There is no shared, org-managed
runner fleet — each runner is provisioned by hand on whichever machine will
host it, following this guide. If you clone this repo onto a new machine and
need to stand up a runner (a replacement, an additional one, or recovering
this one after a rebuild), this is the procedure — before 2026-09-18 it only
existed as ad hoc shell history and gitignored planning notes, invisible to
anyone starting from a fresh clone.

## Why two separate runners, not one

| Runner | Repo it's registered against | Labels | Serves |
|---|---|---|---|
| `alienware-m18-wsl2-test` | `Aspose/aspose.org-workflows` (public) | `self-hosted,Linux,X64,wsl2-linux,gha-selfhosted-test` | The smoke-test workflow (`selfhosted-runner-smoke-test.yml`); a proving ground, not load-bearing |
| `alienware-m18-wsl2-private` | `Aspose/aspose.org` (private) | `self-hosted,Linux,X64,gha-private-native` | `content-governance-checks.yml`, `skill-governance.yml`'s required Linux job |

**A GitHub Actions runner is registered against exactly one repo (or one org,
for an org-level runner — not used here) and can only ever pick up jobs
queued by that repo.** This is not a `runs-on:` label-matching detail you can
work around — it is enforced at registration time by which registration-token
endpoint you called. Setting `runs-on: [self-hosted, my-label]` on a workflow
in a repo the runner isn't registered against does nothing; the job queues
forever, waiting for a runner that will never claim it.

**This was a real, live incident** (MT069-2026-09-16-GHA-MINUTES-REARCHITECTURE,
2026-09-18): the first runner set up in this org was registered against
`Aspose/aspose.org-workflows` under the (reasonable-sounding) assumption that
it would eventually serve the private repo's workflows too. It never could
have — confirmed only when a second mission went to wire it up and checked
the runner's own `.runner` config file's `gitHubUrl` field. The fix was a
second, separately-registered runner, not a re-label. **Before trusting any
plan or design document's claim about which repo a runner serves, verify it
directly**: `cat <install-dir>/.runner | grep gitHubUrl`, or
`gh api repos/<owner>/<repo>/actions/runners`.

## Isolation model (MT069 card HC-03, decided 2026-09-18)

**What a job can do today.** Measured, not assumed — the public host probe
(`selfhosted-host-probe.yml`, runs `35380303439` and `35381064675`) runs **host-direct**, on the same
machine, WSL distro and OS user as the private runner:

| Fact | Result |
|---|---|
| Runs in a container | no (`in_container=no`) |
| OS user | `prorata`, uid 1000 (not root) |
| Windows drive readable from job code | **yes** — `/mnt/c`, `/mnt/c/Windows/win.ini`, `/mnt/c/Users` |
| WSL interop (can launch Windows `.exe`) | **enabled** |
| State persists between jobs | **yes** — a marker written to `$HOME` by run 1 was present in run 2 |
| Windows directories on the service `PATH` | yes (Git for Windows, Python, JDKs); `npm` resolves to a Windows shim |
| `docker` on the service `PATH` | **no** — so `container:` jobs fail at job setup (`docker: command not found`, run `35381073902`) |

The original design (`TC-08`) assumed a fresh container per job. That does not hold: it was proven on
2026-09-17 while the runner was started from an interactive shell (which had Docker on its `PATH`) and
silently stopped working when the runner became a systemd service. Treat any "container-per-job works" claim
older than the service conversion as void.

**Options considered.**

| | Isolation | Cost / risk |
|---|---|---|
| (a) `container:` per job | fresh filesystem, no Windows mounts | needs Docker on the service `PATH` and a service restart (`sudo`); container jobs run as root by default and leave root-owned files in `_work` that the runner user then cannot clean; handing job containers the Docker socket is host-root-equivalent; shares Docker Desktop's VM with the maintainer's other containers |
| (b) dedicated WSL distro with automount and interop off | no Windows drive, no Windows binaries, clean `PATH`; no containers needed | one-time human setup (`sudo`, distro admin); both runners move there |
| (c) host-direct + mitigations only (**current state**) | none of the above | none — but the Windows exposure above stays |

**Decision (delegated to the agent by the user's 2026-09-18 "do everything from HC-01 to HC-19";
reversible):** the target is **(b)**. It is the simplest at run time (no containers, no Docker
dependency) and the only option that removes the Windows exposure rather than working around it.

**Interim exception, time-boxed:** the single observed proof run in card HC-02 (see
`first-live-run-protocol.md`) may run on (c). The code it executes is the maintainer's own committed check
scripts, `actions/*`, `peaceiris/actions-hugo` and the packages in `requirements-ci.txt` — all things
already run locally as the same user — and the repo's flow is direct push (no fork PRs). The workflow is
enabled only for that run and **re-disabled afterwards**. This is *not* acceptance of (c) for leaving a
workflow enabled.

**Target state — steps for a human (not run by the agent: they change the machine and need `sudo`).**
Untested as written; treat them as a draft to verify.

1. Create a clean distro (WSL 2.6.1 is installed here): `wsl --install -d Ubuntu-22.04 --name gha-runner`. If your WSL rejects `--name`, import a clean Ubuntu 22.04 rootfs with `wsl --import gha-runner <dir> <rootfs.tar>` — **do not** export the existing distro; it carries the current runners' credentials.
2. Inside it create a non-root user, then set `/etc/wsl.conf`:
   ```ini
   [boot]
   systemd=true
   [automount]
   enabled=false
   [interop]
   enabled=false
   appendWindowsPath=false
   ```
   then `wsl --shutdown` and reopen the distro.
3. Install `git`, `curl`, `tar`; run `scripts/ci/setup-self-hosted-runner.sh` once per runner (see Setup below), then `sudo ./svc.sh install && sudo ./svc.sh start` for each.
4. **Negative control (must pass before HC-03 is closed):** as the runner user, `ls /mnt/c` must fail or be empty and `cmd.exe` must not run; then dispatch `selfhosted-host-probe.yml` on that runner and expect `reachable /mnt/c=no` and `wsl_interop=disabled`.
5. Decommission the two old runners (see Decommissioning) once the new ones are `online`.

## Prerequisites

- A Linux environment (WSL2 on Windows, or a native Linux host) with `bash`,
  `curl`, `tar`.
- `sudo` access on that machine, usable **interactively** (a password prompt
  must be answerable by a human at a real terminal — this cannot be automated
  or scripted, and an agent session cannot supply it).
- `gh` CLI, authenticated with admin access to the target repo's Actions
  runner settings, available **somewhere** — not necessarily in the same
  shell that will run the setup script. On this dev machine, `gh` is
  installed on the Windows host but **not** inside the WSL2 distro where the
  runner itself needs to live; the setup script accounts for this (see
  `--token` below).
- Know the exact target repo (`owner/repo`) and the label(s) you want before
  you start. Do not guess or default this — see the incident above.

## Setup

1. **Get a registration token**, from wherever `gh` is authenticated for the
   target repo (this may be a different shell/machine than where the runner
   will run):

   ```bash
   gh api -X POST repos/<owner>/<repo>/actions/runners/registration-token --jq '.token'
   ```

   This token is short-lived (~1 hour) — fetch it immediately before the next
   step, not in advance.

2. **Run the setup script**, in the shell/environment where the runner will
   actually live (e.g. inside the WSL2 distro, not the Windows host):

   ```bash
   bash scripts/ci/setup-self-hosted-runner.sh \
     --repo <owner>/<repo> \
     --name <descriptive-runner-name> \
     --labels <your-custom-label> \
     --token <token-from-step-1>
   ```

   Omit `--token` if `gh` is authenticated in the *same* shell you're running
   this script from — it will fetch its own token automatically in that case.
   `--dir` defaults to `~/actions-runner-<owner-repo-with-dashes>`; pass it
   explicitly if you want a non-default location or need more than one runner
   registered on the same machine (each needs its own directory).

   The script downloads (or reuses an already-downloaded copy from a sibling
   runner directory on the same machine) the runner package, extracts it, and
   runs `config.sh --unattended` with your parameters. It refuses to run
   against a directory that already has a registered runner (`.runner`
   exists) rather than silently reconfiguring it — pass a different `--dir`
   for a genuinely separate, additional runner.

3. **Install it as a persistent service** — the script prints these exact
   commands at the end, but they must be run **by a human, interactively**,
   because they need a `sudo` password:

   ```bash
   cd <install-dir>
   sudo ./svc.sh install
   sudo ./svc.sh start
   sudo ./svc.sh status   # expect: active (running)
   ```

   Until this step, the runner only exists as a registered identity with no
   listener running — it will show `status: offline` via the API and pick up
   no jobs.

## Verifying

```bash
# From wherever gh is authenticated for the target repo:
gh api repos/<owner>/<repo>/actions/runners --jq '.runners[] | {name, status, busy}'
```

Expect `status: online`, `busy: false` once the service is running and idle.

```bash
# On the machine hosting the runner, no sudo needed:
ps aux | grep Runner.Listener
```

Expect exactly **one** `Runner.Listener` process per registered runner
directory. See Troubleshooting below if you see more than one.

## Troubleshooting

### Two listener processes for the same runner

**A real incident** (2026-09-18): a runner was started for a quick manual
test via `nohup ./run.sh &` before its systemd service was installed. After
installing and starting the service, the original `nohup` process was never
killed — leaving two `Runner.Listener` processes both holding the same
runner identity's session simultaneously. Caught via `ps aux | grep
Runner.Listener` showing two PIDs for the same install directory.

**Fix**: identify and kill the non-systemd one. The systemd-managed process's
parent is `runsvc.sh`; a manually-started one's parent is `run-helper.sh` or
a bare shell. `ps aux | grep -i '<install-dir>'` shows both process trees —
kill the PIDs belonging to whichever one is *not* under systemd's control
(`systemctl status <service-name>` shows the systemd-managed PID to compare
against).

**Prevention**: never run `./run.sh` or `nohup ./run.sh &` in a directory
whose service has already been installed. If you need a quick smoke test
before installing the service, kill that manual process
(`pkill -f 'Runner.Listener run$'` — note the `$`, this excludes the
service-managed process which runs with `--startuptype service` appended)
before running `sudo ./svc.sh install`.

### Both runners go `offline` a short while after the last terminal closes (WSL stopped)

**Observed 2026-09-19 (MT069 HC-05/06):** after a machine restart both runner services came up on their own
(the unit is `enabled`) and showed `online`. About 25 minutes later, with no terminal open, `wsl -l -v` showed
the distro `Stopped` and both runners `offline`; `runner-availability-watch.yml` correctly reported "matching
runners: 1, online: 0". **A systemd service does not keep a WSL instance alive — an open `wsl` session does.**
Before the restart the runners had stayed online for hours; the likely reason (an inference, not proven) is that
two long-running background `wsl` sessions happened to be open.

Bring it back and keep it up (session-scoped: no configuration is changed, and it ends at logoff or reboot):

```powershell
Start-Process wsl.exe -ArgumentList '-d','Ubuntu-22.04','--exec','sleep','infinity' -WindowStyle Hidden
wsl -l -v          # Ubuntu-22.04 should read Running; the runners reconnect within ~30 s
```

**To make it permanent** — one per-user Windows Scheduled Task that starts the keepalive at every logon. It needs
**no administrator rights** (verified 2026-09-19 with a dummy task on this machine, which was deleted). Run once, in
a normal (non-elevated) PowerShell:

```powershell
$who      = "$env:USERDOMAIN\$env:USERNAME"
$action   = New-ScheduledTaskAction -Execute "conhost.exe" -Argument "--headless wsl.exe -d Ubuntu-22.04 --exec sleep infinity"
$trigger  = New-ScheduledTaskTrigger -AtLogOn -User $who
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
              -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName "WSL keepalive (GitHub runners)" -Action $action -Trigger $trigger -Settings $settings `
  -RunLevel Limited -User $who -Description "Keeps the Ubuntu-22.04 WSL instance running so the two GitHub Actions runner services stay online."
Start-ScheduledTask -TaskName "WSL keepalive (GitHub runners)"     # start it now instead of waiting for the next logon
```

Why each setting matters: `--headless` (Windows 11's `conhost`) keeps a console window from appearing at every logon;
`-ExecutionTimeLimit 0` is essential, because a task registered from PowerShell otherwise gets a **72-hour limit** and
would silently kill the keepalive after three days; the two battery switches stop Windows from cancelling it when a
laptop unplugs; `-RestartCount 3` retries if `wsl.exe` fails to start.

Verify: `Get-ScheduledTask "WSL keepalive (GitHub runners)" | Get-ScheduledTaskInfo` (LastTaskResult `0`),
`wsl -l -v` reads `Running`, and both runners are `online` in the repo settings. Undo:
`Unregister-ScheduledTask -TaskName "WSL keepalive (GitHub runners)" -Confirm:$false`.

What this does **not** fix: it starts at *logon*, so after a reboot nothing runs until you sign in (turn on Windows
auto-login if this machine should recover unattended); and if Windows sleeps or hibernates, everything stops and
queued jobs wait until it wakes. On AC this machine is set to never sleep; battery is not covered. Until the task
exists, expect a `runner-offline` issue on the public repo whenever the machine is off or the keepalive is gone; the
availability watch closes it itself once the runner is back.

### Runner shows `offline` and never picks up jobs

Check, in order:
1. Is the listener process actually running? (`ps aux | grep Runner.Listener`
   on the host machine.)
2. Is it registered against the repo the workflow actually lives in? (`cat
   <install-dir>/.runner | grep gitHubUrl` — see "Why two separate runners"
   above.)
3. Does the workflow's `runs-on:` list include every custom label you
   registered the runner with? GitHub requires an exact-set match on custom
   labels (the automatic `self-hosted`/OS/arch labels are implicit).

### `docker: command not found` in "Set up job" of a `container:` job

**A real regression** (2026-09-18, run `35381073902`): the container smoke test that passed on 2026-09-17
now fails at job setup. A systemd-managed runner does not inherit your interactive shell's `PATH`; it uses
the `PATH` captured in `<install-dir>/.path`, and that file has many Windows directories but not Docker's.
Fixing it means adding Docker's directory to `.path` and restarting the service (`sudo`). This does not
matter under the recommended isolation model (no containers) — see "Isolation model".

### `error while loading shared libraries: libpython3.13.so.1.0` when reproducing a job by hand

The Python that `actions/setup-python` installs under `_work/_tool` needs `LD_LIBRARY_PATH` to include its own
`lib/` directory; the action sets it for real jobs. When simulating a job in a plain shell, export
`LD_LIBRARY_PATH="<install-dir>/_work/_tool/Python/<ver>/x64/lib:$LD_LIBRARY_PATH"` first (this bit the
HC-06 simulation).

### `gh: command not found` when running the setup script

Expected on this dev machine's WSL2 distro — `gh` is only installed on the
Windows host here. Fetch the token from a shell where `gh` *is* available
(see Setup step 1) and pass it with `--token`.

## Decommissioning a runner

**Automated (MT069 HC-18, 2026-09-23)** — `scripts/ci/decommission-self-hosted-runner.sh --repo
<owner/repo> --name <runner-name>`. It looks up the runner's id, checks (read-only, no `sudo`)
whether a systemd service is active for it — if so it prints the exact `sudo` stop/uninstall
commands and stops, since it cannot supply a password non-interactively — otherwise kills any
foreground (non-service) listener, deletes the GitHub registration, removes the install
directory, and verifies both are gone. Refuses to target `alienware-m18-wsl2-private` or
`alienware-m18-wsl2-test` (this org's two real, load-bearing runners) unless you pass
`--i-mean-it`.

**Proven live, fresh-machine style (2026-09-23):** registered a temporary third runner
(`mt069-hc18-freshtest`) against the public repo via `setup-self-hosted-runner.sh`, started it as
a foreground (non-service) listener, confirmed `online` in the API alongside the two real
runners (untouched), then ran the decommission script. Its first attempt used `--token`
(this host has no `gh` inside WSL) with `curl ... --jq` — **a real bug**: curl does not
understand `--jq`, and wrapped in `|| true` the failure silently read as "runner not found"
instead of an error, so the script reported success while the runner was still fully registered
and online. Fixed: this host also has no system `jq` (a separately confirmed gap), so every
JSON response — from both the `gh` and `curl` transports — is now filtered through Python
instead of `--jq`/`jq`. Re-run: found the runner, deleted its registration, removed its
directory, and verified both were gone — confirmed independently afterward via a fresh `gh api`
call and a directory listing. The foreground listener process itself was found already gone by
the time of the second run, most likely because a plain `nohup`+`disown`'d process does not
reliably survive across separate `wsl -e` invocations the way a real `systemd` service does —
reinforcing why the two real runners are services, not foreground listeners.

Manual fallback if the script is ever unavailable, in order: stop and remove the service
(`sudo ./svc.sh stop && sudo ./svc.sh uninstall`), remove the runner's registration from GitHub
(`gh api -X DELETE repos/<owner>/<repo>/actions/runners/<runner-id>`, id from the verification
API call above), then delete the install directory.

## Related

- `scripts/ci/setup-self-hosted-runner.sh` — the setup script itself
- `scripts/ci/decommission-self-hosted-runner.sh` — the decommission script (MT069 HC-18)
- `scripts/ci/deployed-workflows/selfhosted-runner-smoke-test.yml` — the
  manual-dispatch health-check workflow proven against the public-repo runner
- [Governance gates reference](../reference/governance-gates.md)
