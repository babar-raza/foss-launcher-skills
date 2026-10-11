# Upstream Issues — cells/java

Genuine defects found in the real upstream repository (`runs/.clone_cache/aspose_cells_java/`)
during clean-room composition/verification. None of these are invented; each cites the exact
file/line evidence.

## The old README's own Installation example quotes a stale dependency version

- **Severity**: VERSION-DRIFT
- **Evidence**: `README.md`'s Installation section shows a `pom.xml` dependency snippet with
  `<version>1.0.0</version>`. The repository's own real `pom.xml` (root, lines 9-10) declares
  `<version>26.5.0</version>`, which matches the live-verified, currently-published Maven Central
  artifact (`data/package_registry.json`'s `cells.java` entry: `verification.published: true`,
  evidence URL `https://repo1.maven.org/maven2/org/aspose/aspose-cells-foss/`, verified
  2026-07-24) and `knowledge/cells/java/merged/model.yaml`'s own `version: 26.5.0` field. `1.0.0`
  is not a real, resolvable version of this artifact on Maven Central.
- **Impact**: a reader who copies the old README's example verbatim gets a dependency resolution
  failure. Not a BLOCKING command (it doesn't fail the build itself, only a dependency-download
  attempt using that exact stale coordinate), but a real, disclosed doc defect.
- **Not fixable here because**: this is the upstream repository's own stale `README.md` content;
  the new candidate's Installation section uses the real, current `26.5.0` instead.

## Four public API classes are unimplemented skeleton code, undisclosed in their own class descriptions

- **Severity**: FUNCTIONAL-DEFECT
- **Evidence**: `SharedStringTableXmlMapper`, `StylesheetXmlMapper`, `WorkbookXmlMapper`, and
  `WorksheetXmlMapper` (all four listed as real public classes in
  `content/reference.aspose.org/en/cells/java/_index.md`'s Core API table, and in
  `knowledge/cells/java/merged/api_surface.md`) have two methods each that unconditionally raise
  `UnsupportedOperationException`. Evidence, `src/main/java/com/aspose/
  cells_foss/xml/WorkbookXmlMapper.java` lines 12-42: the class Javadoc states "This class is not
  implemented in this initial solution skeleton," and both methods (one takes an input stream
  plus model objects, the other an output stream plus model objects) immediately raise that
  exception with no other body. Confirmed identical shape — a permanent raise, no real body — for
  the other 3 classes via `knowledge/cells/java/merged/limitations.md`, which lists all 8
  affected method signatures with file+line. The real, working save/load path used by the
  library's own save method and constructors does not call any of these four classes (confirmed:
  the Quick Start example's `workbook.save("report.xlsx")` and `new Workbook("input.xlsx",
  options)` succeed against real XLSX files without ever touching this internal sub-package — the
  real serialization goes through `XlsxWorkbookSerializer` and related helpers).
- **Impact**: the class-level Javadoc does disclose "not implemented in this initial solution
  skeleton," but the reference-site index's own one-line class descriptions ("Maps shared string
  tables to/from XML", "Maps style information to and from XML", "Maps workbook data to/from
  SpreadsheetML XML format", "Maps worksheet XML data") read as if these classes are functional —
  a consumer browsing the API reference table alone, without opening the Javadoc, would
  reasonably expect a working XML mapper. This looks like leftover scaffold code from the
  project's initial skeleton that was never removed or hidden from the public API surface.
- **Not fixable here because**: this is real, current source structure in the product's own
  repository (the four classes' own method bodies and their absence from the real save/load call
  graph); a README edit cannot implement them or remove them from the public surface. Disclosed
  as a real, verified Scope and Limitations item in the new candidate rather than silently
  omitted.
