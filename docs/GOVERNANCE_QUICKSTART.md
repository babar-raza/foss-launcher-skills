# Governance Quickstart

You landed here because a PreToolUse hook blocked a tool call and printed
`DOC:     docs/GOVERNANCE_QUICKSTART.md` in its failure message. This page is
that remediation doc — it exists because, until 2026-09-11, every hook that
cited it pointed at a file that didn't exist (see
[`reports/skill-gaps/2026-09-11-imaging-net-pipeline-hardening-prerequisites.md`](../reports/skill-gaps/2026-09-11-imaging-net-pipeline-hardening-prerequisites.md)).

## Why you were blocked

This repo enforces its skills-only execution policy (AGENTS.md §6a) via real
PreToolUse hooks under `scripts/ci/hooks/` — **only under the Claude Code
harness**. They gate `Edit`, `Write`, and `Bash` calls against
`content/`, `scripts/pipeline/`, `scripts/ci/`, `knowledge/`, `data/`,
`.github/workflows/`, and a few other governed prefixes. Every block prints a
five-line message:

```
BLOCKED: <what was denied>
REASON:  <why>
FIX:     <what to do instead>
BYPASS:  <env var, if one exists — almost always "operator only">
DOC:     <this file, or docs/BYPASS_REGISTRY.md>
```

Read the `FIX:` line first — it names the specific unblock condition for
*that* hook, not a generic one.

## The three most common causes

| Hook | Blocks | Fix |
|---|---|---|
| `check_content_edit_hook.sh` / `check_content_write_hook.sh` | `Edit`/`Write` under `content/` with no active skill context | Invoke `/manual-edit` (S-73) for an edit, or the matching creation skill + `/content-check` (S-23) for a new file — not a raw `Edit`/`Write` |
| `check_skill_context_hook.sh` | `Edit`/`Write` under `scripts/pipeline/`, `scripts/ci/`, `knowledge/`, `data/`, `.github/workflows/`, etc. with no active skill context | Invoke the owning skill, or — if no skill's contract covers the change — follow the gap-escalation protocol (`docs/workflows/gap-escalation.md`) and open a context via `skill_context.py gap --task ... --report ... --scope ...` |
| `check_commit_bash_hook.sh` | A raw `git commit` | Use `/commit` (S-76), never `git commit` directly |

## If no registered skill covers the task

Do not bypass the hook to work around a missing skill. Follow
`docs/workflows/gap-escalation.md`: classify your capability state
(FULL/PARTIAL/NONE/BROKEN), and if PARTIAL or NONE, file a gap escalation
report at `reports/skill-gaps/{YYYY-MM-DD}-{task-slug}.md` and classify its
disposition per that doc's rubric. A `bounded-oneoff` disposition (a small,
first-occurrence, bounded patch — no durable recurring skill needed) is
unblocked via:

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py gap \
  --task "<what you're doing>" \
  --report "reports/skill-gaps/{YYYY-MM-DD}-{task-slug}.md" \
  --scope "<comma-separated glob patterns for the exact files you need>"
```

This is a **gap-approved temporary context** (30-minute TTL) — not a bypass.
It still requires a written gap report and, per the protocol, a human
decision the report can point back to (an `ExitPlanMode` approval of a plan
that names the same work satisfies this, per existing precedent in
`reports/skill-gaps/index.yaml`).

## Environment/setup failures (fail-closed, not a policy block)

Several hooks block *everything* if their own prerequisites are broken — a
missing or corrupt `.venv`, no `CLAUDE_TOOL_INPUT`/stdin available, or
unparseable JSON. These fail closed by design (better to block than silently
skip a governance check), and the fix is almost always environmental:

```bash
rm -rf .venv && python -m venv .venv && pip install -r scripts/ci/requirements.txt
```

If a hook is blocking `Read`-only or otherwise clearly-safe tool calls due to
a broken `.venv` with no recovery path, see `check_session_gate.sh`'s own
comments (it hit exactly this live, 2026-08-16) — a bash-only fallback exists
for that specific failure mode.

## Bypass flags

Every hook's `BYPASS:` line names an env var (almost always suffixed
"operator only"). These are last-resort, human-authorized escapes — see
[`docs/BYPASS_REGISTRY.md`](BYPASS_REGISTRY.md) for the full list and what
each one actually does. Do not set a bypass flag yourself to route around a
block you don't understand; ask the human operator, or use the gap-escalation
path above if the real issue is a missing skill.

## Harness-conditional enforcement — read this before assuming a hook "will" block something

These hooks are **Claude Code PreToolUse hooks only**. Kilo Code has no
PreToolUse mechanism at all (its own `.kilocode/rules-code/governance.md`
states this explicitly — enforcement there is prompt-level only) and Codex
has none either. Even under Claude Code, coverage has known, live-incident
seams: a tool-specific hook (e.g. one gating `Write`) does not see the same
operation performed via a different tool (`Bash cp`, confirmed live 2026-07-14,
backlog row ST-016), and a session that never calls `Edit`/`Write`/
`session_ledger.py init` at all is invisible to every hook in this repo.
Treat these hooks as real, working, and worth respecting — not as a
technical guarantee that a violation is always caught. See
`reports/skill-gaps/2026-09-11-imaging-net-pipeline-hardening-prerequisites.md`
for the full diagnosis this quickstart was written to close.
