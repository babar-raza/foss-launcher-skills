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
