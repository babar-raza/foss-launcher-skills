# Archived Document

Archived: 2026-05-30

Reason: Superseded by the docs architecture refactor. This file is retained for history only; do not use it as current operating guidance.

Successor: See docs/README.md for the current documentation map and canonical references.

Original path: docs/_archive/root-orphans/governance-enforcement-pre-refactor.md

---

# Governance Enforcement — Operator Reference

**Status**: CONDITIONAL GO
**Last verified**: 2026-04-16
**Evidence base**: Sprint 3 (TC-11, TC-17) + Sprint 4 (TC-18, TC-19)

---

## Summary

The skills-only governance model enforces that all agent work on governed files
requires an active registered skill context. Enforcement operates at three
independent layers:

| Layer | Mechanism | Environment | Confirmed |
|-------|-----------|-------------|-----------|
| **Edit-time** | PreToolUse hooks in `.claude/settings.json` | Claude Code CLI + VSCode Extension | **YES** (Sprint 4, TC-18) |
| **Commit-time** | Git `commit-msg` hook | All environments (git-native) | **YES** (Sprint 4, TC-19) |
| **Merge-time** | GitHub Actions CI workflow | All environments (GitHub-native) | **YES** (CI operational) |

**The enforcement chain is confirmed end-to-end.**

---

## Layer 1: Edit-Time Enforcement (PreToolUse Hooks)

### What it does

Before any `Edit` or `Write` tool call executes, the hook:

1. Reads the target `file_path` from stdin (Claude Code runtime format)
2. Classifies the path as **governed** or **ungoverned**
3. For governed paths: checks `reports/skill-context/ACTIVE.json`
   - No file → **BLOCKED** ("No active skill context")
   - File present, path outside scope → **BLOCKED** ("File outside active skill scope")
   - File present, path in scope → **ALLOWED**
4. For ungoverned paths: **ALWAYS ALLOWED** (no skill context required)

### Governed paths (require active skill context)

```
content/*
scripts/pipeline/*
scripts/ci/*
scripts/maintenance/*
knowledge/*
data/*
```

### Ungoverned paths (always allowed)

```
reports/*
plans/*
backlog/*
.claude/plans/*
tests/*
```

### Hook scripts

| Hook | Trigger | Purpose |
|------|---------|---------|
| `scripts/ci/hooks/check_session_gate.sh` | All tools (`.*`) | Session bootstrap gate — blocks all tools until session is bootstrapped |
| `scripts/ci/hooks/check_skill_context_hook.sh` | Edit + Write | Skill context gate for all governed paths |
| `scripts/ci/hooks/check_content_edit_hook.sh` | Edit | Additional gate requiring `/manual-edit` (S-73) for content edits |
| `scripts/ci/hooks/check_content_write_hook.sh` | Write | Requires content-check pass marker for content writes |
| `scripts/ci/hooks/check_py_write_hook.sh` | Write | Python file placement validation |

### Wiring (`.claude/settings.json`)

```json
"PreToolUse": [
  { "matcher": ".*",   "hooks": [{ "command": "bash scripts/ci/hooks/check_session_gate.sh" }] },
  { "matcher": "Edit", "hooks": [{ "command": "bash scripts/ci/hooks/check_content_edit_hook.sh" },
                                  { "command": "bash scripts/ci/hooks/check_skill_context_hook.sh" }] },
  { "matcher": "Write","hooks": [{ "command": "bash scripts/ci/hooks/check_py_write_hook.sh" },
                                  { "command": "bash scripts/ci/hooks/check_content_write_hook.sh" },
                                  { "command": "bash scripts/ci/hooks/check_skill_context_hook.sh" }] }
]
```

### Confirmed environment support

PreToolUse hooks were confirmed operational in the VSCode extension runtime
(Sprint 4, TC-18). Root cause of prior non-execution: the Windows absolute path
format provided by the runtime (`d:/path`) did not match the MSYS2/Git Bash
format returned by `pwd` (`/d/path`), causing all governed paths to fall through
as ungoverned. Fixed by adding drive-letter normalization before prefix stripping.

### Exit code semantics

| Exit code | Meaning |
|-----------|---------|
| `0` | Allow — tool executes |
| `2` | Block — tool is denied; stderr shown to agent |
| `1` | Non-blocking error — tool STILL EXECUTES (reserved for errors, not enforcement) |

**All blocking paths in all hook scripts use `exit 2`.**

### Permissions allow-list (`permissions.allow`)

`.claude/settings.json` also contains a `permissions.allow` list of Bash commands
that auto-approve without user confirmation.  This is **not** a blocking mechanism —
commands not on the list still execute after user confirmation.  It controls approval
friction only.

**Rule:** Broad wildcard entries in `permissions.allow` are prohibited.  Allowed
pattern types:

- Exact bootstrap command
- Exact check-only governance command (e.g., `--check` flag)
- `pytest` limited to known test directories (`tests/*`, `scripts/pipeline/tests/*`, `scripts/ci/tests/*`)
- Exact read-only diagnostics
- Narrow governance lifecycle commands (e.g., `skill_context.py *`)

**Prohibited patterns:** `scripts/*`, `PYTHONPATH=* ...`, `.venv/.../python *`,
`bash *`, `powershell`, `cmd`, `rm`, `del`, `git push *`, `git reset *`,
bare `python`/`python3`/`py`, `pip install`, `curl|bash`/`wget|bash`,
`iwr|iex`/`irm|iex`, `chmod 777`, `sudo`.

**Enforcement:** `scripts/ci/checks/check_settings_breadth.py` scans
`permissions.allow` and rejects overbroad entries (exit 1).

---

## Layer 2: Commit-Time Enforcement (Git Hook)

### What it does

`scripts/commit-msg-skills.sh` (installed as `.git/hooks/commit-msg`) runs on
every `git commit`. For commits that touch `content/*.md` files:

1. **Step 1** — Requires `Skills invoked: [S-xx, ...]` field in commit message
2. **Step 2** — Validates all `S-{n}` IDs against the §12 skill registry (docs/registries/skills.md)
3. **Step 3** — Validates declared skills against the pending skill-run record
   - No pending run record → **BLOCKED**
   - Run record found but skills don't match → **BLOCKED**
   - Run record found and skills match → **ALLOWED**

Non-content commits (no `content/*.md` staged) skip all checks and exit 0.

### Confirmed enforcement (TC-19)

| Scenario | Result |
|----------|--------|
| Content commit, no `Skills invoked:` field | Blocked (exit 1) |
| Content commit, valid skill ID, no run record | Blocked (exit 1) |
| Content commit, invalid skill ID | Blocked (exit 1) |
| Non-content commit | Allowed (exit 0) |

### Hook installation check

The git hook must be installed from the canonical source:

```bash
cp scripts/commit-msg-skills.sh .git/hooks/commit-msg
chmod +x .git/hooks/commit-msg
diff scripts/commit-msg-skills.sh .git/hooks/commit-msg && echo "OK"
```

**Note**: The `.git/hooks/` directory is not tracked by git. If you clone the
repository or the hook falls out of sync, reinstall it using the command above.
A stale pre-TC-1 hook was found during Sprint 4 testing — always verify the hook
matches the canonical source.

### Pre-commit hook

`scripts/pre-commit-audit.sh` (installed as `.git/hooks/pre-commit`) runs
`path_guard.py` before each commit. It blocks commits that touch forbidden-exact
files (`path_guard.py`, `session_ledger.py`, etc.) without an operator override token.

---

## Layer 3: Merge-Time Enforcement (GitHub Actions CI)

### Workflow

`.github/workflows/skill-governance.yml` runs on every push and PR for branches
touching governance-critical files. It:

- Runs `check_commit_skill_provenance.py` to validate `Skills invoked:` in commit messages
- Runs the governance test suite (`test_skill_context.py`, `test_skill_run_manager.py`, etc.)
- Blocks PR merges that fail governance checks

### Trigger paths

The workflow triggers on changes to:
```
scripts/pipeline/commands/governance/skill_context.py
scripts/pipeline/commands/ops/skill_run_manager.py
scripts/pipeline/commands/ops/session_ledger.py
scripts/pipeline/commands/governance/path_guard.py
scripts/pipeline/lib/path_utils.py
scripts/ci/*.sh
scripts/commit-msg-skills.sh
.claude/settings.json
content/**/*.md
```

---

## Skill Context Lifecycle

A well-formed skill invocation follows this lifecycle:

```
1. Skill begins    → skill_context.py begin --skill S-XX --scope "..."
                     Creates reports/skill-context/ACTIVE.json

2. Agent edits     → PreToolUse hook checks ACTIVE.json
                     Governed edits in-scope: ALLOWED
                     Governed edits out-of-scope: BLOCKED

3. Skill ends      → skill_context.py end --skill S-XX --status completed
                     Archives ACTIVE.json to reports/skill-context/history/

4. Commit          → /commit (S-76) creates skill-run record
                     commit-msg hook validates: record present + IDs match

5. CI              → PR merge validates commit provenance chain
```

### Active context marker (`reports/skill-context/ACTIVE.json`)

```json
{
  "skill_id": "S-XX",
  "context_type": "skill",
  "scope_patterns": ["content/docs.aspose.org/en/words/python/*"],
  "started_at": "2026-04-16T19:00:00Z"
}
```

Contexts expire after **2 hours** (stale-context guard). If a skill crashes
without calling `end`, the next `begin` cleans up the stale context.

### Gap-approved contexts

For work not covered by any registered skill:

```bash
# Requires human approval before running
python scripts/pipeline/commands/governance/skill_context.py gap \
    --task "Brief description" \
    --report reports/skill-gaps/YYYY-MM-DD-slug.md \
    --scope "specific/path/*"
```

Gap-approved contexts expire after **30 minutes** and automatically append a
backlog item to `backlog/inbox.md` for durable skill coverage follow-up.

---

## Operator Bypass Procedures

Bypass variables exist for genuine operator emergencies. They are **not
documented in agent-visible files** and must not be mentioned to agents.

Full documentation: `docs/OPERATOR_BYPASSES.md`

---

## Verification Commands

Verify enforcement is operational before each sprint:

```bash
# 1. Confirm no stale ACTIVE.json
ls reports/skill-context/ACTIVE.json 2>/dev/null && echo "STALE — clean up" || echo "Clean"

# 2. Verify commit-msg hook is current
diff scripts/commit-msg-skills.sh .git/hooks/commit-msg && echo "Hook OK"

# 3. Run governance unit tests
python -m pytest scripts/ci/tests/ scripts/pipeline/tests/test_skill_context.py -q

# 4. Spot-check edit-time enforcement (no ACTIVE.json)
echo '{"tool_name":"Edit","tool_input":{"file_path":"'"$(pwd)"'/scripts/pipeline/commands/content/audit.py"}}' \
    | bash scripts/ci/hooks/check_skill_context_hook.sh; echo "Exit: $?"
# Expected: exit 2 (blocked)
```

---

## Override Tokens for Governance Plans

When a remediation plan (e.g., monkeypatch governance, policy rewrite) must edit
files on the DENY path list (`path_guard.py`), the human operator creates
**override tokens** before the agent executes. This uses the existing
`override_manager.py` system documented in AGENTS.md §4.

### How it works

1. **Human creates token** before the wave that needs the DENY-path edit:

   ```bash
   python scripts/pipeline/commands/governance/override_manager.py create \
     --paths <DENY-path-file> \
     --reason "Brief justification referencing plan ID" \
     --plan <plan-id>
   ```

2. **Agent validates** before editing the DENY file:

   ```bash
   python scripts/pipeline/commands/governance/override_manager.py validate-for-path <file>
   # Exit 0 = valid token exists; non-zero = HALT, request human
   ```

3. **Post-commit hook consumes** the token automatically after any commit,
   archiving it to `reports/overrides/archived/` with the commit SHA.

### Token properties

| Property | Value |
|----------|-------|
| TTL | 7 days (`_TOKEN_TTL_DAYS = 7`) |
| Storage | `reports/overrides/pending/` (gitignored, local-only) |
| Archive | `reports/overrides/archived/` (gitignored, local-only) |
| Scope | Path-only — all other quality gates (lint, tests, CI) still enforce |

### Important behaviors

- **Tokens are consumed on ANY commit**, not just commits that stage the DENY
  file. If other commits occur between token creation and the DENY-path commit,
  the token will be consumed and must be recreated.
- If a wave takes longer than 7 days, the token expires and must be recreated.
- The agent must never use `--no-verify` to bypass the pre-commit hook.
- Override tokens bypass only path ownership (Layer 2/3 in the enforcement
  model above). All other pre-commit steps still execute.

### Example: multi-wave plan

```bash
# Wave 0: needs AGENTS.md edit
python scripts/pipeline/commands/governance/override_manager.py create \
  --paths AGENTS.md \
  --reason "Governance rewrite per plan-id" \
  --plan plan-id

# Wave 1: needs CI workflow edit
python scripts/pipeline/commands/governance/override_manager.py create \
  --paths .github/workflows/content-audit.yml \
  --reason "Add CI enforcement step per plan-id" \
  --plan plan-id

# Wave 4: needs pre-commit hook edit
python scripts/pipeline/commands/governance/override_manager.py create \
  --paths scripts/pre-commit-audit.sh \
  --reason "Promote lint to blocking per plan-id" \
  --plan plan-id
```

---

## Known Limitations

| Limitation | Impact | Mitigation |
|-----------|--------|-----------|
| `.git/hooks/` not tracked by git | Stale hook after clone or upgrade | Reinstall from `scripts/commit-msg-skills.sh` on setup |
| Wildcard scope `*` is valid | Any governed file accessible under wildcard scope | Restrict wildcard to gap-approved contexts only (design decision pending) |
| Path traversal outside governed prefix | `content/../AGENTS.md` passes edit-time hook | Pre-commit path_guard catches it at commit time |
| FORBIDDEN_EXACT files under governed prefixes | `scripts/pipeline/commands/governance/path_guard.py` passes edit-time hook (under `scripts/pipeline/*`) | Pre-commit path_guard.py blocks at commit time |
