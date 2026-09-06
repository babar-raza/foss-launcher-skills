# Upstream issues — Aspose.Words FOSS for .NET

Verified: 2026-08-13 against https://github.com/aspose-words-foss/Aspose.Words-FOSS-for-.NET
(clone cache SHA e38a872082c39c58ff819487a0d9ebec28f25e22; NuGet findings below re-verified live
against api.nuget.org and api.nuget.org's registration endpoint for `Aspose.Words.FOSS`)

## Repo is unbuildable from a clean clone -- missing NuGet package dependency
- **Severity**: BLOCKING (for contributors building from source only -- see note below)
- **Evidence**: `Aspose.Words/Aspose.Words.csproj` and `Aspose.Foundation/Aspose.Foundation/Aspose.Foundation.csproj` both carry an unconditional `PackageReference Include="Aspose.EnumExtensionsGenerator" Version="1.0.2"` (a Roslyn source-generator package, confirmed via direct read of both project files). A live check of `https://api.nuget.org/v3-flatcontainer/aspose.enumextensionsgenerator/index.json` returns a real HTTP 404 -- this package has never been published to nuget.org, so `dotnet build Aspose.Words.sln -c Release` on a genuinely fresh clone fails at restore with `NU1101`.
- **Impact**: a contributor building from source to run the test suite hits this immediately. **Does not affect end users** -- `Aspose.Words.FOSS` itself is genuinely published on nuget.org (v26.2.0, live-verified), so this candidate's Installation section uses `dotnet add package` rather than a from-source build, sidestepping this defect entirely for consumers. A real, working fallback exists for contributors who do need to build from source: both project files set `<CompilerGeneratedFilesOutputPath>Generated</CompilerGeneratedFilesOutputPath>`, and the generator's own prior output is already checked into the repository (confirmed real files under `Aspose.Words/Generated/Aspose.EnumExtensionsGenerator/` and `Aspose.Foundation/Aspose.Foundation/Generated/Aspose.EnumExtensionsGenerator/`) -- removing the failing `PackageReference` block from both `.csproj` files lets the build proceed against that already-generated, checked-in source instead.
- **Not fixable here because**: the missing dependency reference and its unresolvable NuGet publication state live entirely in the upstream repository's own project files, not in this candidate's README.

## Repo's own README and AGENTS.md still say the NuGet package is "coming very soon"
- **Severity**: INFORMATIONAL
- **Evidence**: the real, current root `README.md` says "A NuGet package is coming very soon. Until then, build from source" and `AGENTS.md` says "NuGet (coming very soon): `dotnet add package <package id will be announced in the README>`". A live check of `https://api.nuget.org/v3-flatcontainer/aspose.words.foss/index.json` returns a real, published version (`26.2.0`), and the live registration endpoint confirms package id `Aspose.Words.FOSS`, author `Aspose`, MIT license.
- **Impact**: a reader or an AI coding agent following either file's literal guidance would build from source and never discover the already-published NuGet package, or would not know the real package id to install.
- **Not fixable here because**: this is the upstream repository's own root `README.md`/`AGENTS.md` content, not something a `reports/repo-presenter-regen-full` candidate can change; this candidate itself uses the real, live-verified `dotnet add package Aspose.Words.FOSS` command rather than repeating the stale "coming very soon" framing.

## data/package_registry.json's `published: false` flag is stale for this product
- **Severity**: INFORMATIONAL
- **Evidence**: this repo's own `data/package_registry.json` records `words.net.verification.published: false` with `evidence_note` explaining the flag is a naming-convention guess, not a live check. A live check of the real NuGet flatcontainer and registration endpoints for `aspose.words.foss` confirms the package genuinely is published (version `26.2.0`, author `Aspose`, MIT license, multi-targeting `.NET Framework 4.6.2`, `.NET Standard 2.0`, and `.NET 8.0`).
- **Impact**: any downstream tooling that trusts `data/package_registry.json`'s `published` flag at face value (rather than live-checking) would incorrectly treat this product as unpublished and could recommend "build from source" fallback text instead of the real install command.
- **Not fixable here because**: `data/package_registry.json` is out of this candidate's write scope (this session's boundaries explicitly exclude `data/`); this finding is recorded here as a real, disclosed, live-verified discrepancy for the registry's own maintainers to reconcile, and this candidate itself uses the live-verified package id/command rather than the stale registry value.

## Published NuGet package's real dependency graph is not obviously "no native dependencies"
- **Severity**: INFORMATIONAL
- **Evidence**: the repo's own `README.md`/`AGENTS.md` describe the library as having "No native dependencies, no Office automation" (true of the C# source itself: no P/Invoke or COM interop in `Aspose.Words/`). The live NuGet registration for the published `Aspose.Words.FOSS` 26.2.0 package lists `SkiaSharp`, `BitMiracle.LibTiff.NET`, and `Microsoft.Win32.Registry` as real package dependencies; `SkiaSharp` is a managed wrapper that bundles native, per-runtime Skia binaries.
- **Impact**: a consumer who reads "no native dependencies" as a claim about the installed package's full dependency graph (rather than about the library's own source) could be surprised by SkiaSharp's native runtime assets landing in their build/publish output.
- **Not fixable here because**: this is a fact about the real, live-published package's dependency graph, not something a README edit to this repository changes; this candidate's own Installation section lists the real dependencies factually rather than repeating the "no native dependencies" framing.

## Quick Start / Additional Examples code was not compiled in this environment
- **Severity**: INFORMATIONAL
- **Evidence**: this verification pass had no .NET SDK / MSBuild toolchain invocation available to compile-check the C# snippets in this candidate against the real `Aspose.Words.dll` surface.
- **Impact**: none identified from static review — every class, method, and property referenced in the Quick Start, Additional Examples, and Detailed Member Reference sections was cross-checked against `knowledge/words/net/merged/api_surface.md` and/or the real `runs/.clone_cache/aspose_words_net/AGENTS.md` recipes and confirmed to exist with matching signatures, and the chart-inspection example's real API usage pattern (`chart.Series[0]`, `series.DataLabels.ShowValue`, `ChartDataLabel.Position`) is adapted directly from real scouted test snippets in `knowledge/words/net/merged/snippets/`.
- **Not fixable here because**: TOOLCHAIN-UNAVAILABLE in this verification environment; matches this skill's own documented default verification-runner scope (real per-language compile wiring is separate, follow-on work).
