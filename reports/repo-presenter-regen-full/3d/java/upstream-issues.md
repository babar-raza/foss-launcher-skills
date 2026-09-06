# Upstream issues — Aspose.3D FOSS for Java

Verified: 2026-08-13 against https://github.com/aspose-3d-foss/Aspose.3D-FOSS-for-Java.git @ 35963f673e0811285d6b1ad0911fd7171bf70f41 (clone cache HEAD, runs/.clone_cache/aspose_3d_java)

## glTF and FBX import/export are silent no-op stubs, not disclosed as such

- **Severity**: FUNCTIONAL-DEFECT
- **Evidence**: `src/main/java/com/aspose/threed/FileFormat.java` registers `GLTF`/`GLTF2`/`GLTF_BINARY`/`GLTF2_BINARY` and `FBX6100ASCII`/`FBX6100_BINARY` as real, reachable formats (`registerFormat(...)`, lines ~148-156), and `FileFormat.load()`/`FileFormat.save()` (lines ~279-330) dispatch `.gltf`/`.glb` to `GltfReader`/`GltfSaver` and `.fbx` to `FbxReader`/`FbxWriter`. All four inner classes (lines ~604-618 and ~803-813) are unimplemented stubs: `GltfReader.load` and `FbxReader.load` each contain only a `// TODO: implement ... loading` comment and `return new Scene();`, and `GltfSaver.save` and `FbxWriter.save` each contain only a `// TODO: implement ... saving` comment with an otherwise empty method body. None of the four raises an exception — `GltfReader.load`/`FbxReader.load` silently return an empty `Scene`, and `GltfSaver.save`/`FbxWriter.save` silently write zero bytes.
- **Impact**: any caller doing `Scene.fromFile("model.gltf")` or `scene.save("model.fbx")` gets a normal, successful return with no error and no real data — silent data loss rather than a clear failure. This is a materially worse failure mode than the many other unimplemented members in this codebase (e.g. `DracoFormat.decode`, `Camera.moveForward`), which correctly raise `UnsupportedOperationException`.
- **Not fixable here because**: this is a missing implementation in the product's own source, not something a README edit can resolve. The new README candidate documents this explicitly in Scope and Limitations rather than presenting glTF/FBX as supported.

## TODO.md's own glTF-export completion claim is contradicted by the current source

- **Severity**: VERSION-DRIFT
- **Evidence**: `TODO.md`'s "Session 4" entry claims glTF export was fully implemented and tested ("**Created GltfExporter with full glTF 2.0 JSON structure support**", "**glTF export tested successfully with ASCII and binary formats**", "16 tests passing"), and marks the `TODO.md` checklist items "glTF: Implement exporter" as `[x]` done. The current source's `GltfSaver.save()` (see the issue above) is an empty method body with a `// TODO: implement GLTF saving` comment — the opposite of "fully implemented and tested." `TODO.md`'s later "Session 13"/"Session 14" entries independently confirm a related regression: `GltfExporter`/`GltfImporter` (along with `FbxExporter`/`FbxImporter`, `ObjExporter`/`ObjImporter`, `StlExporter`/`StlImporter`, `IExporter`, `IImporter`) are listed under "Removed Types (14 - must delete)"/"11 removed types" during an API-signature-alignment pass, consistent with a working glTF-export implementation being replaced by the current `FileFormat`-embedded stub during that refactor, without `TODO.md`'s own earlier "done" claim being corrected.
- **Impact**: a contributor or maintainer trusting `TODO.md`'s own progress log would believe glTF export already works and is tested; it does not.
- **Not fixable here because**: this is a discrepancy between the product repo's own historical changelog and its current source, not something a README edit resolves.

## FILE_FORMATS.md contradicts itself on glTF and FBX support

- **Severity**: INFORMATIONAL
- **Evidence**: `FILE_FORMATS.md`'s summary table (lines 5-11) states glTF has "Full import/export" and FBX has "Import only (binary)". The same file's own "Format Details" section repeats a contradictory glTF/FBX entry twice each: lines 32-38 say glTF "Import: Full support... Export: Full support", then lines 48-51 say glTF "Import: Not implemented... Export: Not implemented... (format not yet implemented)"; lines 39-46 say FBX "Import: Binary FBX format supported... Export: Not implemented", then lines 53-56 say FBX "Import: Not implemented... Export: Not implemented". The file appears to interleave two different states of the same two formats without reconciling them.
- **Impact**: a reader following `FILE_FORMATS.md` (which the old README explicitly points to for "the list of supported formats") gets two different, contradictory answers for the same two formats depending which part of the file they read.
- **Not fixable here because**: this is upstream documentation content in the product's own repo, not the aspose.org README under refresh. The new README candidate does not repeat this table's optimistic entries and calls out the contradiction directly (Scope and Limitations).

## OBJ export is an unimplemented stub

- **Severity**: FUNCTIONAL-DEFECT
- **Evidence**: `FileFormat.java`'s `ObjWriter.save()` (lines ~797-801) has the identical empty-body shape as `GltfSaver.save`/`FbxWriter.save` above — only a `// TODO: implement OBJ saving` comment, no real write logic. Reachable the same way as glTF/FBX above — `scene.save("x.obj")` returns successfully having written nothing.
- **Impact**: same silent-data-loss shape as the glTF/FBX issue, for OBJ export specifically. OBJ import (`ObjReader`) is a genuine, working implementation in the GitHub source — but see the next entry: the currently published Maven Central package does not contain this implementation.
- **Not fixable here because**: missing implementation in product source; the new README candidate does not present OBJ export as functional.

## OBJ import works in the GitHub source but the published Maven Central artifact still ships an older, stub version (shipped-vs-source drift)

- **Severity**: FUNCTIONAL-DEFECT
- **Evidence**: independently downloaded and decompiled the real, currently-published artifact (`https://repo1.maven.org/maven2/org/aspose/aspose-3d-foss/26.5.0/aspose-3d-foss-26.5.0.jar`, SHA1 `efa37b32a68de663baa784b6dc29d5f4e412b08a`, `Last-Modified: 2026-07-16`). `javap -p -c` on `com/aspose/threed/FileFormat$ObjLoader.class` from that jar shows its `load(...)` method body is exactly `new Scene(); return scene;` — a bare stub, and structurally/name-wise a different, older implementation than the current GitHub source's `FileFormat$ObjReader` (which contains a full OBJ vertex/face parser, confirmed directly in `src/main/java/com/aspose/threed/FileFormat.java`, lines ~513-580, and independently corroborated by `knowledge/3d/java/merged/formats.md`'s source-derived "OBJ | Yes | -" row). By contrast, `javap -p -c` on the same jar's `FileFormat$StlLoader.class` and `FileFormat$StlSaver.class` shows real, substantial parsing/writing logic, matching the current GitHub source for STL. The published jar's inner-class names themselves (`ObjLoader`/`ObjSaver`/`StlLoader`/`StlSaver`/`GltfLoader`/`GltfSaver`/`FbxLoader`/`FbxSaver`) differ from the current source's naming (`ObjReader`/`ObjWriter`/`StlReader`/`StlWriter`/`GltfReader`/`GltfSaver`/`FbxReader`/`FbxWriter`), independently confirming the published artifact was built from an earlier, structurally different commit than the pinned clone-cache HEAD (`35963f673e0811285d6b1ad0911fd7171bf70f41`).
- **Impact**: a user who installs the library the way this README's own Installation section instructs (the Maven Central dependency) gets the stub `ObjLoader` — `Scene.fromFile("model.obj")` silently returns an empty `Scene`, not the real parsed geometry that exists in the GitHub source. Only building the library from the GitHub source directly (not the published dependency) gets the working OBJ import.
- **Not fixable here because**: this is a release/publishing gap in the product's own repo (an unpublished fix), not something a README edit can resolve. The new README candidate does not present OBJ import as a working capability of the published package, and calls out this specific shipped-vs-source drift in Scope and Limitations.

## Old README's stated minimum Java version (8+) contradicts the project's actual compiler target (21)

- **Severity**: VERSION-DRIFT
- **Evidence**: the old README states "It requires **Java 8** or later." `pom.xml` sets `<maven.compiler.source>21</maven.compiler.source>` and `<maven.compiler.target>21</maven.compiler.target>`. A jar built from this `pom.xml` targets Java 21 bytecode and cannot load on a Java 8-20 runtime (`UnsupportedClassVersionError`). `content/products.aspose.org/en/3d/java/_index.md` (this repo's own products page, generated more recently) already correctly states "Aspose.3D FOSS requires Java 21 or later."
- **Impact**: a developer following the old README's own stated minimum version on a pre-21 JVM would hit a runtime class-version error the README gives them no reason to expect.
- **Not fixable here because**: this is a stale claim in the product's own README, not the aspose.org candidate. The new candidate states "Requires Java 21 or later," matching `pom.xml` and the already-correct products.aspose.org copy.

## Several primitive shapes implement `toMesh()` but always throw

- **Severity**: FUNCTIONAL-DEFECT
- **Evidence**: `Pyramid.toMesh()`, `Torus.toMesh()`, `RectangularTorus.toMesh()`, `RevolvedAreaSolid.toMesh()`, and `LinearExtrusion.toMesh()` (each confirmed directly in its own source file) are all `throw new UnsupportedOperationException();` with no real body, despite each class declaring the method (satisfying `IMeshConvertible`) and being a real, constructible, publicly documented type. `Box.toMesh()`, `Cylinder.toMesh()`, `Sphere.toMesh()`, and `Dish.toMesh()`, by contrast, are real, working implementations that build actual mesh geometry.
- **Impact**: constructing a `Pyramid`/`Torus`/`RectangularTorus`/`RevolvedAreaSolid`/`LinearExtrusion` and calling the one method needed to actually use it as geometry throws at runtime — undisclosed anywhere upstream.
- **Not fixable here because**: missing implementation in product source. The new README candidate lists exactly which primitives work and which don't in Scope and Limitations.

## `NurbsCurve` curve evaluation is unimplemented

- **Severity**: FUNCTIONAL-DEFECT
- **Evidence**: `NurbsCurve.evaluate(int steps)`, `NurbsCurve.evaluate()`, and `NurbsCurve.evaluateAt(double u)` are each `throw new UnsupportedOperationException();`. The class's data model (control points, knot vectors, degree, order, rational flag, curve type) is real and fully functional — only point sampling along the curve is missing.
- **Impact**: a caller can build a `NurbsCurve`'s data but cannot sample points along it, the operation most consumers would actually want.
- **Not fixable here because**: missing implementation in product source; documented in Scope and Limitations instead.

## `PbrSpecularMaterial` is entirely unimplemented

- **Severity**: FUNCTIONAL-DEFECT
- **Evidence**: every accessor on `PbrSpecularMaterial` (`getTransparency`/`setTransparency`, `getNormalTexture`/`setNormalTexture`, `getSpecularGlossinessTexture`/`setSpecularGlossinessTexture`, `getGlossinessFactor`/`setGlossinessFactor`, `getSpecular`/`setSpecular`, `getDiffuseTexture`/`setDiffuseTexture`, `getDiffuse`/`setDiffuse`, `getEmissiveTexture`/`setEmissiveTexture`, `getEmissiveColor`/`setEmissiveColor` — 9 property pairs, 18 methods total) is `throw new UnsupportedOperationException();`. `PbrMaterial` (a separate class) is fully functional.
- **Impact**: the class is constructible but unusable for anything beyond its constructor; not disclosed anywhere upstream.
- **Not fixable here because**: missing implementation in product source; the new README candidate recommends `PbrMaterial` instead and does not list `PbrSpecularMaterial` as a working capability.

No BLOCKING-severity issues were found — nothing in the standard install/build path
(`mvn clean package`, `mvn test`, the Maven Central dependency coordinates) is broken or
undisclosed as broken.
