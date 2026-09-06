# S-63: Code Smoke — Syntax and Type-Check Code Blocks

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}` or `--files {path1} [path2 ...]`

## Purpose

Check that code blocks in content pages are syntactically valid. Supports
Python (via `py_compile` and `mypy`), Java, C#, TypeScript, C++, Go, and Rust
(via tree-sitter grammar parsing). **Never executes code by default** —
syntax/type-check only at `--max-tier 2` (the default); a real execution
tier is not wired into this CLI yet (see "Relationship to
lib/example_verification/" below).

S-63 is the skill identity for the central example-verification module
(MT065-2026-09-06-EXAMPLE-VERIFICATION-CENTRALIZATION mission): the tree-
sitter loader, the platform/language declarations, and (eventually) the
runner dispatch all live in `scripts/pipeline/lib/example_verification/`,
with this script as the CLI surface over it. No new skill ID was minted for
that package — S-63 absorbed it.

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

   # Specific files (languages auto-detected from each file's own fence tags
   # when no --lang/platform is given -- see "Language auto-detection" below):
   .venv/Scripts/python scripts/pipeline/commands/diagnostics/smoke_test.py --files path/to/file.md

   # Explicit language override:
   .venv/Scripts/python scripts/pipeline/commands/diagnostics/smoke_test.py --files path/to/file.md --lang java,csharp

   # Tier 1 (syntax-only, skips Python's mypy step) or --json output:
   .venv/Scripts/python scripts/pipeline/commands/diagnostics/smoke_test.py {family} {platform} --max-tier 1
   .venv/Scripts/python scripts/pipeline/commands/diagnostics/smoke_test.py {family} {platform} --json
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
| 1 | At least one WARN (type errors only, or a missing tree-sitter grammar, no syntax errors) |
| 2 | At least one FAIL (syntax error) |

`--json` emits the same PASS/WARN/FAIL data as machine-readable JSON on
stdout instead of the human-readable report, with the identical exit code.

## Language auto-detection (2026-09-06 fix)

A bare `--files {path}` invocation with no `--lang`/`{family} {platform}`
used to hardcode the language set to `{"python"}` regardless of the file's
real content — silently skipping every non-Python block (RC22: this
skill's own "Integration with eval-page" section below claimed
"multi-language" checking for exactly this call shape while the code
underneath only ever checked Python). Language tags are now auto-detected
by scanning the file's own fence tags and intersecting with every language
this script can syntax-check, falling back to `{"python"}` only when no
known language is found — a Python-only page's behavior is unchanged; a
Java/C#/TypeScript/C++/Go/Rust-only page is now actually checked via this
call path for the first time.

## Integration with eval-page

When `eval-page` is run for any platform, add this as step 2b:

```
2b. Run smoke test (multi-language: Python, C#, Java, C++, TypeScript, Go, Rust):
    .venv/Scripts/python scripts/pipeline/commands/diagnostics/smoke_test.py --files {relative-file-path}
    - Exit code 2 (FAIL): count each failing block as an additional FAIL finding in the eval grade
    - Exit code 1 (WARN): count each warning block as an additional WARN finding
    - Exit code 0 (PASS): no additional findings
```

This claim is now actually true for every platform (see "Language
auto-detection" above) — before the 2026-09-06 fix it was only true for
Python-platform products.

## Relationship to lib/example_verification/

The tree-sitter loader (`_ts_parser_for`) and the platform/language
declarations (`_PLATFORM_LANGS`/`_TS_LANG_MAP`) are no longer independent
copies in this script — both are derived from the shared
`scripts/pipeline/lib/example_verification/` package (`syntax.py` and
`registry.py` respectively), the same package `readme-refresh` (S-120)'s
real Python/TypeScript verification runners were extracted into. This is
why Go is now a declared platform here (it wasn't before): the shared
`registry.py` already declared it, and this script's own hardcoded dicts
were the only place that hadn't caught up.

A real execution tier (compiling and running code, not just parsing it)
exists in the shared package's `runners/python.py`/`runners/typescript.py`
but is **not yet dispatched from this CLI** — `--max-tier` today only
distinguishes tier 1 (syntax-only) from tier 2 (syntax + Python's mypy
type-check, this script's original default behavior). Wiring a real
`--acquire`/tier-3 flag here is later work, once the package exposes a
stable `api.py` entrypoint for it.

## Known Limitations

- Multi-block examples (variables defined in block 1 used in block 2) are
  checked independently. This may produce false-positive `NameError` or type
  complaints for variables defined in prior blocks.
- Java, C#, TypeScript, C++, Go, and Rust blocks are checked via tree-sitter
  syntax parsing (grammar-level only — not semantic analysis or type
  inference). A genuinely missing tree-sitter grammar on the running machine
  is reported as a WARN (`GRAMMAR-UNAVAILABLE`), never silently as PASS.
- `bash` blocks are never checked.
- The syntax check only catches compile-time errors, not runtime errors —
  this script never executes code (see "Relationship to
  lib/example_verification/" above for what a real execution tier would need).

## Post-conditions

- Exit code 0 or 1: page may be committed (type warnings are advisory only)
- Exit code 2: fix all syntax errors before committing the page
- If integrated with `eval-page`: FAIL blocks lower the page grade

## Error handling

- If `model.yaml` missing: WARN and check without import prefix
- If a block has `# noqa` or `# type: ignore` on all lines: still check (these suppress mypy only)
- If pyproject.toml/setup.cfg configures mypy in the repo root, those settings apply
