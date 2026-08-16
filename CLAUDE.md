# CLAUDE.md — Session Gate

This file contains **no operational rules**. All governance, skill chains,
write-path enforcement, evidence requirements, and task protocols live
exclusively in `AGENTS.md` (constitutional root) and its child documents:
- `docs/governance/` — backlink policy, DAR table, forensic-heal history, planning
  methodology (write boundaries, evidence, provenance, and launch gates specifically
  live under `docs/_archive/pre-refactor/governance/` per AGENTS.md §7a/§10 — see
  AGENTS.md for the exact current location of each, since this has moved before)
- `docs/workflows/` — skill chains, maintenance, evaluator changes, gap escalation
- `docs/registries/` — file map, skills registry (Phase 4)

## Mandatory First Action

You must read `AGENTS.md` in full before doing anything else in this session.
Use the Read tool now:

  Read: AGENTS.md

Do not begin any task, respond to any request, or invoke any skill until
`AGENTS.md` is in your active context. If you cannot read it (file missing,
path error), stop and report the failure — do not proceed with cached memory
of its contents.

## Git Push (Non-Interactive)

Agent Bash sessions have no TTY — GCM credential dialogs do not appear.
Use `GH_TOKEN` (always present in env) with `x-access-token`:

```bash
git push "https://x-access-token:${GH_TOKEN}@github.com/Aspose/aspose.org.git" main
```

`GITHUB_PAT` is also set but **does not work** for push to this repo.

### Concurrent-session git-index contention (ST-021)

If another session is actively mutating the shared `.git/index` (large in-flight
`content/` sweeps are common in this repo), an ordinary `git add`/`git commit` risks
staging or corrupting the other session's work. The sanctioned escalation is git
object-plumbing against an isolated temp index — this never touches the real
`.git/index` and never invokes `git commit`.

**Use `scripts/pipeline/commands/ops/git_plumb_commit.py`, not the manual sequence.**
It wraps the full plumbing procedure (`GIT_INDEX_FILE` + `git read-tree <parent>` +
scoped `git add -f <exact paths>` + `git write-tree` + `git commit-tree -p <parent>` +
`git push <sha>:refs/heads/main`) AND makes the two paired safety steps below
non-skippable by construction, instead of relying on the agent to remember to run
them by hand:

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/ops/git_plumb_commit.py \
  --files <exact paths...> --message "<commit message>" \
  --skills S-xx [S-yy ...] --plan "<what this commit does>"
```

This runs the stale-file-regression check before building the temp index (raising
`PlumbCommitBlocked` and pushing nothing if it finds a silent revert — pass
`--skip-stale-check` only when you've deliberately verified the "regression" is an
intentional revert, ideally backed by an override token), builds and pushes the
commit, and creates+finalizes the retroactive skill-run record against the real
resulting SHA automatically. Pass `--no-push` to commit locally without pushing, or
`--base-sha`/`--session-id` to control what the stale-file check compares against.

For batches large enough to risk OS argument-list-too-long errors (roughly 450-500+
files on this repo's Windows/MSYS setup), pass `--files-from <listfile>` (one path
per line) instead of expanding paths into `--files` directly.

If you must fall back to the raw manual sequence (e.g. the tool itself is broken),
both paired steps below are still mandatory — the tool exists to make them
impossible to forget, not to make them optional:

**1. Retroactive skill-run record**, created and finalized against the resulting SHA
immediately after pushing:

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/ops/skill_run_manager.py create \
  --skills S-xx [S-yy ...] --plan "<what this commit does>" --retroactive --run-type targeted
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/ops/skill_run_manager.py finalize \
  --run-id <run_id from create output> --outcome success --commit-sha <the pushed sha>
```

`scripts/ci/checks/check_skill_run_records.py` recognizes a retroactive record
matched by `commit_sha` and reports the commit as `RECONCILED` rather than
`NO DECLARATION`. Skipping this step leaves the commit with zero governance trail
(found live 2026-07-24, MT007 L1-01/L3-01/L3-02 — 3 commits from the words/net launch
sprint had no skill-run record until reconciled post-hoc).

**2. Manual stale-file-regression check**, for the same structural reason:
`scripts/ci/checks/check_stale_file_regression.py` (Step 30 of the normal pre-commit
hook) detects staged content that silently reverts a more recent commit made by
someone else since your session began — but pre-commit hooks never fire for a commit
that never runs `git commit`, so plumbing bypasses this gate too, by the same
construction as every other hook. Run it against your exact file list, using the
`HEAD_SHA` you captured before `git read-tree`, BEFORE building the temp index:

```bash
printf '%s\n' <exact files> | PYTHONPATH=scripts/pipeline .venv/Scripts/python \
  scripts/ci/checks/check_stale_file_regression.py --base-sha "$HEAD_SHA" --working-tree
```

A nonzero exit means at least one of your files matches the state from BEFORE a commit
made by someone else since `$HEAD_SHA` — re-read the current file and reapply your change
on top of it before proceeding, rather than pushing a silent revert (found live 2026-08-01:
TC-MT018-06's commit `d2dce37de5` silently reverted an unrelated fetch_aspose_com_targets.py
fix committed by another session hours earlier, with its own message never mentioning
either file — the exact incident this check exists to prevent).

For a newly-built module with no consumer yet, also consider
`scripts/ci/checks/check_module_consumption.py --module <path>` (advisory, not a
gate — backlog G-48) before calling that module's task done: registry.yaml's
`requires_test` proves a module is tested, not that anything outside its own test
suite actually calls it. Found live 2026-08-01/02: `taskcard_store.py` and
`master_plan_index.py` both reached "fully tested" status with zero real callers
until caught by manual self-audit within the same session that built them.

## Behavioral Mandates (enforced by hooks)

These rules are enforced by PreToolUse hooks — violations will be auto-blocked:

| Action | Required first step |
|--------|---------------------|
| Edit any file under `content/` | Invoke `/manual-edit` (S-73) |
| Write any new file under `content/` | Invoke appropriate creation skill, then `/content-check` (S-23) |
| Commit any content change | Invoke `/commit` (S-76) — never run `git commit` directly |

**Inline reasoning bypass is prohibited.** If no skill covers the task, invoke the
gap escalation protocol (§6b — full detail: docs/workflows/gap-escalation.md) — do not proceed without a registered skill.

## After Reading AGENTS.md

Follow §2 (Read Order) in AGENTS.md exactly. The session start checklist is
in AGENTS.md §3 (Mental Model Refresh Protocol).

## Sites & Content Paths (reference only — not rules)

| Site | Config | Content |
|------|--------|---------|
| docs.aspose.org | `configs/docs.aspose.org.toml` | `content/docs.aspose.org/en/{family}/{platform}/` |
| blog.aspose.org | `configs/blog.aspose.org.yml` | `content/blog.aspose.org/{family}/{platform}/` |
| kb.aspose.org | `configs/kb.aspose.org.toml` | `content/kb.aspose.org/en/{family}/{platform}/` |
| products.aspose.org | `configs/products.aspose.org.toml` | `content/products.aspose.org/en/{family}/` |
| reference.aspose.org | `configs/reference.aspose.org.toml` | `content/reference.aspose.org/en/{family}/{platform}/` |

This table is for orientation only. Path enforcement rules are in AGENTS.md §4.

## Available Commands (Quick Reference)

New to this repo? Start with [`docs/QUICKSTART.md`](docs/QUICKSTART.md) — 30-minute onboarding guide.

Skills are invoked as slash commands:

```
/skill-name {arguments}
```

| Category | Commands |
|----------|---------|
| Knowledge | `/knowledge-update`, `/repo-scout`, `/knowledge-enrich`, `/truth-merge`, `/stale-detect`, `/knowledge-diff` |
| Generation | `/page-plan`, `/page-draft`, `/faq-generate`, `/new-docs-page`, `/launch-product`, `/batch-reference` |
| Repair | `/page-update`, `/page-enhance`, `/heal-page`, `/batch-remediate`, `/gap-apply`, `/evidence-repair` |
| Validation | `/content-check`, `/eval-page`, `/content-eval`, `/gap-eval`, `/content-audit`, `/link-validate` |
| Operations | `/update-registry`, `/family-sync`, `/ht-translate`, `/getting-started`, `/session-start`, `/commit`, `/backlog`, `/post-sprint-loop` |

Full list and argument syntax: `.claude/commands/README.md`
Authoritative registry: `AGENTS.md §12` (full detail: [docs/registries/skills.md](docs/registries/skills.md))