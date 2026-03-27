# extraction/ — FOSS Repository Knowledge Extraction

Contains the AST-based extraction engine for FOSS source repositories. Called by the top-level `scout.py` CLI entry point.

## Supported Platforms

| Platform key | Tree-sitter language | File extension |
|-------------|---------------------|---------------|
| `python` | `python` | `.py` |
| `dotnet` | `csharp` | `.cs` |
| `java` | `java` | `.java` |
| `cpp` | `cpp` | `.cpp`, `.h`, `.hpp` |
| `typescript` | `typescript` | `.ts` |
| `javascript` | `javascript` | `.js` |
| `nodejs` | `javascript` | `.js` |

## Modules

### scout.py — Scout Orchestration Class

The main extraction orchestrator. Top-level `scout.py` re-exports `Scout` from here.

```python
from extraction.scout import Scout

s = Scout(family="3d", platform="python",
          repo=Path("runs/.clone_cache/aspose_3d_python"),
          output=Path("knowledge/3d/python/scout"))
s.run()
```

`Scout.run()` executes these steps in order:
1. `_extract_api_surface()` — AST traversal via tree-sitter
2. `_enrich_docstrings()` — populate `doc` fields using `scout_enrichers/`
3. `_detect_formats()` — scan for file format support
4. `_detect_limitations()` — scan for `NotImplementedException` / `raise NotImplementedError`
5. `_extract_snippets()` — extract code examples from tests/examples directories
6. `_build_identity_claims()` — package identity claims from manifest
7. `_build_class_graph()` — inheritance relationships
8. `_build_coverage()` — per-class coverage matrix
9. `_write_outputs()` — write all artifacts to output directory
10. `_log_extraction_quality()` — log return_type_fill_rate, property_fill_rate, has_tests_fill_rate

### api_surface.py — API Surface Extraction

Extracts classes, methods, properties, and enum values via tree-sitter AST traversal.

```python
from extraction.api_surface import extract_api_surface

classes, claims, scanned_files, packages = extract_api_surface(
    parser, language, pkg_root, repo, family)
```

Each class record has: `name`, `kind`, `file`, `line`, `methods`, `properties`, `enum_members`, `bases`, `doc`.

### tree_helpers.py — Parser Loading and Tree Utilities

Language constants and generic tree-sitter helper functions.

| Symbol | Description |
|--------|-------------|
| `PLATFORM_TO_LANG` | Maps platform key → tree-sitter language name |
| `_CLASS_TYPES` | Per-language AST node type sets for class declarations |
| `_FUNC_TYPES` | Per-language AST node type sets for method/function declarations |
| `_FILE_EXTENSIONS` | Per-language source file extension |
| `MAX_FILES` | File cap (500) for `_collect_source_files` |
| `get_parser(language)` | Load tree-sitter parser for a language |
| `collect_nodes(node, types)` | Recursively collect nodes of given types |
| `node_text(node, source)` | Extract UTF-8 text for a node |
| `child_by_field(node, field)` | Get first child with a named field |
| `find_child_by_type(node, type)` | Get first child of a node type |
| `find_children_by_type(node, type)` | Get all children of a node type |
| `is_public(node, language)` | True if node has public visibility modifier |
| `_collect_source_files(root, ext)` | Glob source files up to MAX_FILES |
| `_extract_bases(node, language, src)` | Extract base class names |
| `_extract_enum_members(node, language, src)` | Extract enum member names |

### formats.py — Format Detection

Scans source files for file format constants and flags import/export support.

```python
from extraction.formats import detect_formats

formats, claims = detect_formats(parser, language, pkg_root, repo, family)
```

Each format record has: `name` (or `format`), `can_import`, `can_export`, `direction`.

### claims.py — Identity Claim Generation

Builds basic package identity claims from the parsed manifest.

```python
from extraction.claims import build_identity_claims

claims = build_identity_claims(manifest, family)
```

### snippets.py — Code Example Extraction

Extracts function-level code examples from test files and examples/samples directories.

```python
from extraction.snippets import extract_snippets

snippets = extract_snippets(parser, language, pkg_root, repo, classes, formats)
```

Scans these directories: `tests`, `test`, `examples`, `example`, `samples`, `demo`.

Each snippet record has: `id`, `source_file`, `source_function`, `classes_used`, `lang`, `file`.

### outputs.py — Artifact Writer

Writes all extraction artifacts to the output directory.

```python
from extraction.outputs import write_outputs

write_outputs(output=Path("knowledge/3d/python/scout"), family="3d", platform="python",
              manifest=manifest, classes=classes, claims=claims, ...)
```

### package_root.py — Package Root Detection

Detects the root of the extractable package within a cloned repo.

```python
from extraction.package_root import detect_package_root

pkg_root = detect_package_root(repo, platform)
```

### package_manifest.py — Package Manifest Parser

Reads `pyproject.toml`, `setup.py`, `pom.xml`, `.csproj`, and `package.json` for package metadata.

```python
from extraction.package_manifest import parse_manifest

manifest = parse_manifest(repo, platform)
# manifest keys: name, version, description, license, homepage, ...
```

## Output Artifact Set (scout/ directory)

| File | Description |
|------|-------------|
| `api_surface.json` | List of class/enum/interface records with methods and properties |
| `claims.json` | Structured claims with `claim_id`, `kind`, `text`, `confidence=1.0`, `claim_source="scout"` |
| `formats.json` | Supported file formats with `can_import`/`can_export` flags |
| `model.yaml` | Metadata: family, platform, version, license, repo_url, repo_sha |
| `snippets/snippets_index.json` | Code example index |
| `snippets/snippet_NNN.{ext}` | Individual snippet files |
| `class_graph.json` | Inheritance relationships |
| `coverage_matrix.json` | Per-class coverage stats |
| `limitations.md` | Table of `NotImplemented` locations |
| `install.md` | Install command |
