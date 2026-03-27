# verification/ — Token Extraction & Verification (Re-export Namespace)

## Purpose

This package provides a clean, discoverable namespace for the token extraction and verification layer. It is a **transparent re-export shim** over `token_ops.py` — all logic lives in `token_ops.py`; these modules contain only import re-exports.

Both import paths work simultaneously. Backward compatibility with `token_ops.py` is maintained. The `verification/` namespace is preferred for new code.

## Modules

### extractor.py

Re-exports `extract_tokens`, `_extract_from_code_line`, and `Token` from `token_ops`.

**`extract_tokens(filepath: Path, platform: str) -> list[Token]`**

Scans a content page (markdown) and extracts all API token references from code blocks. Returns a list of `Token` objects.

**`Token`** fields: `kind`, `class_name`, `member_name`, `line_no`, `raw_text`

### verifier.py

Re-exports `verify_tokens` and `Finding` from `token_ops`.

**`verify_tokens(tokens: list[Token], knowledge: Knowledge, filepath: Path) -> list[Finding]`**

Checks each token against the merged `api_surface.json` knowledge model. Returns a list of `Finding` objects.

**`Finding`** fields: `level` (`FAIL`/`WARN`/`INFO`), `filepath`, `line_no`, `message`, `suggestion`

## Usage

```python
# Preferred (new namespace):
from verification.extractor import extract_tokens, Token
from verification.verifier import verify_tokens, Finding

tokens = extract_tokens(Path("content/docs.aspose.org/en/3d/python/index.md"), "python")
findings = verify_tokens(tokens, knowledge, filepath)

for f in findings:
    if f.level == "FAIL":
        print(f"  FAIL L{f.line_no}: {f.message}")
```

```python
# Legacy (still works):
from token_ops import extract_tokens, verify_tokens, Token, Finding
```

## Relationship to token_ops.py

`token_ops.py` (at the pipeline root level) is the **sole implementation**. `verification/` simply re-exports from it.

- Do not duplicate logic between `verification/` and `token_ops.py`
- If you need to change extraction or verification behavior, edit `token_ops.py`
- The sub-module `sys.path` guard in each file ensures `token_ops` is importable when the package is used as a sub-package import

## Finding Levels

| Level | Meaning |
|-------|---------|
| `FAIL` | Class or member not found in `api_surface.json` |
| `WARN` | Probable match but not directly confirmed (e.g., inherited member) |
| `INFO` | Advisory information (e.g., no evidence block) |
