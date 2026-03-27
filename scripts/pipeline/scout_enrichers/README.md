# scout_enrichers/ — API Documentation Enrichers

## Purpose

Extracts human-readable docstrings from FOSS source files to enrich the API surface with descriptions. Called by `extraction/scout.py` after initial AST extraction via `_enrich_docstrings()`.

Enrichers populate the `doc` field on class and method records in `api_surface.json`. This field is used in `api_surface.md` (the LLM-injectable knowledge artifact) and in content generation prompts.

## Enrichers

### _doxygen.py — C++ Doxygen Comments

**`enrich_doxygen(classes: list[dict], repo_dir: Path) -> int`**

Extracts docstrings from C++ Doxygen-style comments:
- Triple-slash: `/// Brief description`
- Block-style: `/** ... */`

Strips `@param`, `@return`, `@throws`, `@see`, `@since` and other Javadoc-style tags. Strips XML-style `<tags>`. Returns the number of class/method records enriched.

Handles `.h`, `.hpp`, and `.cpp` files.

### _javadoc.py — Java Javadoc Comments

**`enrich_javadoc(classes: list[dict], repo_dir: Path) -> int`**

Extracts docstrings from Java Javadoc block comments (`/** ... */`). Walks backward from each class/method declaration line to find the preceding comment block. Strips `@param`, `@return`, `@throws`, `@see`, `@since`, `@deprecated`, `@author` tags.

Returns the number of class/method records enriched.

### _xml_doc.py — .NET XML Doc Comments

**`enrich_xml_doc(classes: list[dict], repo_dir: Path) -> int`**

Extracts docstrings from C# XML documentation comments (`/// <summary>...</summary>`). Walks backward from each class/method declaration collecting consecutive `///` lines. Strips all XML tags (`<summary>`, `<para>`, `<see cref="..."/>`, etc.) leaving clean plain text.

Handles class, interface, struct, enum, and record declarations.

Returns the number of class/method records enriched.

## Integration

`extraction/scout.py` calls enrichers via `_enrich_docstrings()`:

```python
# In extraction/scout.py Scout._enrich_docstrings():
from scout_enrichers import enrich_classes
count = enrich_classes(self.classes, self.repo, self.platform)
```

The `__init__.py` dispatcher (`enrich_classes`) routes to the correct enricher based on platform:

| Platform | Enricher |
|----------|---------|
| `cpp` | `_doxygen.py` — `enrich_doxygen()` |
| `java` | `_javadoc.py` — `enrich_javadoc()` |
| `dotnet` | `_xml_doc.py` — `enrich_xml_doc()` |
| `python`, `typescript`, `javascript` | No enricher (Python docstrings extracted directly via AST) |

## Notes

- Enrichers are optional — if an enricher returns 0 or raises an exception, the pipeline continues without docstrings. No `doc` field means an empty string in the output.
- `extraction/scout.py` loads the `scout_enrichers` package via `importlib.util.spec_from_file_location` to avoid circular import issues at module load time.
- Doxygen enricher handles both `/// triple-slash` and `/** block */` comment styles.
- All enrichers skip records that already have a non-empty `doc` field (idempotent).
- Processing is grouped by source file to minimize disk reads — each file is read once per enricher pass.
