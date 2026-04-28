# Governance Quickstart

Concise operator guide to the aspose.org governance system.
For full details, see AGENTS.md. For bypass details, see [BYPASS_REGISTRY.md](BYPASS_REGISTRY.md).

## How Governance Works

Three layers of enforcement run in sequence:

1. **PreToolUse hooks** (8 hooks) -- fire before Claude Code Edit/Write/Bash tools execute
2. **Pre-commit hook** (11 steps) -- fires on `git commit`
3. **CI checks** (2 workflows) -- fire on PR push

All blocking hooks exit 2 (PreToolUse) or exit 1 (pre-commit/commit-msg) to deny the action.

## Top 5 Most Common Failures and Fixes

### 1. "Session gate blocked: session not bootstrapped"
**Hook**: check_session_gate.sh
**Fix**: Run `/session-start` or `bash scripts/ci/bootstrap_session_gate.sh`
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

# Root-level writes (logged to reports/root-writes/audit.log)
ROOT_WRITE_AUTHORIZED=1

# Commit-msg skill check (3-var model — ALL THREE required, audited)
SKIP_SKILL_COMMIT_CHECK=1 GOV_BYPASS_TASKCARD=TC-GOV-XX GOV_BYPASS_REASON='reason' git commit ...
```

### Override Token (for forbidden paths)

```bash
# Create a token for a forbidden-path write
.venv/Scripts/python scripts/pipeline/override_manager.py create \
  --path AGENTS.md --reason "governance update per TC-GOV-XX"

# Token is consumed automatically by post-commit hook
```

## Forbidden Bypass Methods

| Method | Why Forbidden |
|--------|--------------|
| `--no-verify` | Skips ALL hooks; breaks entire audit trail |
| Direct hook file editing | Hooks are repo-managed; use `bash scripts/install-hooks.sh` |

## Which Checks Block What

| Action | Blocking Checks |
|--------|----------------|
| Edit content file | Session gate, content edit hook, skill context hook |
| Write new content file | Session gate, write path hook, content write hook, skill context hook |
| Write Python file | Session gate, write path hook, py placement hook, skill context hook |
| Run bash command | Session gate, venv bash hook, destructive bash hook |
| Git commit (content) | Pre-commit Steps 0-8, commit-msg skills check |
| Git commit (non-content) | Pre-commit Steps 0-7 |
| PR push | CI content-audit, CI skill-governance |

## Reinstalling Hooks

If hooks get out of sync with source scripts:

```bash
bash scripts/install-hooks.sh
```

## Related Documentation

- [BYPASS_REGISTRY.md](BYPASS_REGISTRY.md) -- Full bypass mechanism catalog
- [HARD_STOP_RECOVERY.md](HARD_STOP_RECOVERY.md) -- Recovery protocols for unconditional halts
- AGENTS.md -- Complete governance specification
- docs/OPERATOR_BYPASSES.md -- Operator bypass protocols
