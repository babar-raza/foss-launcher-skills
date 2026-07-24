# CLAUDE.md — Session Gate

This file contains **no operational rules**. All governance, skill chains,
write-path enforcement, evidence requirements, and task protocols live
exclusively in `AGENTS.md` (constitutional root) and its child documents:
- `docs/governance/` — write boundaries, evidence, provenance, DAR, launch gates
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
object-plumbing against an isolated temp index (`GIT_INDEX_FILE` + `git read-tree
<parent>` + scoped `git add -f <exact paths>` + `git write-tree` + `git commit-tree
-p <parent>` + `git push <sha>:refs/heads/main`) — this never touches the real
`.git/index` and never invokes `git commit`.

**This bypasses every commit-time git hook** (`pre-commit`, `commit-msg`,
`post-commit`) by construction — no local hook can fire for a commit that never goes
through `git commit`, including the `Skills invoked:` / skill-run-record validation
in `.git/hooks/commit-msg` (TC-GOV-15). This is not a bug to work around; it is a
structural property of how git hooks work. **A git-plumbed commit is therefore
mandatory-paired with a retroactive skill-run record**, created and finalized against
the resulting SHA immediately after pushing:

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
| Operations | `/update-registry`, `/family-sync`, `/translate`, `/getting-started`, `/session-start`, `/commit`, `/backlog`, `/post-sprint-loop` |

Full list and argument syntax: `.claude/commands/README.md`
Authoritative registry: `AGENTS.md §12` (full detail: [docs/registries/skills.md](docs/registries/skills.md))