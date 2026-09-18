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

### `gh: command not found` when running the setup script

Expected on this dev machine's WSL2 distro — `gh` is only installed on the
Windows host here. Fetch the token from a shell where `gh` *is* available
(see Setup step 1) and pass it with `--token`.

## Decommissioning a runner

Not yet automated (flagged, not built, as of 2026-09-18 — a real gap once a
runner becomes load-bearing enough that decommissioning it safely matters).
Manually, in order: stop and remove the service
(`sudo ./svc.sh stop && sudo ./svc.sh uninstall`), remove the runner's
registration from GitHub (`gh api -X DELETE
repos/<owner>/<repo>/actions/runners/<runner-id>`, id from the verification
API call above), then delete the install directory.

## Related

- `scripts/ci/setup-self-hosted-runner.sh` — the setup script itself
- `scripts/ci/deployed-workflows/selfhosted-runner-smoke-test.yml` — the
  manual-dispatch health-check workflow proven against the public-repo runner
- [Governance gates reference](../reference/governance-gates.md)
