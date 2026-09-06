# Upstream issues — Aspose.3D FOSS for TypeScript

Verified: 2026-08-13 against https://github.com/aspose-3d-foss/Aspose.3D-FOSS-for-TypeScript.git @ repo_sha 227894a1120c22b9b6522564e23dc1d14c8fc39a (pinned clone-cache HEAD at that time)

Re-verified: 2026-08-20 against the current pinned clone-cache HEAD, repo_sha
7b959706f2ad976db929f26ec079f43a07d578e1 (commit "Refresh README: verified API accuracy,
simplified diagram, restored content (#2)") -- the clone cache advanced since the 2026-08-13 pass.
All 4 findings below from that pass were independently re-confirmed still real and current
(`adm-zip`/devDependency, `main`/`types` entry point, missing `LICENSE` file, `Watermark`
not-implemented). 4 new findings added from this pass (OBJ import material non-assignment, OBJ
export traversal-gating bug, binary GLB export RangeError, glTF export-then-reimport duplicate
top-level nodes) -- all confirmed with real, executable test evidence (existing repo tests plus
purpose-built probe scripts run against the real compiled library via `npx jest`), not source
inspection alone.

## `adm-zip` is required at runtime by the 3MF importer/exporter but is only declared as a devDependency

- **Severity**: BLOCKING
- **Evidence**: `src/aspose/threed/formats/threemf/ThreeMfExporter.ts:162` calls
  `new (require('adm-zip'))()` and `src/aspose/threed/formats/threemf/ThreeMfImporter.ts:53-54`
  calls `require('adm-zip')` directly — both are real, unconditional runtime `require` calls, not
  test-only code. `package.json`'s `dependencies` block contains only `{"xmldom": "^0.6.0"}`;
  `adm-zip` (`^0.5.16`) is listed exclusively under `devDependencies`. A clean
  `npm install @aspose/3d` in a consumer project therefore does not install `adm-zip`, and any
  attempt to import or export a `.3mf` file throws `Error: Cannot find module 'adm-zip'` at
  runtime unless the consumer's own project happens to already depend on `adm-zip` for an
  unrelated reason.
- **Impact**: Every consumer of this library who tries to use the advertised 3MF import/export
  capability in a normal production install hits a hard runtime failure. The failure is silent
  until the 3MF code path is actually exercised — `npm install` and TypeScript compilation both
  succeed cleanly.
- **Not fixable here because**: This is a `package.json` dependency-declaration defect in the
  product's own repository — no README edit can change what gets installed by `npm install` for
  downstream consumers.

## `package.json`'s declared `main`/`types` entry point is never produced by the real build

- **Severity**: BLOCKING
- **Evidence**: `package.json` declares `"main": "dist/index.js"` and `"types": "dist/index.d.ts"`.
  `tsconfig.json` sets `"rootDir": "./src"` and `"outDir": "./dist"`, with no `src/index.ts` file
  anywhere in the repository (confirmed: `find src -iname index.ts` returns only nested
  submodule barrels — `src/aspose/threed/index.ts`, `src/aspose/threed/formats/index.ts`, and
  similar — never a top-level `src/index.ts`). Running `tsc` per `npm run build` therefore never
  produces `dist/index.js`; the real compiled entry point is `dist/aspose/threed/index.js`.
- **Impact**: Any consumer who installs this package (once published) and does
  `import { Scene } from '@aspose/3d'` or `require('@aspose/3d')` gets a module-resolution
  failure, because the file Node.js looks up via `package.json`'s own `main` field does not exist.
- **Not fixable here because**: This is a `package.json`/build-configuration mismatch inside the
  product's own repository — no README edit changes what the real build produces or what
  `package.json` declares.

## Old README's License section links a `LICENSE` file that does not exist in the repository

- **Severity**: INFORMATIONAL
- **Evidence**: The repository root (verified via a case-insensitive listing of the full clone
  cache) contains no `LICENSE`, `LICENSE.txt`, `LICENSE.md`, or any case variant — `package.json`
  declares `"license": "MIT"` but no license text file is actually checked in. The old README's own
  `## License` section nonetheless reads "see the [LICENSE](LICENSE) file for details," a broken
  relative link on GitHub.
- **Impact**: A visitor who clicks the old README's License link gets a 404 on GitHub rather than
  the actual license text.
- **Not fixable here because**: Adding a real `LICENSE` file is a repository change outside a
  README edit; this candidate instead uses the correct unlinked MIT License template sentence
  rather than repeating the broken link.

## `Watermark.encodeWatermark()`/`decodeWatermark()` are entirely unimplemented despite being a
   named, public class

- **Severity**: FUNCTIONAL-DEFECT
- **Evidence**: `Watermark` is a real, exported public class documenting text-watermark
  embed/extract functionality. Both `encodeWatermark()` and `decodeWatermark()` unconditionally
  `throw new Error('... is not implemented')` in every code path — there is no working text
  watermarking anywhere in this class. **This is the identical defect, in the identical class,
  independently confirmed on the sibling `3d/net` platform** (see `aspose-3d-foss`'s .NET port,
  where `Watermark.EncodeWatermark`/`DecodeWatermark` throw `NotImplementedException` the same
  way) — strong evidence this is a real, cross-platform gap in the underlying library design or
  port process, not a one-off omission specific to this TypeScript port.
- **Impact**: a caller who finds `Watermark` in the public API surface and calls either method
  gets an immediate, unconditional exception on every invocation — the class currently has no
  functional use on any platform in this product family checked so far.
- **Not fixable here because**: this is a missing implementation in the product's own source, not
  something a README edit can resolve. The new README candidate documents this explicitly in
  Scope and Limitations rather than presenting text watermarking as a working capability.

## OBJ import recognizes `usemtl` but never assigns the referenced material

- **Severity**: FUNCTIONAL-DEFECT
- **Evidence**: `src/aspose/threed/formats/obj/ObjImporter.ts:193-194` has
  `} else if (keyword === 'usemtl' && oOptions.enableMaterials) {\n}` — the branch body is
  completely empty. `mtllib` (the OBJ keyword that declares which `.mtl` file to load) is not
  handled anywhere in this file or anywhere else in the repository (`grep -rn mtllib src/` returns
  nothing outside a content-sniffing heuristic in `Scene.ts` that only checks for the substring to
  guess the file is OBJ-shaped). Confirmed by a purpose-built test: importing a hand-authored OBJ
  buffer containing `usemtl MyMaterial` with `ObjLoadOptions.enableMaterials = true` (the default)
  produces a node with `node.material === null`.
- **Impact**: Any consumer relying on `enableMaterials` to bring in per-face material assignment
  from an imported OBJ file gets silently no material at all, regardless of the option's value.
- **Not fixable here because**: this is a missing implementation in the product's own source, not
  something a README edit can resolve. The new README candidate documents this explicitly in
  Scope and Limitations and the API Reference `ObjImporter`/`ObjLoadOptions` rows.

## OBJ export silently produces no output for the standard scene-construction pattern

- **Severity**: BLOCKING
- **Evidence**: `src/aspose/threed/formats/obj/ObjExporter.ts`'s private `_collectNodes(node, ...)`
  gates its entire body — including the recursive walk into `node.childNodes` — behind
  `if (mesh !== undefined && ...)`, where `mesh = node.entity`. Since `scene.rootNode` itself never
  carries an entity in ordinary usage (real meshes are attached to children via
  `scene.rootNode.createChildNode(...).entity = mesh`, the pattern used throughout this very
  README and the product's own test suite), the very first call — on `scene.rootNode`, which has
  no entity — fails this check and returns immediately, so no descendant is ever visited. Confirmed
  by a purpose-built test: a scene built with the standard child-node pattern exports to a
  completely empty `.obj` file (no `fs.writeFileSync` call is even reached, since the joined
  content is the empty string); the identical scene with the mesh attached directly to
  `scene.rootNode` instead exports real content. Separately, when export does produce output,
  material data (`newmtl`/`Kd/Ka/Ks/Ns/d` lines from `_writeMaterial`) is appended directly
  into the same `.obj` stream with no `mtllib`/`usemtl` directive anywhere and no second,
  companion `.mtl` file is ever written (`fs.existsSync` on the expected companion path returns
  false) — confirmed the same way.
- **Impact**: OBJ export is non-functional for the scene-construction pattern this README (and
  every sibling platform's README) demonstrates and recommends; the only construction pattern that
  produces output (attaching the mesh directly to `scene.rootNode`, never to a child node) is not
  demonstrated anywhere and does not match how any other exporter in this library is used.
- **Not fixable here because**: this is a real bug in the product's own `ObjExporter`
  implementation, not something a README edit can resolve. The new README candidate documents this
  explicitly in Scope and Limitations and the API Reference `ObjExporter` row, and no longer lists
  OBJ as a working Output format in the "At a Glance" diagram.

## Binary glTF export throws `RangeError` for any non-empty mesh

- **Severity**: BLOCKING
- **Evidence**: The product's own existing test, `tests/test_gltf_exporter.test.ts`'s
  `testSimpleTriangleBinary`, fails at the currently pinned revision:
  `RangeError: The value of "offset" is out of range. It must be >= 0 and <= 636. Received 640`,
  thrown from `GltfExporter._writeGlb` (`src/aspose/threed/formats/gltf/GltfExporter.ts:419`,
  `glbBuffer.writeFloatLE(binaryBuffer[i], offset)`) — a real buffer-length miscalculation in the
  binary-chunk padding/allocation logic, not a test-harness issue (10 of the suite's other 11
  tests pass; only the one exercising `binaryMode: true` against a non-empty mesh fails).
  Independently confirmed the SAME way this file's original 2026-08-13 pass found it (the old
  upstream README's own "Convert STL to GLTF" example already carried this exact caveat verbatim);
  this pass re-ran the real test rather than trusting that old prose. Binary GLB **import** is
  unaffected: a purpose-built test hand-constructing a spec-correct GLB container (12-byte header +
  a 4-byte-aligned JSON chunk, wrapping a known-good JSON glTF export) round-trips correctly
  through `Scene.open()`/`GltfImporter`.
- **Impact**: any consumer attempting `GltfSaveOptions.binaryMode = true` on a scene with real mesh
  geometry gets an immediate, unconditional exception; only the JSON/ASCII glTF export path
  (`binaryMode: false`, the default) is currently usable.
- **Not fixable here because**: this is a real bug in the product's own `GltfExporter`
  implementation, not something a README edit can resolve. The new README candidate documents this
  explicitly in Scope and Limitations, the API Reference `GltfExporter`/`GltfSaveOptions` rows, and
  no longer lists GLB as a working Output format in the "At a Glance" diagram (GLB stays listed on
  the Starting Points/import side, where it is confirmed working).

## Re-importing a glTF file this library exported can produce extra, duplicate top-level nodes

- **Severity**: FUNCTIONAL-DEFECT
- **Evidence**: A purpose-built test built a single-node scene (`scene.rootNode.childNodes.length`
  === 1, named `TestNode`), exported it via `scene.save(path, GltfFormat.getInstance())` (JSON
  glTF, not binary — isolating this from the separate binary-export defect above), then re-opened
  the exported file into a fresh `Scene`. The reimported scene has 2 top-level nodes
  (`['node_0', 'TestNode']`), not 1 — a real, reproducible round-trip defect in either the exporter
  (writing an extra wrapper node) or the importer (introducing one on read), not narrowed further
  here. Confirmed the same way this file's original 2026-08-13 pass found it (the old upstream
  README's own Scope and Limitations already carried this exact caveat); this pass re-ran a fresh
  executable test rather than trusting that old prose.
- **Impact**: code that assumes a re-imported, self-produced glTF scene has the same top-level node
  structure as the original will see an unexpected extra node. Importing glTF files produced by
  other tools is unaffected (only the self-export-then-reimport round trip is implicated).
- **Not fixable here because**: this is a real bug in the product's own glTF export/import pair,
  not something a README edit can resolve. The new README candidate documents this explicitly in
  Scope and Limitations.

No other upstream issues identified during verification.
