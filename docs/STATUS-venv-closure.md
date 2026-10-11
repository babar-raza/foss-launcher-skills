# STATUS — Venv Enforcement: CLOSED

**Sprint**: rosy-wandering-haven
**Closed**: 2026-04-17
**Current status**: All exit criteria met; enforcement is permanent.

## Summary

This document records the closure of the venv enforcement sprint. All local Python invocations
must use `.venv/Scripts/python` (Windows) or `.venv/bin/python` (Unix/macOS). Bare `python`,
`python3`, or `pip` commands are blocked by the pre-commit hook.

**WSL is permanently rejected** for this repo because it creates a separate venv environment
that bypasses the Windows hooks and produces inconsistent behavior between local development
and CI. All operators on Windows must use Git Bash (MSYS2/MINGW64).

## Enforcement Mechanism

The hook at `scripts/ci/hooks/check_venv_bash_hook.sh` blocks any Bash tool call that uses
a bare interpreter. It is installed at `.git/hooks/` by `bash scripts/install-hooks.sh`.

Exempt commands:
- `python -m venv` (venv creation)
- `python --version` (version checks)

## Exit Criteria — All Closed

| # | Item | Status |
|---|------|--------|
| 1 | `check_venv_bash_hook.sh` installed | DONE |
| 2 | Hook blocks bare interpreter, allows compliant + exempt | DONE |
| 3 | `.claude/settings.json` Bash matcher wired | DONE |
| 4 | `enforce_venv_python.py --check` exits 0 | DONE |
| 5 | `.gitignore` contains `.venv/` | DONE |
| 6 | CI gate (`enforce_venv_python.py`) passes on main | DONE |

## See Also

- Original sprint record: [docs/_archive/root-orphans/status-venv-closure-2026-04.md](../_archive/root-orphans/status-venv-closure-2026-04.md)
- Shell policy: [AGENTS.md §2b](../AGENTS.md#2b-shell-execution-policy-windows-local-operations)
