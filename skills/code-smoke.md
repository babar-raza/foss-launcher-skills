# S-63: Code Smoke — Syntax and Type-Check Code Blocks

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}` or `--files {path1} [path2 ...]`

## Purpose

Check that code blocks in content pages are syntactically valid. Supports
Python (via `py_compile` and `mypy`), Java, C#, TypeScript, and C++ (via
tree-sitter grammar parsing). **Never executes code** — syntax-check only.

## Pre-conditions

1. `knowledge/{family}/{platform}/scout/model.yaml` exists with a non-empty
   `canonical_import` field (the product's Python import statement).
2. Content pages exist for the product under `content/`.
3. Python 3.9+ available in the current environment.
4. `mypy` installed for full type checking (`pip install mypy`). If not
   installed, only syntax checking is performed (no error).

## Steps

> **Skill context gate** — run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-63 --scope "*"
> ```


1. **Parse arguments**: Determine scope — either product-wide (`{family} {platform}`)
   or specific files (`--files`).

2. **Load canonical import**: Read `canonical_import` from
   `knowledge/{family}/{platform}/scout/model.yaml`.
   - If empty: WARN "canonical_import not set — blocks will be checked without import prefix."
   - Never use a hardcoded import — only use the value from `model.yaml`.

3. **Extract code blocks**: For each target `.md` file, extract all fenced
   ` ```python ` blocks with their line numbers.

4. **Per-block checks**:
   a. **Syntax check** (`py_compile`): Prepend the `canonical_import` line to
      the block and run `python -m py_compile`. A non-zero exit is a **FAIL**.
   b. **Type check** (`mypy`): Run `mypy --ignore-missing-imports --no-error-summary`.
      Any mypy errors are a **WARN** (never FAIL). If mypy is unavailable,
      skip this step silently.

5. **Run the script**:
   ```bash
   # Product-wide:
   .venv/Scripts/python scripts/pipeline/commands/diagnostics/smoke_test.py {family} {platform}

   # Specific files:
   .venv/Scripts/python scripts/pipeline/commands/diagnostics/smoke_test.py --files path/to/file.md
   ```

6. **Report results**:
   ```
   ============================================================
   SMOKE TEST REPORT
   Files checked:  N
   Blocks checked: N
     PASS: N
     WARN: N
     FAIL: N
   ============================================================

   path/to/file.md
     [FAIL] block 2 (line 47): SyntaxError: invalid syntax
     [WARN] block 3 (line 65): TypeWarning: ...

   RESULT: FAIL — N block(s) have syntax errors
   ```

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-63 --status completed
> ```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All blocks PASS (no syntax or type errors) |
| 1 | At least one WARN (type errors only, no syntax errors) |
| 2 | At least one FAIL (syntax error) |

## Integration with eval-page

When `eval-page` is run for a Python-platform product, add this as step 2b:

```
2b. Run smoke test (multi-language: Python, C#, Java, C++, TypeScript):
    .venv/Scripts/python scripts/pipeline/commands/diagnostics/smoke_test.py --files {relative-file-path}
    - Exit code 2 (FAIL): count each failing block as an additional FAIL finding in the eval grade
    - Exit code 1 (WARN): count each warning block as an additional WARN finding
    - Exit code 0 (PASS): no additional findings
```

## Known Limitations

- Multi-block examples (variables defined in block 1 used in block 2) are
  checked independently. This may produce false-positive `NameError` or type
  complaints for variables defined in prior blocks.
- Java, C#, TypeScript, and C++ blocks are checked via tree-sitter syntax
  parsing (grammar-level only — not semantic analysis or type inference).
- `bash` blocks are never checked.
- The syntax check only catches compile-time errors, not runtime errors.

## Post-conditions

- Exit code 0 or 1: page may be committed (type warnings are advisory only)
- Exit code 2: fix all syntax errors before committing the page
- If integrated with `eval-page`: FAIL blocks lower the page grade

## Error handling

- If `model.yaml` missing: WARN and check without import prefix
- If a block has `# noqa` or `# type: ignore` on all lines: still check (these suppress mypy only)
- If pyproject.toml/setup.cfg configures mypy in the repo root, those settings apply
