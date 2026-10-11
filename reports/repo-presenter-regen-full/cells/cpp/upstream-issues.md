# Upstream Issues — cells/cpp

## 1. `Aspose.Cells.Foss.Cpp.Tests/README.md` documents a broken build path

**Severity**: INFORMATIONAL — the nested test project's own README gives unusable paths, but
this composed README does not point a reader at those commands; it gives corrected ones directly
in its own Development and Testing section, so no reader of this README hits the broken path.

**Evidence**: `runs/.clone_cache/aspose_cells_cpp/Aspose.Cells.Foss.Cpp.Tests/README.md` lines 7-9
and 14-15 give these commands:

```powershell
cmake -S .\workspace\Aspose.Cells.Foss.Cpp.Tests -B .\workspace\Aspose.Cells.Foss.Cpp.Tests\build\debug-fc
cmake --build .\workspace\Aspose.Cells.Foss.Cpp.Tests\build\debug-fc --config Debug -- /p:VcpkgApplocalDeps=false
...
ctest --test-dir .\workspace\Aspose.Cells.Foss.Cpp.Tests\build\debug-fc -C Debug --output-on-failure
```

These paths assume the test project lives under a `workspace/` directory at the repository root
(`workspace/Aspose.Cells.Foss.Cpp.Tests/...`). A direct listing of the actual clone
(`runs/.clone_cache/aspose_cells_cpp/`) shows no `workspace/` directory anywhere — the real
layout is `Aspose.Cells.Foss.Cpp.Tests/` directly at the repo root, alongside `Aspose.Cells.Foss.Cpp/`,
`samples/`, and `License/`. Running the documented commands as written from a fresh clone fails
immediately (`cmake` cannot find `-S .\workspace\...`, since the path does not exist). This looks
like a leftover from a different internal directory layout (a monorepo/build-orchestration
"workspace" root) that never got updated when the project was published as a standalone
repository.

**Workaround used in the composed README's Development and Testing section**: run the same
commands with the real, current relative paths —

```bash
cd Aspose.Cells.Foss.Cpp.Tests
cmake -S . -B build
cmake --build build
ctest --test-dir build --output-on-failure
```

— verified against the real, on-disk `Aspose.Cells.Foss.Cpp.Tests/CMakeLists.txt`, which
correctly resolves its `aspose_cells_foss` library dependency via
`add_subdirectory("${ASPOSE_CELLS_FOSS_CPP_ROOT}" ...)` with a relative default of
`../Aspose.Cells.Foss.Cpp` — consistent with the test project sitting directly at the repo root,
not under `workspace/`.

## 2. Two false "unimplemented stub" signals in `knowledge/cells/cpp/merged/limitations.md`

**Severity**: INFORMATIONAL — a knowledge-layer/other-page data-quality note, not a defect in the
product itself; disclosed for visibility, not because it blocks anything this README asserts.

Not an upstream (FOSS repo) defect, but a data-quality issue in the knowledge-extraction layer
that would have produced real, false claims in this README if trusted verbatim — disclosed here
per this run's own "genuine defect found during verification" instruction.

`limitations.md` flags ~60 classes (e.g. `Workbook`, `Cell`, `ConditionalFormattingCollection`,
`AutoFilter`, `WorkbookProtection`, ...) as having "an empty body (unimplemented stub)". Direct
inspection of the real source shows this is a scout-heuristic false positive: it is matching each
class's *constructor*, which legitimately has an empty `{}` body after an initializer list (e.g.
`Cell::Cell(...) : _worksheet(worksheet), _address(address) {}`,
`Workbook::Workbook() : _impl(std::make_unique<Impl>()) { ... }`), not a genuinely-missing
implementation. `ConditionalFormattingCollection` and `AutoFilter` (both flagged) are fully
implemented with real, working methods — confirmed by reading
`Aspose.Cells.Foss.Cpp/src/aspose/cells_foss/ConditionalFormattingCollection.cpp`,
`FormatCondition.cpp`, `FormatConditionCollection.cpp`, and `AutoFilter.cpp` in full.

This same false signal has already leaked into two live, shipped content pages that this task's
boundaries prohibit editing, disclosed here for visibility rather than silently worked around:

- `content/products.aspose.org/en/cells/cpp/_index.md`'s FAQ block states: "Several classes in
  v0.1 are declared but stub-only, including `ConditionalFormattingCollection` and `AutoFilter`"
  — contradicted by the direct source read above.
- The same page's FAQ and `content/docs.aspose.org/en/cells/cpp/_index.md`'s `description` both
  state or imply `.csv` load support ("`.csv` load is supported; `.csv` save is not available in
  v0.1." / "read, write, and manipulate spreadsheets in XLSX and CSV formats") — a case-insensitive
  search for `csv` across the entire clone cache's `Aspose.Cells.Foss.Cpp/include` and `src` trees
  returns zero matches. `LoadFormat`/`SaveFormat` each declare exactly one member, `Xlsx`. There is
  no CSV support anywhere in the current source.

This composed README's Key Capabilities, API Reference, and Scope and Limitations sections were
written directly from source (not from `limitations.md`) specifically to avoid carrying these two
false claims forward.

No other genuine upstream defects (broken example code, contradicted test behavior, etc.) were
found during composition or verification.
