# Archived Document

Archived: 2026-05-30

Reason: Superseded by the docs architecture refactor. This file is retained for history only; do not use it as current operating guidance.

Successor: See docs/README.md for the current documentation map and canonical references.

Original path: docs/_archive/root-orphans/governance-quickstart-pre-refactor.md

---

# Governance Quickstart

Concise operator guide to the aspose.org governance system.
For full details, see AGENTS.md. This archived file originally linked to the old root bypass registry, now archived as `docs/_archive/root-orphans/bypass-registry-operator-note.md`.

## How Governance Works

Three layers of enforcement run in sequence:

1. **PreToolUse hooks** (8 hooks) -- fire before Claude Code Edit/Write/Bash tools execute
2. **Pre-commit hook** (11 steps) -- fires on `git commit`
3. **CI checks** (2 workflows) -- fire on PR push

All blocking hooks exit 2 (PreToolUse) or exit 1 (pre-commit/commit-msg) to deny the action.

## Top 5 Most Common Failures and Fixes

### 1. "Session gate blocked: session not bootstrapped"
**Hook**: check_session_gate.sh
**Fix**: Run `/session-start` or `bash scripts/ci/hooks/bootstrap_session_gate.sh`
**Bypass**: `SKIP_SESSION_GATE_CHECK=1`

### 2. "Direct Edit on content file blocked"
**Hook**: check_content_edit_hook.sh
**Fix**: Invoke `/manual-edit` (S-73) first -- it sets the bypass internally
**Bypass**: `SKIP_CONTENT_EDIT_CHECK=1` (operator only)

### 3. "No active skill context"
**Hook**: check_skill_context_hook.sh
**Fix**: Invoke a registered skill that covers the target file
**Bypass**: `SKIP_SKILL_CONTEXT_CHECK=1` (operator only)

### 4. "Content-check (S-23) not passed"
**Hook**: check_content_write_hook.sh
**Fix**: Run `/content-check` on the file first
**Bypass**: `SKIP_CONTENT_WRITE_CHECK=1` (operator only)

### 5. "Content commits must include 'Skills invoked:'"
**Hook**: commit-msg-skills.sh
**Fix**: Add `Skills invoked: [S-xx, S-yy]` line to commit message; use `/commit` (S-76)
**Bypass**: `SKIP_SKILL_COMMIT_CHECK=1` + `GOV_BYPASS_TASKCARD=TC-XX` + `GOV_BYPASS_REASON='reason'` (all three required)

## Available Bypasses

### Environment Variable Bypasses (operator only)

```bash
# Session gate
SKIP_SESSION_GATE_CHECK=1

# Content edit (normally set by S-73 internally)
SKIP_CONTENT_EDIT_CHECK=1

# Skill context
SKIP_SKILL_CONTEXT_CHECK=1

# Content write marker
SKIP_CONTENT_WRITE_CHECK=1

# Python placement
SKIP_PY_PLACEMENT_CHECK=1

# Destructive bash operations
SKIP_DESTRUCTIVE_BASH_CHECK=1

# Session ledger (pre-commit Step 8)
SKIP_SESSION_CHECK=1

# Any path_guard-denied write (logged to reports/root-writes/audit.log)
# CAUTION: bypasses ALL denials including forbidden paths; prefer override tokens
ROOT_WRITE_AUTHORIZED=1

# Commit-msg skill check (3-var model — ALL THREE required, audited)
SKIP_SKILL_COMMIT_CHECK=1 GOV_BYPASS_TASKCARD=TC-GOV-XX GOV_BYPASS_REASON='reason' git commit ...

# Governance maintenance mode (3-var model — ALL THREE required, audited)
# Allows edits to scripts/ci/, scripts/pipeline/, scripts/maintenance/ without skill context
GOV_MAINTENANCE_MODE=1 GOV_MAINTENANCE_PLAN=TC-GOV-XX GOV_BYPASS_REASON='reason'
```

### Override Token (for forbidden paths)

```bash
# Create a token for a forbidden-path write
.venv/Scripts/python scripts/pipeline/commands/governance/override_manager.py create \
  --path AGENTS.md --reason "governance update per TC-GOV-XX"

# Token is consumed automatically by post-commit hook
```

### Editing Forbidden Paths (Full Workflow)

When an agent needs to edit a file under themes/, layouts/, configs/, or other forbidden paths:

1. **Human creates override token**:
   ```bash
   .venv/Scripts/python scripts/pipeline/commands/governance/override_manager.py create \
     --paths "layouts/_default/section.html" \
     --reason "Blog section template fix" --plan "task-id"
   ```
   Token stored in `reports/overrides/pending/` (gitignored). Expires in 7 days.

2. **Agent performs Write/Edit directly** (token-aware PreToolUse — GOV-LIGHT-001/002):
   - The path hook checks for a valid pending token covering the exact path.
   - Token found → write/edit allowed. Audit written to `reports/overrides/pretooluse-audit.log`.
   - No token or wrong path → **Write tool** is blocked at PreToolUse (exit 2).
   - **ROOT_WRITE_AUTHORIZED is not required** for token-covered paths.
   - **Agents must not create their own override tokens.** Token creation is a human operator action.

   > **Edit tool gap (GOV-LIGHT-003):** `layouts/` and `themes/` are NOT in the
   > skill_context hook's governed-path list. The Edit tool on these paths passes all
   > PreToolUse hooks even without an override token. However, the **pre-commit hook
   > WILL block the commit** if no valid token exists. Always create the override token
   > BEFORE editing to avoid stuck uncommitted work.

3. **Human commits** (pre-commit independently revalidates the token):
   ```bash
   git add layouts/_default/section.html
   git commit -m "fix: blog section template"
   ```
   Pre-commit: path_guard DENY → check_forbidden_overrides → token found → ALLOW.
   Post-commit: token archived automatically to `reports/overrides/archived/`.

**When to use ROOT_WRITE_AUTHORIZED instead**: Only for emergency or bootstrap situations
where a token cannot be pre-created (e.g., when fixing override_manager.py itself). It
bypasses ALL path_guard denials — not just forbidden paths. Logged to
`reports/root-writes/audit.log`. Pre-commit still validates token coverage for any
forbidden-path files included in the commit.

### Commit Provenance Bypass: SKIP_SKILL_COMMIT_CHECK

`SKIP_SKILL_COMMIT_CHECK` is a **commit-time** bypass for skill provenance checks in
`commit-msg-skills.sh`. It does **not** grant write or edit access to any path — path
authorization (PreToolUse hooks) is a completely separate system.

**What it bypasses**: The requirement that commit messages include `Skills invoked: [S-xx]`
for commits touching governed paths.

**What it does NOT bypass**: PreToolUse hooks, S-23 content checks, S-73 content edit checks.

**Correct usage** (3-var model — ALL THREE required):
```bash
SKIP_SKILL_COMMIT_CHECK=1 \
  GOV_BYPASS_TASKCARD=TC-GOV-XX \
  GOV_BYPASS_REASON='reason for bypassing skill provenance' \
  git commit -m "your message"
```

**Audit trail**: All uses logged to `reports/overrides/env-bypasses.log`.

**Do NOT use SKIP_SKILL_COMMIT_CHECK for**:
- Content commits — S-23 and S-73 must still pass independently
- Hiding missing skill runs when a proper skill invocation is required
- Gaining write access to protected paths — it has zero effect on path authorization
- Any situation where the commit-msg check is failing for a legitimate governance reason

### SKIP_SKILL_CONTEXT_CHECK and Forbidden Paths

`SKIP_SKILL_CONTEXT_CHECK=1` bypasses the **skill context** requirement. It has **zero
effect on path authorization** for Class B forbidden paths (`themes/`, `layouts/`, etc.).

- `themes/` and `layouts/` are blocked by `path_guard.py`, not by the skill context system.
- Setting `SKIP_SKILL_CONTEXT_CHECK=1` for a forbidden-path write will still result in
  a PreToolUse block (exit 2) from `check_write_path_hook.sh`, or a pre-commit failure
  if Edit was used.
- The correct mechanism for Class B paths is an override token (see workflow above).
- `SKIP_SKILL_CONTEXT_CHECK=1` is operator-only and must never be suggested to agents.

## Forbidden Bypass Methods

| Method | Why Forbidden |
|--------|--------------|
| `--no-verify` | Skips ALL hooks; breaks entire audit trail |
| Direct hook file editing | Hooks are repo-managed; use `bash scripts/install-hooks.sh` |
| `SKIP_SKILL_CONTEXT_CHECK` for forbidden paths | Does not affect path_guard; Class B paths need override tokens |
| `ROOT_WRITE_AUTHORIZED` for routine template edits | Broad bypass for all denials; override tokens are the correct Class B mechanism |

## Which Checks Block What

| Action | Blocking Checks |
|--------|----------------|
| Edit content file | Session gate, content edit hook, skill context hook |
| Write new content file | Session gate, write path hook, content write hook, skill context hook |
| Write Python file | Session gate, write path hook, py placement hook, skill context hook |
| Run bash command | Session gate, venv bash hook, destructive bash hook |
| Git commit (content) | Pre-commit Steps 0-7, Step 8 session ledger (warning only), commit-msg skills check |
| Git commit (non-content) | Pre-commit Steps 0-7 |
| PR push | CI content-audit, CI skill-governance |

## Hook Firing Order (TC-DS-04)

Which PreToolUse hooks fire for each tool, and what can block:

| Tool | Hooks (in firing order) | What can block | Exemptions |
|------|------------------------|----------------|------------|
| Read | session gate (EXEMPT) | Nothing | Always allowed |
| Grep | session gate (EXEMPT) | Nothing | Intrinsically read-only (TC-DS-01) |
| Glob | session gate (EXEMPT) | Nothing | Intrinsically read-only (TC-DS-01) |
| Bash | session gate, venv hook, destructive hook | Bare python/pip; destructive ops | Read-only commands exempt from gate (TC-DS-01) |
| Edit | session gate, content-edit hook, skill-context hook | content/ without S-73; governed path without skill | — |
| Write | session gate, write-path hook, py-write hook, content-write hook, skill-context hook | Forbidden paths; wrong .py location; content/ without S-23; governed path without skill | — |

**Session gate read-only exemptions (TC-DS-01):**
- Grep and Glob are always exempt (zero write side effects)
- Bash commands classified as read-only by `scripts/ci/checks/classify_bash_readonly.py` are exempt
- Read-only = commands like `git log`, `ls`, `cat`, `grep`, `find` (without -delete)
- Non-read-only commands (rm, python, redirects, etc.) still require the gate

## Reinstalling Hooks

If hooks get out of sync with source scripts:

```bash
bash scripts/install-hooks.sh
```

## Related Documentation

- `docs/_archive/root-orphans/bypass-registry-operator-note.md` -- archived bypass mechanism catalog
- [Hard-stop recovery](../../operations/hard-stop-recovery.md) -- current recovery protocol
- AGENTS.md -- Complete governance specification
- docs/OPERATOR_BYPASSES.md -- Operator bypass protocols
