---
name: code-smoke
id: S-63
description: >
  Syntax and type-check Python code blocks in content pages without executing them.
  Uses py_compile for syntax checking and mypy (optional) for type checking.
args: "{family} {platform} | --files {path1} [path2 ...]"
---

# S-63: Code Smoke — Syntax and Type-Check Python Code Blocks

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}` or `--files {path1} [path2 ...]`

## Purpose

Check that Python code blocks in content pages are syntactically valid and
optionally type-correct. Uses `py_compile` for syntax checking and `mypy` for
type checking. **Never executes code** — compile/type-check only.

## Pre-conditions

1. Content pages exist for the product
2. `knowledge/{family}/{platform}/scout/model.yaml` exists with a `canonical_import`
   field (the product's Python import statement) — if absent, checks run without an
   import prefix
3. Python 3.9+ available in the current environment
4. `mypy` installed for full type checking (`pip install mypy`) — if not installed,
   only syntax checking is performed (no error)

> **Optional context gate** — if `scripts/skill_context.py` exists, run before step 1:
> ```bash
> python scripts/skill_context.py begin --skill S-63 --scope "{target}"
> ```

## Steps

### Step 1: Parse arguments

Determine scope:
- Two words (`{family} {platform}`): find all `.md` content files for that product
  under the content directories configured in `config.yaml`
- `--files {path1} [path2 ...]`: check only the specified files

### Step 2: Load canonical import

Read `canonical_import` from `knowledge/{family}/{platform}/scout/model.yaml`.
- If the field is set, prepend it to each code block before checking
- If empty or missing: warn "canonical_import not set — blocks will be checked
  without import prefix" and continue
- **Never hardcode a product import** — only use the value from `model.yaml`

### Step 3: Extract code blocks

For each target `.md` file, extract all fenced ` ```python ` blocks along with
their line numbers. Skip blocks that contain only comments.

### Step 4: Per-block checks

For each extracted block:

**a. Syntax check** (`py_compile`):
1. Write the block to a temp file, prepending the `canonical_import` line
2. Run `python -m py_compile {temp_file}`
3. Non-zero exit = **FAIL**

**b. Type check** (`mypy`, if available):
1. Run `mypy --ignore-missing-imports --no-error-summary {temp_file}`
2. Any mypy error = **WARN** (never FAIL)
3. If mypy is unavailable, skip silently

### Step 5: Run via script (if available)

If `scripts/smoke_test.py` exists in the repo, prefer it over manual steps:

```bash
# Product-wide:
python scripts/smoke_test.py {family} {platform}

# Specific files:
python scripts/smoke_test.py --files {path/to/file.md}
```

If the script is absent, execute Steps 3–4 manually as described above.

### Step 6: Report results

```
============================================================
SMOKE TEST REPORT
Files checked:  N
Blocks checked: N
  PASS: N
  WARN: N
  FAIL: N
============================================================

{path/to/file.md}
  [FAIL] block 2 (line 47): SyntaxError: invalid syntax
  [WARN] block 3 (line 65): TypeWarning: ...

RESULT: {PASS | WARN | FAIL} — {N} block(s) have syntax errors
```

> **Optional context close** — if `scripts/skill_context.py` exists, run after the last step:
> ```bash
> python scripts/skill_context.py end --skill S-63 --status completed
> ```

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | All blocks PASS (no syntax or type errors) |
| 1 | At least one WARN (type errors only, no syntax errors) |
| 2 | At least one FAIL (syntax error) |

## Integration with eval-page (Python platform)

When eval-page (S-25) is run for a Python-platform product, add this as a sub-step:

- Exit code 2 (FAIL): count each failing block as an additional FAIL finding
- Exit code 1 (WARN): count each warning block as an additional WARN finding
- Exit code 0 (PASS): no additional findings

## Known limitations

- Multi-block examples (variables defined in block 1 used in block 2) are checked
  independently — may produce false-positive `NameError` complaints
- Non-Python code blocks (Java, C#, TypeScript, C++) are not checked by this skill
- `bash` and shell blocks are never checked
- Syntax check catches compile-time errors only, not runtime errors

## Post-conditions

- Exit code 0 or 1: page may be committed (type warnings are advisory only)
- Exit code 2: fix all syntax errors before committing the page
