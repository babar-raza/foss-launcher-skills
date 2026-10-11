# Bypass Registry

Every governance PreToolUse hook under `scripts/ci/hooks/` exposes exactly one
environment-variable bypass, printed on its `BYPASS:` line when it blocks a
tool call. All of them are **operator-only** — a human, deliberately, in
their own shell — never something an agent sets on itself to route around a
block it doesn't like. If you are an agent and a hook is blocking you, see
[`docs/GOVERNANCE_QUICKSTART.md`](GOVERNANCE_QUICKSTART.md) for the actual
fix instead.

This registry exists because, until 2026-09-11, several hooks cited it by
name and it didn't exist — see
[`reports/skill-gaps/2026-09-11-imaging-net-pipeline-hardening-prerequisites.md`](../reports/skill-gaps/2026-09-11-imaging-net-pipeline-hardening-prerequisites.md).
`scripts/ci/checks/check_governance_doc_links.py` now asserts every doc path
a hook cites resolves to a real file, so this table rotting again would be
caught by CI rather than discovered live by a blocked agent.

| Env var | Hook | What it does |
|---|---|---|
| `SKIP_SESSION_GATE_CHECK=1` | `check_session_gate.sh` | Skips all checks for this hook entirely (exit 0). This hook fires on *every* tool call (`matcher: ".*"`), so this is the broadest bypass in the table — reserve it for recovering a session whose own `.venv`/environment is broken enough that the gate itself can't run (see `check_session_gate.sh`'s own comments on the 2026-08-16 incident where a broken `.venv` blocked even `Read`). |
| `SKIP_CONTENT_EDIT_CHECK=1` | `check_content_edit_hook.sh` | Bypasses the `Edit`-under-`content/`-requires-`/manual-edit` gate. Documented as "for operator use inside S-73 only" — i.e. it's what `/manual-edit` itself sets internally while it holds an active edit context, not a general escape hatch. |
| `SKIP_CONTENT_WRITE_CHECK=1` | `check_content_write_hook.sh` | Bypasses the `Write`-under-`content/` gate. Documented as "for operator debugging only." |
| `SKIP_SKILL_CONTEXT_CHECK=1` | `check_skill_context_hook.sh` | Bypasses the active-skill-context requirement for `Edit`/`Write` under `scripts/pipeline/`, `scripts/ci/`, `knowledge/`, `data/`, `.github/workflows/`, etc. If the real issue is "no skill covers this," the fix is `skill_context.py gap` (see the quickstart), not this flag. |
| `SKIP_PY_PLACEMENT_CHECK=1` | `check_py_write_hook.sh` | Bypasses the Python-file-placement convention check on `Write`. Documented as "for operator debugging only." |
| `SKIP_COMMIT_BASH_CHECK=1` | `check_commit_bash_hook.sh` | Bypasses the raw-`git commit`-is-blocked gate. Documented as "operator-only, not for agent use" — the sanctioned path is always `/commit` (S-76) or, for the isolated-temp-index concurrency case, `git_plumb_commit.py`. |
| `SKIP_DESTRUCTIVE_BASH_CHECK=1` | `check_destructive_bash_hook.sh` | Bypasses the destructive-shell-command gate (e.g. `rm -rf`, `git reset --hard`). Documented as "operator-only, not for agent use." |
| `SKIP_ADD_BASH_CHECK=1` | `check_add_bash_hook.sh` | Silences an *advisory-only* warning about unguarded `git add` sweeps (added after a live 2026-08-26 incident where one swept 26 files from another session). This hook never blocks — the flag only silences the warning text. |
| `SKIP_LEDGER_INIT_CHECK=1` | `check_ledger_init_hook.sh` | Skips the session-ledger-initialized requirement entirely. Operator-only. |
| `SKIP_SESSION_LEDGER_HOOKS=1` | `session_end_ledger_hook.sh`, `session_heartbeat_hook.sh` | Disables the session-ledger `SessionEnd`/heartbeat hooks. Operator-only. |

## What this table does NOT cover

These are the Claude Code PreToolUse/session hooks only. They have no effect
under Kilo Code (no PreToolUse mechanism at all — see
`.kilocode/rules-code/governance.md`) or Codex (prose-only enforcement, no
hooks). A bypass flag being unset is not proof a governed action will be
blocked — it depends on which harness is running. See
`docs/GOVERNANCE_QUICKSTART.md`'s "Harness-conditional enforcement" section.

`git_plumb_commit.py`'s own internal safety checks (the stale-file-regression
check before it builds a commit) are a separate mechanism with no env-var
bypass at all — see its `--skip-stale-check` flag (requires a verified
override token) if you have a genuine reason to skip it, documented in
`CLAUDE.md`'s git-plumbing section, not here.
