# Upstream issues — Aspose.Cells FOSS for TypeScript

Verified: 2026-08-14 against https://github.com/aspose-cells-foss/Aspose.Cells-FOSS-for-TypeScript @ commit cabbb9d8ba2067854f7cb3dcdc4acfeec849747b

## `Workbook.save()` silently writes XLSX binary data when given a `.csv`, `.json`, or `.md`/`.markdown` filename

- **Severity**: FUNCTIONAL-DEFECT
- **Evidence**: In `aspose_cells/workbook.ts`, `detectFormat()` correctly recognizes `.csv`,
  `.json`, `.md`, and `.markdown` extensions and maps them to real `SaveFormat` enum values
  (`SaveFormat.CSV`, `SaveFormat.JSON`, `SaveFormat.MARKDOWN`). However, `save()`'s own
  dispatch logic only special-cases `SaveFormat.HTML` — every other format value, including
  the three correctly-detected ones above, falls through to the default code path, which
  writes the workbook's XLSX ZIP container bytes regardless of the requested format. Calling
  `workbook.save("report.csv")` produces a file named `report.csv` that actually contains
  ZIP/XLSX binary data, not CSV text.
- **Impact**: Any caller who calls `save()` with a `.csv`/`.json`/`.md`/`.markdown` path
  (following the same format-inferring convention `save()` establishes for every other
  supported extension) receives a corrupt, wrongly-typed output file with no error or warning.
- **Not fixable here because**: This is a defect in the library's own `save()` dispatch logic
  (`aspose_cells/workbook.ts`), not something a README edit can work around beyond documenting
  the real, working alternative — `workbook.toCsv()`, `workbook.toJson()`, and
  `workbook.toMarkdown()` are separate, correctly-implemented methods (confirmed real, each
  returning a string) that must be called directly and the result written to a file by the
  caller, bypassing `save()`'s broken dispatch entirely.

## `package.json`'s package name is not Aspose-branded

- **Severity**: INFORMATIONAL
- **Evidence**: `package.json`'s `"name"` field is `"excel-cells"`, not an `@aspose/*`-scoped or
  `aspose-cells-foss`-style name. `data/package_registry.json`'s own tracked candidate name for
  this product is also `"excel-cells"`, with `verification.published: false` (no live npm match
  found as of the most recent backfill scan) — consistent with this being an unpublished,
  internal working name rather than a typo.
- **Impact**: Low — the package is not currently published to npm under any name, so this does
  not block installation (which is source/git-based today). If the package is published in the
  future under this exact name, users may find it confusing that an Aspose product ships under a
  generic, unbranded npm package name.
- **Not fixable here because**: Renaming a package's `"name"` field is a real upstream repository
  change, not something a README can correct.

## A stray, empty top-level `License` file sits alongside the real license text

- **Severity**: INFORMATIONAL
- **Evidence**: The repository root contains two separate paths: `License` (a file, 0 bytes,
  confirmed empty) and `License/LICENSE.txt` (1108 bytes, confirmed real MIT license text
  starting "The MIT License (MIT)\n\nCopyright (c) 2001-2025 Aspose Pty Ltd"). Git treats
  `License` as a directory in the actual working tree (since `License/LICENSE.txt` exists inside
  it), but a stray empty file entry named exactly `License` is also present, which is unusual and
  could confuse tooling or a human browsing the repository root expecting a conventional root
  `LICENSE` file.
- **Impact**: Low — does not block anything; the real license text is present and correctly
  reachable at `License/LICENSE.txt`, which this README links to directly.
- **Not fixable here because**: This is a repository file-structure artifact in the upstream
  repo, not something a README edit can resolve — the recommended fix (removing the stray empty
  entry, or relocating the real license text to a conventional root `LICENSE` path) is an
  upstream repository change.
