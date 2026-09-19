# First Live Run Protocol (private self-hosted cutover)

Status: Current
Audience: Operator
Canonical reference: `plans/from_backlog/2026-09-16-gha-minutes-rearchitecture.md` (§H7 GATE-HARD, §H8 evidence contract, cards HC-02 / HC-11)
Last code-backed audit: 2026-09-18

All 20 workflows in `Aspose/aspose.org` have been `disabled_manually` since the cost emergency.
Everything fixed since 2026-09-11 — the platform-capabilities checker, the evaluator-version-bump
gate, the concurrency guards, the scoped `llms` regeneration, the move of two jobs to a
self-hosted runner — has **never executed in CI**. This protocol is the only sanctioned way to
turn one workflow back on and find out, and to do it so that the result is *evidence* and the
step is *reversible*.

## Authority

Enabling or dispatching a private workflow is a human decision (GATE-HARD). Before step 2, paste the
go-ahead **verbatim** into the evidence bundle — the person's words, the date, and which workflow(s)
it covers. A general "carry on" does not name a workflow; ask. An agent may perform the steps below
only under that recorded go-ahead, one workflow at a time.

## What was verified in advance (2026-09-18, public repo, no private workflow touched)

Every observation command below was run against real runs on the public `Aspose/aspose.org-workflows`
repo's test runner (same machine, WSL distro and OS user as the private runner) so nothing in this
protocol is a guess about what a command returns.

| Mechanism | Verified how | Result |
|---|---|---|
| Dispatch on a proof branch | branch created from `main`; `gh workflow run … --ref <branch>`; run `35381607387` | run's `headBranch` = the proof branch, so a concurrency group keyed on `github.ref` differs from `main`'s |
| Cancel | `gh run cancel 35381607387` | `completed/cancelled` within ~15 s |
| Which runner took the job | REST `…/actions/runs/<id>/jobs` mid-run (run `35382133262`) and after (`35380303439`) | `runner_name`, `runner_id`, `labels`, `created_at`, `started_at` are populated **as soon as the job starts** (not only at the end). Note: `gh run view --json jobs` does **not** expose them — use the REST endpoint |
| Queue latency | `started_at − created_at` on a completed job | 3 s for run `35380303439` |
| Cost signature | REST `…/actions/runs/<id>/timing` | self-hosted: `"billable": {}`; GitHub-hosted: a populated map (`UBUNTU`/`WINDOWS`…). Empty `billable` is the proof a job cost no Actions minutes |
| Full-history checkout, `setup-python@v5`, `actions-hugo@v3` host-direct | host probe run `35380303439` | all succeeded (740 commits, `Python 3.13.15`, `hugo v0.154.5 extended`) |

**Not verifiable without enabling a private workflow, therefore untested at the time of writing:** `gh workflow enable/disable`
on the private repo, and the first run of the two target workflows. **Update 2026-09-19:** steps 2, 3 and 6 were
exercised for `content-governance-checks.yml` (see "Observed on the first real run" below); `skill-governance.yml`
is still untested.

## Preconditions (all must hold before step 2)

- [ ] HC-03's isolation decision is recorded, or the human has recorded that the time-boxed exception applies to this run (see "Isolation note").
- [ ] HC-04's runner-availability alert has been demonstrated firing and recovering.
- [ ] HC-06 is done (tool needs proven met on the runner host).
- [ ] The runner is `online` and idle:
      `gh api repos/Aspose/aspose.org/actions/runners --jq '.runners[] | {name,status,busy,labels: [.labels[].name]}'`
- [ ] `skill-governance.yml` only: it has a `workflow_dispatch` trigger. (It had none — push and `pull_request` only — until HC-02 prep added one.) Its `governance-tests-windows` job runs on **GitHub-hosted Windows and is billed**; expect a few minutes of Windows time.
- [ ] Nothing else is queued on the runner (it has one slot).

## Isolation note

The private jobs run **host-direct** on the WSL2 host as an ordinary user (`uid 1000`). The host probe
showed: WSL interop is enabled; `/mnt/c`, `/mnt/c/Windows/win.ini` and `/mnt/c/Users` are readable from
job code; a file written under `$HOME` by one job is visible to the next; `npm` resolves to a Windows
binary. The container-per-job model the original design assumed does **not** currently work — the
systemd service's `PATH` has no Docker, so `container:` jobs fail at job setup with `docker: command
not found` (run `35381073902`). So this run happens on a host that is not isolated from the Windows
side. That is acceptable only as a time-boxed, observed proof of code the maintainer already runs
locally as the same user; it is **not** a reason to leave a workflow enabled (HC-03).

## Steps

### 0. Pre-state snapshot (read-only)

```bash
gh workflow list --repo Aspose/aspose.org --all --json name,state          # expect: 20 x disabled_manually
gh api repos/Aspose/aspose.org/actions/runners --jq '.runners[] | {name,status,busy}'
git fetch origin main && git rev-parse origin/main                          # the SHA the proof will run
gh run list --repo Aspose/aspose.org --workflow <file> --limit 3 --json databaseId,conclusion,createdAt
```

Save the output into the bundle (`EVIDENCE_BUNDLE.md`, `E-API` entries).

### 1. Create a proof ref

A push to `main` by a concurrent session would cancel your run if it shared `main`'s concurrency group
(both target workflows use `cancel-in-progress: true` keyed on `github.ref`). So run on a branch of your own:

```bash
SHA=$(git rev-parse origin/main)
git push origin "$SHA:refs/heads/mt069-live-proof-$(date -u +%Y%m%d)"
```

Neither target workflow's `push` trigger matches a non-`main` branch, so creating it starts nothing.

### 2. Enable exactly one workflow *(exercised 2026-09-19)*

Start with `content-governance-checks.yml` (largest cost driver, no soft-launched sibling job).

```bash
gh workflow enable content-governance-checks.yml --repo Aspose/aspose.org
```

From this moment a push to `main` matching its path filter also queues a run on the same single-slot
runner. Keep the window short.

### 3. Dispatch on the proof ref *(exercised 2026-09-19)*

```bash
gh workflow run content-governance-checks.yml --repo Aspose/aspose.org --ref mt069-live-proof-YYYYMMDD
```

### 4. Observe (verified commands)

```bash
RID=$(gh run list --repo Aspose/aspose.org --workflow content-governance-checks.yml --limit 1 --json databaseId --jq '.[0].databaseId')
# which runner took each job, and how long it waited
gh api repos/Aspose/aspose.org/actions/runs/$RID/jobs --jq '.jobs[] | {name,status,conclusion,runner_name,runner_id,labels,created_at,started_at,completed_at}'
# per-step conclusions
gh run view $RID --repo Aspose/aspose.org --json jobs --jq '.jobs[].steps[] | "\(.status)/\(.conclusion) \(.name)"'
# cost signature (after completion)
gh api repos/Aspose/aspose.org/actions/runs/$RID/timing
```

**Abort immediately** (go to step 6) if any of: the job sits `queued` more than 15 minutes while the
runner is `online`; a job's `runner_name` is not `alienware-m18-wsl2-private` (a silent fallback to another
runner — investigate before anything else); a secret value appears unmasked in a log; a step reads or
writes outside the workspace. *(The 15-minute figure is a proposal for the human to confirm, not a measured threshold.)*

### 5. Classify every failing step — do not just re-run

| Class | Meaning | Action |
|---|---|---|
| (a) genuine finding | the check ran correctly and found a real problem in the repo | record it; it is a content/governance backlog item, **not** a cutover failure |
| (b) runner/toolchain defect | `command not found`, missing library, PATH, permission, network from the host | stop; this is what HC-06/HC-03 exist to prevent — fix, then re-run |
| (c) workflow bug | wrong condition, bad path, stale step | fix the workflow file; reproduce (GATE-ROOTCAUSE) before changing it |

Every classification needs a saved reproduction (§H10). A red run is not automatically a failure of
the cutover — a *correctly failing* check is the point of the check.

### 6. Roll back / disable *(disable and branch deletion exercised 2026-09-19; `gh run cancel` verified earlier on the public repo)*

```bash
gh run cancel <run-id> --repo Aspose/aspose.org           # verified on the public repo
gh workflow disable content-governance-checks.yml --repo Aspose/aspose.org
git push origin --delete mt069-live-proof-YYYYMMDD
```

Leaving the workflow enabled afterwards is the human's separate decision; the default is to restore the
`disabled_manually` state it started in.

### 7. Post-state snapshot and evidence bundle

Repeat step 0's commands and diff them against the pre-state. The E-LIVE entry (§H8) for each run must
contain: run URL/ID, workflow file, head SHA it executed, event, conclusion, per-step conclusions,
`runner_name`, timestamps, and the `timing.billable` value.

### 8. Then repeat for `skill-governance.yml`

Same steps, with the differences in the preconditions: dispatch requires the added `workflow_dispatch`
trigger, and the `governance-tests-windows` job is GitHub-hosted and billed — record its minutes.

## Rollback matrix

| Trigger | Action |
|---|---|
| Job queued > threshold with runner online | cancel run; `gh workflow disable`; check the runner |
| Job on the wrong runner | cancel; disable; treat as an incident (silent fallback) |
| Class (b) failure | cancel; disable; fix; re-run from step 3 |
| Secret exposed in a log | cancel; disable; delete the run's logs; tell the human immediately |
| Anything surprising | disable first, investigate second |

## Observed on the first real run (2026-09-19, `content-governance-checks.yml`, run `35433173048`)

- **Result:** all 36 steps green on `alienware-m18-wsl2-private` (runner 21), queue latency 3 s, `timing.billable = {}`
  (no Actions minutes), 1,029 s in total. Enabled 08:52:20Z, disabled 09:09:51Z.
- **The first run on a cold runner is dominated by `actions/checkout`** (848 s): it fetches the whole history of a
  ~941 MB repository over this machine's network at ~1.6 MB/s. That is not a hang. Check `.git` growth in the runner's
  `_work` directory before aborting; the run holds the runner's single slot meanwhile. `_work` persists, so later runs
  should fetch only new objects (not yet measured).
- **A `workflow_dispatch` run diffs only `HEAD~1`.** The grade-presence and evaluator-version-bump steps therefore saw
  "No content files changed" / "none changed". To exercise them, make the proof ref's last commit touch representative
  content.
- **Do step 6 (disable) first** once the run is complete, then collect evidence: the workflow's push trigger is live for
  as long as it is enabled.
- **What the job touched outside the workspace:** only the two standing tool caches (`~/.cache/pip`, `~/actions_hugo`);
  `actions/checkout` copies the user's `~/.gitconfig` into a temp directory (a read). No `/mnt/` reference, no secret
  used.
- **The runner must stay online for the whole window:** a systemd service does not keep a WSL instance alive — an open
  `wsl` session does (see the setup guide, Troubleshooting).
