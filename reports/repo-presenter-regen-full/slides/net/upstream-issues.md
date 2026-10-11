# Upstream issues — Aspose.Slides FOSS for .NET

Verified: 2026-08-13 against the checked-out clone cache
(`runs/.clone_cache/aspose_slides_net`, pinned SHA `bd19e16057b628310b4a04330585d366cb40e9b7`) for
`https://github.com/aspose-slides-foss/Aspose.Slides-FOSS-for-.NET`.

## LoadOptions declares Ppt/Odp source formats but Presentation.Open only reliably reads PPTX-family OPC packages
- **Severity**: INFORMATIONAL
- **Evidence**: `Presentation.InitFromFile(string path)` calls `OpcPackage.Open(path)` — an
  OPC/ZIP-package reader — unconditionally, then `DetectSourceFormat(path)` merely records a
  `SourceFormat` value (`Ppt`, `Pptx`, or `Odp`) from the file extension for bookkeeping; it does
  not select a different parser. `.ppt` is the legacy binary (CFB, not ZIP) format, and `.odp`
  uses a different OOXML-incompatible part/namespace layout than `.pptx`/`.pptm`/`.ppsx`/`.potx`.
  Neither is exercised by the test suite's real fixture files (checked
  `tests/Aspose.Slides.Foss.Tests` and `tests/Aspose.Slides.Foss.IntegrationTests` for `.ppt`/
  `.odp` sample assets — none found), and `knowledge/slides/net/merged/formats.md` marks both
  Import and Export as `-` (unsupported) for every non-PPTX row.
- **Impact**: `SourceFormat.Ppt`/`SourceFormat.Odp` and the extension-based detection that sets
  them exist in the public surface, but opening a real `.ppt`/`.odp` file is not a verified,
  working path — it would most likely fail at `OpcPackage.Open()` (not a ZIP container, for
  `.ppt`) or fail later while resolving OOXML-specific parts (for `.odp`), rather than being
  silently mis-read like the `Save()` case above.
- **Not fixable here because**: this reflects the library's current, real implementation scope
  (PPTX-family OPC packages only); confirmed by reading `Presentation.cs`'s `InitFromFile`/
  `DetectSourceFormat` methods directly, not by executing an end-to-end `.ppt`/`.odp` load (no
  such fixture exists in this checkout to run against).

No other undisclosed BLOCKING install/build defects were found. A plain restore/build/test
sequence and both real test projects build and run through the project's own CI workflow on both
Linux and Windows runners with no special flags or hidden prerequisites.
