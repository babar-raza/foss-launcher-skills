# ADR-004: Python + Tree-Sitter for Knowledge Extraction

**Date:** 2026-04-01
**Status:** Accepted
**Deciders:** @prora

## Context

The knowledge pipeline (S-34: repo-scout) needs to extract structured API information from FOSS repositories in multiple languages: Python, C#, Java, JavaScript, C++, Go, Ruby. The extraction must produce consistent structured output (class names, method signatures, property lists) regardless of source language.

We need a tool that:
- Handles multiple programming languages with a unified interface
- Produces machine-readable ASTs (not regex-based heuristics)
- Can run in a CI environment without language-specific runtimes
- Is maintainable by Python developers

## Decision

We use **tree-sitter** (`tree-sitter>=0.25` with `tree-sitter-language-pack>=0.13`) via Python bindings as the AST parser for knowledge extraction. The scout script (`scripts/scout.py`) uses tree-sitter grammars to parse source files and extract:

- Class declarations and inheritance hierarchies
- Public method signatures (name, parameters, return type)
- Property and field declarations
- Namespace/package structure

Python is chosen as the implementation language because:
- tree-sitter's Python bindings are mature
- The rest of the pipeline (validate_skills, local_gate, path_guard) is already Python
- The `[scout]` optional dependency group isolates tree-sitter from the base install

## Alternatives Considered

- **Regex-based extraction**: Rejected — error-prone for multi-language codebases; doesn't handle nested classes, generics, or complex signatures.
- **Language Server Protocol (LSP)**: Rejected — requires running a language server per language; complex infrastructure for a batch analysis tool.
- **Roslyn (for C#) + language-specific tools**: Rejected — separate toolchain per language, no unified output format.
- **LLM-based extraction**: Rejected as primary — LLMs hallucinate API names; tree-sitter provides ground truth.

## Consequences

- tree-sitter is required for scout operations (`[scout]` extras)
- Tests requiring tree-sitter are marked `@pytest.mark.scout` and excluded from fast CI runs
- Grammar updates may be needed when tree-sitter grammars are revised
- C# extraction requires the separate `tree-sitter-c-sharp>=0.23` package

## Implementation

- Scout script: [`scripts/scout.py`](../../scripts/scout.py)
- Dependencies: [`pyproject.toml`](../../pyproject.toml) `[project.optional-dependencies.scout]`
- Test marker: `pytest.mark.scout` (excluded from fast CI via `-m "not scout"`)
- Output artifacts: `knowledge/{family}/{platform}/scout/` (api_surface.json, class_graph.json, etc.)
