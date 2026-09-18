# TC-MT070-01: Build-based independent verification

**Method**: this repo's extraction pipeline (`scripts/pipeline/extraction/api_surface.py`)
is 100% static tree-sitter AST parsing — it never invokes `dotnet build`, Roslyn, or
reflection. That was the one genuine evidence gap left after MT068's otherwise-exhaustive
source-level investigation (`reports/skill-gaps/2026-09-11-imaging-net-pipeline-hardening-prerequisites.md`,
"§7d class_count=3 investigation"). This taskcard closes it with a real compiled-assembly
check, independent of the pipeline's own extraction code.

**Steps performed** (session 503e95f0, 2026-09-16):

1. Copied `runs/.clone_cache/aspose_imaging_net/` (read-only per AGENTS.md §11) to an
   isolated temp directory (`mktemp -d`, never written back). Verified pinned HEAD
   `f2cf68fd64545bfb704c45ee756af3125103fd74` unchanged, working tree clean, 21 `.cs`
   files (17 under `src/`, 4 test files under `tests/`) — matches
   `knowledge/imaging/net/scout/scout_report.json`'s `files_attempted: 17`.
2. `dotnet build Aspose.Imaging.Foss.sln -c Release` (dotnet SDK 10.0.204, `.csproj`
   targets `netstandard2.0;net8.0`, `GenerateDocumentationFile: true`, no conditional
   compilation symbols defined) — **Build succeeded, 0 errors, 52 warnings** (all
   `CS1591` "missing XML doc comment for publicly visible member", one per
   target-framework-doubled public member — itself a free compiler-verified enumeration
   of every publicly-visible member, corroborating the reflection dump below
   independently a third way).
3. Built a throwaway reflection-dump console app (`ApiDump`, net8.0,
   `System.Reflection` + `Assembly.LoadFrom` + `GetExportedTypes()`) against the built
   `Aspose.Imaging.Foss.dll` (net8.0 target). `GetExportedTypes()` returns only
   publicly-visible types — i.e. this is the CLR's own authoritative answer to "what is
   this assembly's public surface", independent of source-level `internal` keyword
   parsing. Full output: `reflection_api_dump.json` (this directory).

**Result — exact match, zero discrepancy** between the compiled assembly's exported
surface and the tracked `knowledge/imaging/net/merged/api_surface.json`:

| Type | Reflection (compiled DLL) | api_surface.json (tree-sitter) | Match |
|---|---|---|---|
| `ImageFormat` (enum) | 12 members: Bmp, Dicom, Emf, Gif, Ico, Jpeg, Png, Psd, Tiff, Unknown, WebP, Wmf | same 12, same names | Exact |
| `ImageInfo` (class) | 1 ctor + 5 properties (BitDepth, Format, FrameCount, Height, Width) | methods:[ImageInfo], properties: same 5 | Exact |
| `ImageProbe` (static class) | 5 methods: DetectFormat(Stream), DetectFormat(byte[]), Probe(Stream), Probe(byte[]), ProbeFile(string) | methods: DetectFormat×2, Probe×2, ProbeFile | Exact |
| Any other public type | **none** (`GetExportedTypes()` returns exactly these 3) | 3 entries total | Exact |

No `TargetFrameworks` divergence: both `netstandard2.0` and `net8.0` builds produced
identical warning sets (same 26 CS1591 lines per framework), so no conditional-compilation
or multi-targeting surface difference exists that static parsing could have missed.
`InternalsVisibleTo` was checked — absent from the `.csproj` and all source files, so no
"internal" type is exposed to any friend assembly either.

**Conclusion**: `class_count=3` is independently reconfirmed by a completely different
verification path (compiled CLR metadata, not source-text parsing) than MT068's own
three checks. This closes Phase 4's "compiled assembly metadata or reflection" evidence
requirement with a real, non-fabricated result — not a re-assertion of the same static
analysis. No pipeline defect, no missing entity, no system fix required from this
taskcard.

**Artifacts**: `reflection_api_dump.json` (this directory), this file. Build performed in
an isolated `mktemp -d` temp copy per AGENTS.md's clone-cache read-only rule; temp
directory discarded, nothing written back to `runs/.clone_cache/`.
