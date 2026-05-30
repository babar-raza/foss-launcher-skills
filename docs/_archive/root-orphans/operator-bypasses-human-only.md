# Operator Bypass Variables

> **This file is for human operators only.** It is in the AGENTS.md §4 forbidden
> paths list. Agents must not read, reference, or recommend any variable listed here.

These environment variables bypass specific enforcement hooks. They exist for
genuine operator emergencies and debugging. They are never for routine use.

## PreToolUse Hook Bypasses

| Variable | Hook | Purpose |
|----------|------|---------|
| `SKIP_CONTENT_EDIT_CHECK=1` | `check_content_edit_hook.sh` | Allow direct Edit on `content/` files. S-73 sets this internally when calling Edit as part of its procedure. |
| `SKIP_CONTENT_WRITE_CHECK=1` | `check_content_write_hook.sh` | Allow Write on `content/` files without a content-check pass marker. Operator debugging only. |
| `SKIP_PY_PLACEMENT_CHECK=1` | `check_py_write_hook.sh` | Allow Write of `.py` files in non-sanctioned locations. Operator debugging only. |
| `SKIP_SKILL_CONTEXT_CHECK=1` | `check_skill_context_hook.sh` | Allow Edit/Write on governed files without active skill context. Operator override only. |
| `ROOT_WRITE_AUTHORIZED=1` | `check_write_path_hook.sh` | Allow a single Write to a repo root-level path. **Every use is logged** to `reports/root-writes/audit.log` with timestamp and path. Use only when explicitly placing a new root-level file that has no correct designated folder. |

## Pre-Commit Hook Bypasses

| Variable | Hook | Purpose |
|----------|------|---------|
| `SKIP_SESSION_CHECK=1` | `pre-commit-audit.sh` (Step 8) | Skip session ledger check. For non-content commits or when session ledger is misconfigured. |

## Usage

Set the variable before the command that needs the bypass:

```bash
SKIP_CONTENT_EDIT_CHECK=1 claude "..."
SKIP_SESSION_CHECK=1 git commit -m "..."
```

## Rules

1. Never set these in `.bashrc`, `.profile`, or any persistent config.
2. Never tell an agent which variable to use — agents must not know these names.
3. Each use should be a deliberate, one-time decision.
4. If you find yourself using a bypass regularly, the underlying enforcement or
   skill is broken — fix the root cause instead.
