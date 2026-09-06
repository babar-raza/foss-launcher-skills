# Upstream issues — Aspose.3D FOSS for .NET

Verified: 2026-08-13 against https://github.com/aspose-3d-foss/Aspose.3D-FOSS-for-.NET.git @ repo_sha 6a209e8fc3dfc305df39a417037e32a4d4c7b2be (pinned clone-cache HEAD)

## Format-registry capability flags contradict actual (unimplemented) encode/decode/extract behavior for Draco, PLY, and PDF

- **Severity**: INFORMATIONAL
- **Evidence**: `src/main/Aspose.ThreeD/Aspose/ThreeD/FileFormat.cs` registers `Formats.DracoFormat` and
  `Formats.PlyFormat` as `public static readonly` format entries, and `DracoFormat`/`PlyFormat`'s own
  base constructor calls declare `canExport=true, canImport=true`
  (`src/main/Aspose.ThreeD/Aspose/ThreeD/Formats/DracoFormat.cs:12-21`,
  `src/main/Aspose.ThreeD/Aspose/ThreeD/Formats/PlyFormat.cs:12-21`). In practice every one of
  `DracoFormat`'s `Encode`/`Decode` overloads and every one of `PlyFormat`'s `Encode`/`Decode`
  overloads unconditionally `throw new NotImplementedException(...)`
  (`DracoFormat.cs:27-56`, `PlyFormat.cs:24-83`) — there is no working code path for either format
  at all. Similarly, `PdfFormat`'s constructor declares `canImport=true`
  (`src/main/Aspose.ThreeD/Aspose/ThreeD/Formats/PdfFormat.cs:12-20`), but the class's only methods
  (`Extract`, `ExtractScene`) all `throw new NotImplementedException(...)`
  (`PdfFormat.cs:22-40`) — there is no working PDF import path either, despite the registered flag.
- **Impact**: A caller who introspects `FileFormat.Draco`/`FileFormat.PLY`/`FileFormat.PDF`'s own
  declared import/export capability (rather than reading the class's XML doc comments or trying the
  call and catching the exception) would reasonably conclude these formats are usable — they are not,
  in this FOSS build. This is a metadata/implementation mismatch inside the library itself, not a
  documentation gap the project's own README already discloses correctly at the prose level.
- **Not fixable here because**: This is a source-level inconsistency between the format registry's
  own declared capability flags and the actual method bodies in the shipped library — no README edit
  in this repository can change what the compiled/shipped library reports about itself at runtime.

## `Watermark.EncodeWatermark`/`DecodeWatermark` are entirely unimplemented despite being a named,
   documented public class

- **Severity**: FUNCTIONAL-DEFECT
- **Evidence**: `src/main/Aspose.ThreeD/Aspose/ThreeD/Watermark.cs` declares a public `Watermark`
  utility class with real, documented `EncodeWatermark`/`DecodeWatermark` overloads (XML doc
  comments describe embedding and extracting a text watermark in a 3D scene, with an optional
  password-protection overload). Every overload of both methods unconditionally
  `throw new NotImplementedException(...)` — there is no working code path for text watermarking
  anywhere in this class.
- **Impact**: a caller who finds `Watermark` in the public API surface (it is a real, exported,
  documented class, not an internal/experimental one) and calls either method gets an immediate,
  unconditional exception on every invocation — the class currently has no functional use.
- **Not fixable here because**: this is a missing implementation in the product's own source, not
  something a README edit can resolve. The new README candidate documents this explicitly in Scope
  and Limitations rather than presenting text watermarking as a working capability (it does not
  list `Watermark` as a Key Capability, and the API Reference table entry for `Watermark` carries no
  functional claim beyond naming the class).

No other upstream issues identified during verification.
