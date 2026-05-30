# Archived Document

Archived: 2026-05-30

Reason: Superseded by the docs architecture refactor. This file is retained for history only; do not use it as current operating guidance.

Successor: See docs/README.md for the current documentation map and canonical references.

Original path: docs/_archive/root-orphans/status-venv-closure-2026-04.md

---

# STATUS — Venv Enforcement Closure Sprint
## Track: rosy-wandering-haven
## Date: 2026-04-17
## Final state: CLOSED

---

## Exit Criteria — All 12 Items

| # | Item | Commit | Status |
|---|------|--------|--------|
| 1 | `check_venv_bash_hook.sh` exists at HEAD | `82c9f880ef` | DONE |
| 2 | Hook blocks bare interpreter/allows compliant+exempt | `82c9f880ef` | DONE (pytest+terminal) |
| 3 | `.claude/settings.json` Bash matcher wired | `82c9f880ef` | DONE |
| 4 | `enforce_venv_python.py` has `--include-shell` | `82c9f880ef` | DONE |
| 5 | `enforce_venv_python.py --check` exits 0 | ongoing | DONE |
| 6 | `check_py_write_hook.sh` uses `$PYTHON`, exit 2 | `f14814b080` | DONE |
| 7 | `.gitignore` contains `.venv/` | `c7bc1c1291` | DONE (TC-A) |
| 8 | Skill file violations committed (20 fixes, 8 files) | `06ce669032` | DONE (TC-B) |
| 9 | `simulate_pr_checks.sh` assessed + committed | `36dad788c4` | DONE (TC-C) |
| 10 | Automated tests for hook (20 cases, 20 passing) | `182cb86734` | DONE (TC-D) |
| 11 | L-1 false-positive documented in hook | `182cb86734` | DONE (TC-E) |
| 12 | Legacy shell debt inventoried + handed off | `36dad788c4` | DONE (TC-F) |

**Track status: CLOSED. All 12 exit criteria met.**

---

## Root Causes Found and Fixed

1. **CRLF in hook script**: `core.autocrlf=true` produced CRLF endings;
   subprocess bash received `pipefail` as option name, causing ALL hook
   invocations to exit 2. Fixed: `sed` strip + `*.sh eol=lf` in `.gitattributes`.

2. **WSL vs Git Bash subprocess**: Default `bash` in Python subprocess PATH on
   Windows is WSL bash, which drops environment variables across the
   Windows-to-WSL boundary. Tests use `_find_bash()` to select Git Bash at
   `C:\Program Files\Git\usr\bin\bash.exe` explicitly.

---

## Test Coverage Added

`scripts/ci/tests/test_check_venv_bash_hook.py` — 20 pytest cases:

- TC-D-01: Bare interpreter invocations are blocked (3 cases)
- TC-D-02: Compliant `.venv` paths are allowed (3 cases)
- TC-D-03: Exemptions are allowed (3 cases)
- TC-D-04: Bare pip invocations are blocked (3 cases)
- TC-D-05: Env-var prefix stripping (3 cases)
- TC-D-06: Pipeline segment scanning (3 cases)
- TC-D-07: Fail-open for missing or unparseable input (2 cases)

All 20 passing. Full suite 115/115 passing.
