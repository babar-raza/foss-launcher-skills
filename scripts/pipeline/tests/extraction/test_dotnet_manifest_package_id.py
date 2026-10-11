"""HARDEN-dotnet-test-csproj (2026-09-11): _parse_dotnet_manifest must find
the real package's <PackageId>, not a same-depth test project's csproj.

Found live bootstrapping imaging/net's package registry entry: the real
repo has src/Aspose.Imaging.Foss/Aspose.Imaging.Foss.csproj (PackageId =
"Aspose.Imaging.Foss") and tests/Aspose.Imaging.Foss.Tests/
Aspose.Imaging.Foss.Tests.csproj (IsPackable=false, no PackageId) -- both
exactly 6 path parts deep. pathlib.Path.rglob()'s file order is filesystem-
dependent, not deterministic; on this run it returned the test project's
csproj first, and the original depth-only sort picked it, silently
returning an EMPTY manifest name (not an error) even though the real
PackageId was sitting in a sibling file one directory over. Every downstream
caller (registry_backfill.py) then fell back to a naming-convention GUESS
("Aspose.Imaging.FOSS", wrong case) instead of the real, confirmed identity
("Aspose.Imaging.Foss").

reports/skill-gaps/2026-09-11-imaging-net-pipeline-hardening-prerequisites.md
"""
from __future__ import annotations

from pathlib import Path

from extraction.package_manifest import _parse_dotnet_manifest


def _write_real_package_csproj(repo: Path, *, package_id: str = "Aspose.Imaging.Foss") -> None:
    proj_dir = repo / "src" / "Aspose.Imaging.Foss"
    proj_dir.mkdir(parents=True, exist_ok=True)
    (proj_dir / "Aspose.Imaging.Foss.csproj").write_text(
        f"""<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFrameworks>netstandard2.0;net8.0</TargetFrameworks>
    <AssemblyName>Aspose.Imaging.Foss</AssemblyName>
  </PropertyGroup>
  <PropertyGroup>
    <PackageId>{package_id}</PackageId>
  </PropertyGroup>
</Project>
""",
        encoding="utf-8",
    )


def _write_test_project_csproj(repo: Path) -> None:
    proj_dir = repo / "tests" / "Aspose.Imaging.Foss.Tests"
    proj_dir.mkdir(parents=True, exist_ok=True)
    (proj_dir / "Aspose.Imaging.Foss.Tests.csproj").write_text(
        """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <IsPackable>false</IsPackable>
  </PropertyGroup>
  <ItemGroup>
    <ProjectReference Include="..\\..\\src\\Aspose.Imaging.Foss\\Aspose.Imaging.Foss.csproj" />
  </ItemGroup>
</Project>
""",
        encoding="utf-8",
    )


class TestDotnetManifestPrefersRealPackageOverTestProject:
    def test_finds_package_id_when_test_project_sits_at_same_depth(self, tmp_path):
        """Both csproj files are exactly the same path depth (the real
        incident's shape) -- the real PackageId must be found regardless
        of which file the filesystem happens to enumerate first."""
        _write_real_package_csproj(tmp_path)
        _write_test_project_csproj(tmp_path)
        info = _parse_dotnet_manifest(tmp_path)
        assert info.get("name") == "Aspose.Imaging.Foss"

    def test_also_recovers_real_multi_target_frameworks(self, tmp_path):
        """Regression for the same root cause's second effect: reading the
        wrong (test) csproj also silently lost the real package's full
        multi-target framework list (netstandard2.0;net8.0), since a test
        project typically targets only the one framework it runs under."""
        _write_real_package_csproj(tmp_path)
        _write_test_project_csproj(tmp_path)
        info = _parse_dotnet_manifest(tmp_path)
        assert info.get("target_frameworks") == ["netstandard2.0", "net8.0"]

    def test_no_package_id_anywhere_falls_back_to_non_test_csproj(self, tmp_path):
        """When NEITHER csproj has a PackageId (a valid, if less common,
        real-world shape), still prefer the non-test-named project for the
        AssemblyName/TargetFrameworks fallback rather than an arbitrary
        same-depth tie."""
        proj_dir = tmp_path / "src" / "Example"
        proj_dir.mkdir(parents=True)
        (proj_dir / "Example.csproj").write_text(
            "<Project Sdk=\"Microsoft.NET.Sdk\">\n"
            "  <PropertyGroup>\n"
            "    <TargetFramework>net8.0</TargetFramework>\n"
            "    <AssemblyName>Example.Real</AssemblyName>\n"
            "  </PropertyGroup>\n"
            "</Project>\n",
            encoding="utf-8",
        )
        _write_test_project_csproj(tmp_path)
        info = _parse_dotnet_manifest(tmp_path)
        assert info.get("name") == "Example.Real"

    def test_this_repos_real_3d_net_clone_extracts_the_library_not_the_cli_tool(self):
        repo = Path(__file__).resolve().parents[4] / "runs" / ".clone_cache" / "aspose_3d_net"
        if not repo.is_dir():
            import pytest
            pytest.skip("3d/net clone cache not present on this machine")
        assert _parse_dotnet_manifest(repo).get("name") == "Aspose.3D.FOSS"

    def test_this_repos_real_imaging_net_clone_extracts_correctly(self):
        """The real regression proof, against the actual cloned repo (skipped
        if the clone cache isn't present on this machine)."""
        repo = Path(__file__).resolve().parents[4] / "runs" / ".clone_cache" / "aspose_imaging_net"
        if not repo.is_dir():
            import pytest
            pytest.skip("imaging/net clone cache not present on this machine")
        info = _parse_dotnet_manifest(repo)
        assert info.get("name") == "Aspose.Imaging.Foss"
        assert "netstandard2.0" in info.get("target_frameworks", [])
        assert "net8.0" in info.get("target_frameworks", [])


def _write_csproj(repo: Path, rel_dir: str, name: str, body: str) -> None:
    d = repo / rel_dir
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.csproj").write_text(f'<Project Sdk="Microsoft.NET.Sdk">\n  <PropertyGroup>\n{body}\n  </PropertyGroup>\n</Project>\n', encoding="utf-8")


_LIBRARY = "    <AssemblyName>Aspose.3D.FOSS</AssemblyName>\n    <PackageId>Aspose.3D.FOSS</PackageId>\n    <Version>26.1.0</Version>"
_CLI_TOOL = ("    <OutputType>Exe</OutputType>\n    <AssemblyName>aspose-3d-converter</AssemblyName>\n"
             "    <PackageId>Aspose.3D.Converter</PackageId>\n    <Version>1.0.0</Version>")


class TestDotnetManifestPrefersLibraryOverExecutable:
    """3d/net regression (2026-09-18): the repo has two projects that declare a
    <PackageId> -- the CLI `src/converter/Converter.csproj` (OutputType=Exe,
    depth 3) and the real library `src/main/Aspose.ThreeD/Aspose.ThreeD.csproj`
    (Aspose.3D.FOSS, depth 4). The shallowest-PackageId rule picked the tool, so
    the knowledge model, and through it the published docs, taught readers to
    install `Aspose.3D.Converter`, a package that does not exist on NuGet."""

    def test_library_wins_over_a_shallower_executable_with_a_package_id(self, tmp_path):
        _write_csproj(tmp_path, "src/converter", "Converter", _CLI_TOOL)
        _write_csproj(tmp_path, "src/main/Aspose.ThreeD", "Aspose.ThreeD", _LIBRARY)
        info = _parse_dotnet_manifest(tmp_path)
        assert info["name"] == "Aspose.3D.FOSS"
        assert info["version"] == "26.1.0"

    def test_winexe_and_pack_as_tool_are_also_not_the_library(self, tmp_path):
        _write_csproj(tmp_path, "src/a", "Tool", "    <OutputType>WinExe</OutputType>\n    <PackageId>Some.Gui</PackageId>")
        _write_csproj(tmp_path, "src/b", "Cli", "    <PackAsTool>true</PackAsTool>\n    <PackageId>Some.Cli</PackageId>")
        _write_csproj(tmp_path, "src/deep/er/x", "Lib", "    <PackageId>Some.Library</PackageId>")
        assert _parse_dotnet_manifest(tmp_path)["name"] == "Some.Library"

    def test_an_executable_is_still_used_when_it_is_the_only_package(self, tmp_path):
        """No library anywhere: returning the tool's PackageId is no worse than
        the old behaviour, and better than an empty manifest."""
        _write_csproj(tmp_path, "src/converter", "Converter", _CLI_TOOL)
        assert _parse_dotnet_manifest(tmp_path)["name"] == "Aspose.3D.Converter"

    def test_result_does_not_depend_on_filesystem_enumeration_order(self, tmp_path):
        """Same repo built in two creation orders must extract identically
        (rglob order is filesystem-dependent; ties must break on sorted path)."""
        a, b = tmp_path / "a", tmp_path / "b"
        for repo, order in ((a, ("lib1", "lib2")), (b, ("lib2", "lib1"))):
            for n in order:
                _write_csproj(repo, f"src/{n}", n, f"    <PackageId>Pkg.{n}</PackageId>")
        assert _parse_dotnet_manifest(a)["name"] == _parse_dotnet_manifest(b)["name"]

    def test_real_package_beyond_the_first_twenty_enumerated_projects_is_still_found(self, tmp_path):
        """The old code capped rglob() at 20 BEFORE sorting, so in a repo with
        more than 20 csproj files the real package could be dropped by
        enumeration order alone. Latent (largest repo today has 16); pinned so it
        cannot become a silent identity loss when a repo grows."""
        # Which 20 an unsorted rglob() yields first depends on the platform's
        # traversal order (Python 3.13 on NTFS visited the LAST directory first,
        # so a single 'zzz' position passed against the old code by luck). Place
        # the real project at BOTH ends of the alphabet: under a cap-before-sort
        # at least one of the two placements loses it, whatever the order is.
        for label, real_dir in (("front", "aaa/first/dir/x"), ("back", "zzz/last/dir/x")):
            repo = tmp_path / label
            for i in range(30):
                _write_csproj(repo, f"tests/T{i:02d}", f"T{i:02d}.Tests", "    <IsPackable>false</IsPackable>")
            _write_csproj(repo, real_dir, "Real", "    <PackageId>Real.Package</PackageId>")
            assert _parse_dotnet_manifest(repo)["name"] == "Real.Package", label
