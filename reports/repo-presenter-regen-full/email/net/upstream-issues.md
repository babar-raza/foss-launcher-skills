# Upstream issues — Aspose.Email FOSS for .NET

Verified against `runs/.clone_cache/aspose_email_net/` (pinned repo_sha
`a8999e259143a9ffc660086b34a7f39516da29f5`).

## Stale `csharp/` directory prefix in build and example instructions

- **Severity**: FUNCTIONAL-DEFECT (documentation-only; does not affect the published NuGet package or the library itself)
- **Evidence**: the real repository root contains no csharp directory anywhere — confirmed by a direct listing of the clone cache root (changelog, build-props, license, public-API doc, root README, plus the examples/src/tests directories). Despite this, the upstream root README's Build And Test section instructs `dotnet build csharp/src/Aspose.Email.Foss/Aspose.Email.Foss.csproj -c Release`, and its Examples section says examples live under `csharp/examples/`. The same stale prefix recurs three more times, independently, in the examples directory's own README, in its Run instructions for each of its three example programs.
- **Impact**: every documented build/pack/run command in both files fails as written from a fresh clone (MSBuild reports the project file does not exist). Low severity in practice — it only affects a contributor following the docs literally to build from source; end users installing the published NuGet package are unaffected.
- **Not fixable here because**: this is upstream documentation content in the product's own repository, not something a README refresh for aspose.org can change at the source. The candidate README's own Development and Testing section uses the real, verified paths throughout (no stale prefix).

No other upstream defects were found during this verification pass — the library's main project
has zero external `PackageReference` entries (genuinely dependency-free), and every method and
property claim carried over from the old README was independently confirmed against the real C#
source.
