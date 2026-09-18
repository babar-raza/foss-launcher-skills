# 3d/net PLY executable proof (G-52 / TC-RDR-03-3D-NET)

Independent, executable reverification of backlog G-52's claim: `3d/net`'s candidate README
stated PLY encode AND decode both throw `NotImplementedException` in the FOSS build. This is
false for the real, public, documented API — confirmed by building and running real code against
the pinned clone, not by source inspection alone.

## Pinned state

- Product: `aspose-3d-foss/Aspose.3D-FOSS-for-.NET`
- Clone cache commit: `70933ab13eb0e313d9b160c55845011d366b1599` (2026-08-14 14:53:01 +0500)
- `dotnet --version`: 10.0.204
- Command: `dotnet run -c Debug` from this directory (references the already-built
  `Aspose.3D.FOSS.dll` at
  `runs/.clone_cache/aspose_3d_net/src/main/Aspose.ThreeD/bin/Debug/net10.0/`)
- Run date: 2026-08-19. Full output: `run_output_20260819.txt` (exit 0, all assertions passed).

## Verdict

- **PLY export**: WORKS via the public `Scene.Save("file.ply")` API. Verified: produces a
  non-empty, correctly-headed PLY file for a real `Mesh` (Box primitive converted via
  `.ToMesh()` — PlyWriter only walks literal `Mesh` entities, unlike every sibling writer, which
  is a separate, narrower, real discovery — see below).
- **PLY import**: WORKS via the public `Scene.Open("file.ply")` API. Verified two ways: (1)
  round-tripping the file just exported (8 control points / 6 polygons preserved), (2) loading
  an independently hand-authored ASCII PLY fixture never produced by this library (3 vertices /
  1 polygon preserved).
- **Root of the false claim**: `FileFormat.PLY` is a *public* static field of type
  `Formats.PlyFormat` (a different class from the internal dispatch singleton `FileFormat.
  PlyFormat` used by `IOService`, despite the confusingly identical name). `Formats.PlyFormat`'s
  own `Encode`/`Decode` methods throw `NotImplementedException` unconditionally, and passing
  `FileFormat.PLY` directly into `Scene.Save(stream, format)` also throws (a different message,
  "Save options not implemented for ply") — but neither of these is the path `Scene.Open`/
  `Scene.Save` actually use for filename/extension-based PLY I/O, which is `PlyReader`/
  `PlyWriter`, registered separately in `IOService.CreateImporter`/`CreateExporter`.
- **Secondary, real discovery (not part of G-52's own scope, folded into the candidate's Scope
  and Limitations as a narrower true note is NOT currently included — flagged here for the
  record)**: `PlyWriter.Export` only walks literal `Mesh` entities (`entity is Mesh`) with no
  `IMeshConvertible`/`.ToMesh()` fallback, unlike `ObjWriter`/`StlWriter`/`GltfWriter`/
  `FbxWriter`/`Microsoft3MFWriter`/`Discreet3DSWriter`/`ColladaWriter`, which all do. A scene
  containing only a raw, unconverted `Primitive` (`Box`, `Sphere`, etc.) exports as a
  *successful but silently empty* (0 vertex / 0 face) PLY file — no exception. Confirmed via
  TEST 3b in `Program.cs`. Not a blocking defect for the corrected README claim (PLY import/
  export both genuinely work for real `Mesh` content, which is how every other supported format
  behaves too once a primitive is undergone the same explicit-or-implicit `.ToMesh()` step), but
  worth a maintainer's attention upstream.
- **PDF and Draco**: independently re-verified genuinely unsupported — no `PdfReader`/
  `PdfWriter`/`DracoReader`/`DracoWriter` class exists anywhere in the codebase, and neither is
  registered in `IOService`. The candidate's claim for these two formats is accurate and was not
  changed.
- **Portfolio search** (other 3D-family platforms, source-level, no build needed since none of
  them claim PLY works): `3d/python` has `PlyFormat`/`PlyLoadOptions`/`PlySaveOptions` as pure
  option/data classes with no reader/writer and no `PlyPlugin` in its `_register_plugins()` list
  — its own candidate's "PLY unsupported" claim is TRUE, independently confirmed, not changed.
  `3d/java` has only `PlyLoadOptions.java`/`PlySaveOptions.java`, no format/reader/writer classes
  at all. `3d/typescript` has no PLY-related files whatsoever. Neither candidate makes a PLY
  claim currently (silence is accurate, not a defect). The dispatcher-vs-format-internals mistake
  that produced the false `3d/net` claim does not reappear anywhere else in this portfolio.

## Files

- `Program.cs` / `ply_proof.csproj` — the executable proof program (5 test sections: real export,
  real reload, independent fixture import, decoy-class failure mode, decoy-object-into-Save
  failure mode, plus a discovery test for raw-Primitive export).
- `run_output_20260819.txt` — full captured stdout of the run this verdict is based on.
