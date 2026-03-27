# S-38: Truth Audit — Deep Member-Level API Verification

**Arguments**: $ARGUMENTS
Expected format: `{relative-file-path}` or `{family} {platform}`

## Purpose
Perform deep member-level API verification beyond what `audit.py` (S-23) checks. While audit.py verifies that API tokens exist in the surface, truth-audit validates parameter types, method call sequences, and return type usage against the full method signatures in `api_surface.json`.

## Pre-conditions
1. **Knowledge bootstrap**: Run `/knowledge-bootstrap {family} {platform}` and check status:
   - `STOP:partial` → halt (see printed message)
   - Any other status (`READY`, `BOOTSTRAPPED`, `REFRESHED`, `WARN:conflicts`) → continue
2. `knowledge/{family}/{platform}/merged/api_surface.json` must exist with full method signatures after bootstrap
3. Target content file(s) exist under `content/`
4. `knowledge/{family}/{platform}/merged/claims.json` exists for cross-referencing capability claims

## Steps

1. **Parse arguments**: Determine scope — single file or all files for `{family}/{platform}`.

2. **Load API surface**: Read `knowledge/{family}/{platform}/merged/api_surface.json`. Build a lookup of:
   - Class → methods → parameters (name, type, required/optional)
   - Class → methods → return type
   - Class → properties → type
   - Class inheritance relationships (from `knowledge/{family}/{platform}/merged/class_graph.json` if available)

3. **For each content file**, extract all code blocks and analyze:

   **Parameter type verification**:
   - For each method call `obj.method(arg1, arg2)`, check:
     - Number of arguments matches method signature (accounting for optional params)
     - If argument types can be inferred (string literals, numeric literals, enum values), verify they match expected parameter types
     - Flag calls with too many or too few arguments

   **Method call sequence plausibility**:
   - Track object creation: `obj = ClassName()` or `obj = factory_method()`
   - Verify subsequent method calls are valid for the object's type
   - Check that methods are called in plausible order (e.g., don't call `.save()` before `.load()`)
   - Verify constructor parameters match signature

   **Return type usage**:
   - If `result = obj.method()`, check that subsequent `result.X` calls are valid for the return type
   - Flag cases where return value is used as wrong type

   **Property access verification**:
   - For `obj.property` access, verify property exists on the class
   - Check property is not write-only when read, or read-only when written

   **Enum/constant verification**:
   - Verify enum values used in code exist in the API surface
   - Check that enum type matches parameter expectation

4. **Cross-reference with claims**: For each code example, verify it demonstrates what the surrounding prose claims it does (e.g., if text says "export to GLB", the code should contain a save/export call with GLB-related parameters).

5. **Output audit report**:
   ```
   TRUTH AUDIT (DEEP) — {scope}
   Product: {family}/{platform}
   Files analyzed: {count}
   Code blocks analyzed: {count}

   FINDINGS:

   {file-path}:
     Line {N}: FAIL — {ClassName}.{method}() called with {X} args, expects {Y}
     Line {N}: WARN — Return type of {method}() is {type}, but used as {other_type}
     Line {N}: FAIL — {ClassName}.{property} does not exist in API surface
     Line {N}: WARN — Method call sequence: {method2} called before {method1}
     Line {N}: FAIL — Enum value {value} not found in {EnumType}

   SUMMARY:
     FAIL: {count}  WARN: {count}  PASS: {count}
     OVERALL: PASS | WARN | FAIL

   PROSE-CODE ALIGNMENT:
     {file}: {ALIGNED | MISALIGNED} — {description}
   ```

## Post-conditions
- Every code block in scope has been deep-verified against API signatures
- Parameter counts and types are validated where determinable
- Method call sequences are checked for plausibility
- Return type usage is validated
- Report is produced with specific line numbers and fix suggestions
- No file modifications made (read-only skill)

## Error handling
- If `api_surface.json` lacks full signatures (only class/method names), fall back to basic token verification and note that deep audit was partial
- If `class_graph.json` is unavailable, skip inheritance-based checks
- If no code blocks found in a file, report as N/A (not a failure)
