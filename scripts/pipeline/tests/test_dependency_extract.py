"""Ground-truth pytest suite for scripts/pipeline/commands/foss/dependency_extract.py.

Thirty-First incident / MT041 (2026-08-14). Every fixture is a real, synthetic-but-real
manifest file written to a temp directory and parsed by the real extractor functions -- never
mocked, matching this project's own established discipline for scenarios that can't use the
actual gitignored clone caches in committed tests.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "commands" / "foss"))

import dependency_extract as de  # noqa: E402


# ---------------------------------------------------------------------------------------------
# Rust
# ---------------------------------------------------------------------------------------------


def test_cargo_real_cells_rust_shape(tmp_path):
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "aspose-cells-foss-rust"\nversion = "26.7.0"\n\n'
        "[dependencies]\n"
        'chrono = "0.4"\nzip = "0.6"\nsha2 = "0.10"\nbase64 = "0.22"\n'
        'serde_json = "1"\nroxmltree = "0.20"\ngetrandom = "0.3"\n',
        encoding="utf-8",
    )
    snap = de.extract_dependencies("cells", "rust", tmp_path)
    names = {e["name"] for e in snap["required"]}
    assert names == {"chrono", "zip", "sha2", "base64", "serde_json", "roxmltree", "getrandom"}
    assert snap["development"] == []
    assert snap["parse_errors"] == []


def test_cargo_dev_dependencies_excluded_from_required():
    pass  # covered by the populated-dev-deps test below; kept as a named marker for clarity


def test_cargo_populated_dev_dependencies_never_leak_into_required(tmp_path):
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "x"\nversion = "1.0"\n\n'
        '[dependencies]\nserde = "1"\n\n[dev-dependencies]\ncriterion = "0.5"\n',
        encoding="utf-8",
    )
    snap = de.extract_dependencies("t", "rust", tmp_path)
    required_names = {e["name"] for e in snap["required"]}
    dev_names = {e["name"] for e in snap["development"]}
    assert required_names == {"serde"}
    assert dev_names == {"criterion"}
    assert "criterion" not in required_names


def test_cargo_optional_dependency_with_feature(tmp_path):
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "x"\nversion = "1.0"\n\n'
        "[dependencies]\n"
        'rayon = { version = "1", optional = true }\n\n'
        '[features]\nparallel = ["dep:rayon"]\n',
        encoding="utf-8",
    )
    snap = de.extract_dependencies("t", "rust", tmp_path)
    assert snap["required"] == []
    assert len(snap["optional"]) == 1
    entry = snap["optional"][0]
    assert entry["name"] == "rayon"
    assert entry["activating_feature"] == "parallel"


def test_cargo_malformed_toml_raises(tmp_path):
    (tmp_path / "Cargo.toml").write_text("[dependencies\nbroken = true", encoding="utf-8")
    try:
        de.extract_dependencies("t", "rust", tmp_path)
        assert False, "expected DependencyExtractionError"
    except de.DependencyExtractionError:
        pass


def test_cargo_non_string_non_table_value_raises(tmp_path):
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "x"\nversion = "1.0"\n\n[dependencies]\nchrono = 123\n',
        encoding="utf-8",
    )
    try:
        de.extract_dependencies("t", "rust", tmp_path)
        assert False, "expected DependencyExtractionError"
    except de.DependencyExtractionError:
        pass


def test_cargo_extracts_edition_and_rust_version_native_system(tmp_path):
    # readme-refresh-seo-deps-headings-hardening (2026-08-19): native_system was populated for
    # go_modules only -- Cargo's own real [package].edition/rust-version fields were never read.
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "x"\nversion = "1.0"\nedition = "2021"\nrust-version = "1.74"\n\n'
        '[dependencies]\nserde = "1"\n',
        encoding="utf-8",
    )
    snap = de.extract_dependencies("t", "rust", tmp_path)
    native = {e["name"]: e["version_constraint"] for e in snap["native_system"]}
    assert native == {"edition": "2021", "rust-version (MSRV)": "1.74"}


def test_cargo_missing_edition_and_rust_version_omitted_not_guessed(tmp_path):
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "x"\nversion = "1.0"\n\n[dependencies]\nserde = "1"\n',
        encoding="utf-8",
    )
    snap = de.extract_dependencies("t", "rust", tmp_path)
    assert snap["native_system"] == []


# ---------------------------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------------------------


def test_pypi_real_cells_python_shape(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[project]\n"
        'name = "aspose-cells-foss"\n'
        'dependencies = ["pycryptodome>=3.15.0", "olefile>=0.46"]\n\n'
        "[project.optional-dependencies]\n"
        'dev = ["pytest>=7.0.0", "pytest-cov>=4.0.0"]\n',
        encoding="utf-8",
    )
    snap = de.extract_dependencies("cells", "python", tmp_path)
    required_names = {e["name"] for e in snap["required"]}
    dev_names = {e["name"] for e in snap["development"]}
    assert required_names == {"pycryptodome", "olefile"}
    assert dev_names == {"pytest", "pytest-cov"}


def test_pypi_real_barcode_python_shape_pep735_dependency_groups(tmp_path):
    # Found live regenerating barcode/python, 2026-08-14: its real pyproject.toml uses the
    # newer PEP 735 [dependency-groups] table for dev deps, not [project.optional-dependencies]
    # -- the original extractor silently returned an empty `development` list for this shape,
    # with zero parse_errors (worse than raising, since nothing signalled incompleteness).
    (tmp_path / "pyproject.toml").write_text(
        "[project]\n"
        'name = "aspose-barcode-foss"\n'
        'requires-python = ">=3.12"\n'
        'dependencies = ["Pillow>=10.1.0"]\n\n'
        "[dependency-groups]\n"
        'dev = ["pytest>=8.0", "ruff>=0.15.7"]\n',
        encoding="utf-8",
    )
    snap = de.extract_dependencies("barcode", "python", tmp_path)
    required_names = {e["name"] for e in snap["required"]}
    dev_names = {e["name"] for e in snap["development"]}
    assert required_names == {"Pillow"}
    assert dev_names == {"pytest", "ruff"}
    # dev_only entries must never also leak into required/optional (the same Cargo
    # [dev-dependencies]-must-never-leak structural fix, applied here to PEP 735 groups).
    assert "pytest" not in required_names
    assert "ruff" not in required_names


def test_pypi_dependency_groups_skips_include_group_cross_reference(tmp_path):
    # PEP 735 allows a group entry shaped {"include-group": "other-group"} instead of a plain
    # requirement string -- must be skipped, not mis-parsed as a real dependency name.
    (tmp_path / "pyproject.toml").write_text(
        "[project]\n"
        'name = "x"\n'
        'dependencies = []\n\n'
        "[dependency-groups]\n"
        'test = ["pytest>=8.0"]\n'
        'dev = [{include-group = "test"}, "ruff>=0.15.7"]\n',
        encoding="utf-8",
    )
    snap = de.extract_dependencies("t", "python", tmp_path)
    dev_names = {e["name"] for e in snap["development"]}
    assert dev_names == {"pytest", "ruff"}


def test_pypi_setup_cfg_fallback(tmp_path):
    (tmp_path / "setup.cfg").write_text(
        "[options]\ninstall_requires =\n    requests>=2.0\n    click\n", encoding="utf-8",
    )
    snap = de.extract_dependencies("t", "python", tmp_path)
    names = {e["name"] for e in snap["required"]}
    assert names == {"requests", "click"}


def test_pypi_setup_py_only_raises_never_executed(tmp_path):
    (tmp_path / "setup.py").write_text(
        "import os\nos.system('this must never run')\n", encoding="utf-8",
    )
    try:
        de.extract_dependencies("t", "python", tmp_path)
        assert False, "expected DependencyExtractionError"
    except de.DependencyExtractionError as exc:
        assert "setup.py" in str(exc)


def test_pypi_setup_py_only_resolved_via_override(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "dependency_overrides.json").write_text(json.dumps({
        "t/python": {
            "ecosystem": "pypi", "source_manifest_path": "setup.py",
            "required": [{"name": "requests", "version_constraint": None}],
        },
    }), encoding="utf-8")
    manifest_dir = tmp_path / "clone"
    manifest_dir.mkdir()
    (manifest_dir / "setup.py").write_text("print('legacy')\n", encoding="utf-8")
    snap = de.extract_dependencies("t", "python", manifest_dir, pipeline_repo_root=tmp_path)
    assert {e["name"] for e in snap["required"]} == {"requests"}


def test_pypi_extracts_requires_python_native_system(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nrequires-python = ">=3.10"\ndependencies = ["click"]\n',
        encoding="utf-8",
    )
    snap = de.extract_dependencies("t", "python", tmp_path)
    native = {e["name"]: e["version_constraint"] for e in snap["native_system"]}
    assert native == {"requires-python": ">=3.10"}


def test_pypi_setup_cfg_extracts_python_requires_native_system(tmp_path):
    (tmp_path / "setup.cfg").write_text(
        "[options]\npython_requires = >=3.9\ninstall_requires =\n    requests>=2.0\n",
        encoding="utf-8",
    )
    snap = de.extract_dependencies("t", "python", tmp_path)
    native = {e["name"]: e["version_constraint"] for e in snap["native_system"]}
    assert native == {"python_requires": ">=3.9"}


def test_pypi_missing_requires_python_omitted_not_guessed(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\ndependencies = ["click"]\n', encoding="utf-8",
    )
    snap = de.extract_dependencies("t", "python", tmp_path)
    assert snap["native_system"] == []


# ---------------------------------------------------------------------------------------------
# .NET
# ---------------------------------------------------------------------------------------------


def test_nuget_empty_but_parsed_csproj_is_trusted_zero_deps(tmp_path):
    (tmp_path / "Aspose.Cells_FOSS.csproj").write_text(
        '<Project Sdk="Microsoft.NET.Sdk">\n  <PropertyGroup>\n'
        "    <TargetFramework>net8.0</TargetFramework>\n  </PropertyGroup>\n</Project>\n",
        encoding="utf-8",
    )
    snap = de.extract_dependencies("cells", "net", tmp_path)
    assert snap["required"] == []
    assert snap["parse_errors"] == []


def test_nuget_real_package_references(tmp_path):
    (tmp_path / "x.csproj").write_text(
        '<Project Sdk="Microsoft.NET.Sdk">\n  <ItemGroup>\n'
        '    <PackageReference Include="Newtonsoft.Json" Version="13.0.1" />\n'
        "  </ItemGroup>\n</Project>\n",
        encoding="utf-8",
    )
    snap = de.extract_dependencies("t", "net", tmp_path)
    assert {e["name"] for e in snap["required"]} == {"Newtonsoft.Json"}


def test_nuget_malformed_csproj_raises(tmp_path):
    (tmp_path / "x.csproj").write_text("<Project><Unclosed>", encoding="utf-8")
    try:
        de.extract_dependencies("t", "net", tmp_path)
        assert False, "expected DependencyExtractionError"
    except de.DependencyExtractionError:
        pass


def test_nuget_selects_real_main_csproj_over_dot_delimited_test_project(tmp_path):
    # Real, live-confirmed shape (words/net): a real main-library csproj ties in path depth
    # with a dot-delimited test project ("Aspose.Words.Tests") -- the real project must win.
    (tmp_path / "Aspose.Words").mkdir()
    (tmp_path / "Aspose.Words" / "Aspose.Words.csproj").write_text(
        '<Project Sdk="Microsoft.NET.Sdk">\n  <ItemGroup>\n'
        '    <PackageReference Include="RealRuntimeDep" Version="1.0.0" />\n'
        "  </ItemGroup>\n</Project>\n",
        encoding="utf-8",
    )
    (tmp_path / "Aspose.Words.Tests").mkdir()
    (tmp_path / "Aspose.Words.Tests" / "Aspose.Words.Tests.csproj").write_text(
        '<Project Sdk="Microsoft.NET.Sdk">\n  <ItemGroup>\n'
        '    <PackageReference Include="NUnit" Version="3.14.0" />\n'
        "  </ItemGroup>\n</Project>\n",
        encoding="utf-8",
    )
    snap = de.extract_dependencies("words", "net", tmp_path)
    assert snap["source_manifest_path"] == "Aspose.Words/Aspose.Words.csproj"
    assert {e["name"] for e in snap["required"]} == {"RealRuntimeDep"}


def test_nuget_selects_real_main_csproj_over_pascalcase_concatenated_test_project(tmp_path):
    # Real, live-confirmed regression (slides/net): "IntegrationTests" has no dot/word
    # boundary before "Tests" (ordinary C# PascalCase concatenation) -- a naive dot-delimited-
    # segment pattern misses this and the wrong project wins. This is the exact case that
    # forced widening `_TEST_CSPROJ_STEM_RE` from a segment match to a bare substring search.
    (tmp_path / "src" / "Aspose.Slides.Foss").mkdir(parents=True)
    (tmp_path / "src" / "Aspose.Slides.Foss" / "Aspose.Slides.Foss.csproj").write_text(
        '<Project Sdk="Microsoft.NET.Sdk">\n  <ItemGroup>\n'
        '    <PackageReference Include="RealRuntimeDep" Version="1.0.0" />\n'
        "  </ItemGroup>\n</Project>\n",
        encoding="utf-8",
    )
    (tmp_path / "tests" / "Aspose.Slides.Foss.IntegrationTests").mkdir(parents=True)
    (tmp_path / "tests" / "Aspose.Slides.Foss.IntegrationTests" / "Aspose.Slides.Foss.IntegrationTests.csproj").write_text(
        '<Project Sdk="Microsoft.NET.Sdk">\n  <ItemGroup>\n'
        '    <PackageReference Include="xunit" Version="2.9.0" />\n'
        "  </ItemGroup>\n</Project>\n",
        encoding="utf-8",
    )
    snap = de.extract_dependencies("slides", "net", tmp_path)
    assert snap["source_manifest_path"] == "src/Aspose.Slides.Foss/Aspose.Slides.Foss.csproj"
    assert {e["name"] for e in snap["required"]} == {"RealRuntimeDep"}


def test_nuget_prefers_nuspec_over_csproj_for_merged_assembly(tmp_path):
    # Real, live-confirmed shape (words/net): the published package is a MERGED (ILRepack'd)
    # assembly, so the main csproj's own PackageReferences (the merge tool itself, PrivateAssets
    # ="all") have zero overlap with what NuGet actually requires downstream -- only the
    # .nuspec's own real <dependencies> declare the true runtime dependency graph.
    (tmp_path / "Aspose.Words").mkdir()
    (tmp_path / "Aspose.Words" / "Aspose.Words.csproj").write_text(
        '<Project Sdk="Microsoft.NET.Sdk">\n  <ItemGroup>\n'
        '    <PackageReference Include="ILRepack" Version="2.0.46" PrivateAssets="all" />\n'
        "  </ItemGroup>\n</Project>\n",
        encoding="utf-8",
    )
    (tmp_path / "Package").mkdir()
    (tmp_path / "Package" / "Aspose.Words.FOSS.nuspec").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<package xmlns="http://schemas.microsoft.com/packaging/2012/06/nuspec.xsd">\n'
        "  <metadata>\n    <dependencies>\n"
        '      <group targetFramework="net462" />\n'
        '      <group targetFramework=".NETStandard2.0">\n'
        '        <dependency id="SkiaSharp" version="3.119.0" exclude="Build,Analyzers" />\n'
        '        <dependency id="Microsoft.Win32.Registry" version="5.0.0" exclude="Build,Analyzers" />\n'
        "      </group>\n"
        '      <group targetFramework="net8.0">\n'
        '        <dependency id="SkiaSharp" version="3.119.0" exclude="Build,Analyzers" />\n'
        "      </group>\n"
        "    </dependencies>\n  </metadata>\n</package>\n",
        encoding="utf-8",
    )
    snap = de.extract_dependencies("words", "net", tmp_path)
    assert snap["source_manifest_path"] == "Package/Aspose.Words.FOSS.nuspec"
    names = {e["name"] for e in snap["required"]}
    assert names == {"SkiaSharp", "Microsoft.Win32.Registry"}
    registry_entry = next(e for e in snap["required"] if e["name"] == "Microsoft.Win32.Registry")
    assert registry_entry["platform_condition"] == ".NETStandard2.0"
    skia_entry = next(e for e in snap["required"] if e["name"] == "SkiaSharp")
    assert skia_entry["platform_condition"] == ".NETStandard2.0, net8.0"


def test_nuget_private_assets_all_classified_as_dev_only_build_tool(tmp_path):
    # A build/dev-time-only PackageReference (PrivateAssets="all") must never land in
    # `required` -- confirmed real via words/net's own ILRepack/EnumExtensionsGenerator
    # references -- when there's no .nuspec to prefer instead.
    (tmp_path / "x.csproj").write_text(
        '<Project Sdk="Microsoft.NET.Sdk">\n  <ItemGroup>\n'
        '    <PackageReference Include="ILRepack" Version="2.0.46" PrivateAssets="all" />\n'
        '    <PackageReference Include="RealRuntimeDep" Version="1.0.0" />\n'
        "  </ItemGroup>\n</Project>\n",
        encoding="utf-8",
    )
    snap = de.extract_dependencies("t", "net", tmp_path)
    assert {e["name"] for e in snap["required"]} == {"RealRuntimeDep"}
    assert {e["name"] for e in snap["development"]} == {"ILRepack"}
    ilrepack_entry = next(e for e in snap["development"] if e["name"] == "ILRepack")
    assert ilrepack_entry["role"] == "build"


def test_nuget_scans_real_test_project_csproj_for_development_dependencies(tmp_path):
    # Real, confirmed extraction gap (2026-08-17, email/net): _select_main_csproj deliberately
    # EXCLUDES every test-project csproj to find the real library project, but nothing ever
    # scanned the excluded file(s) for their own real, test-only PackageReferences -- so
    # `development` stayed empty even though the real README correctly names real test-project
    # dependencies. Real shape reproduced from email/net's own
    # tests/Aspose.Email.Foss.Tests/Aspose.Email.Foss.Tests.csproj.
    (tmp_path / "src" / "Aspose.X.Foss").mkdir(parents=True)
    (tmp_path / "src" / "Aspose.X.Foss" / "Aspose.X.Foss.csproj").write_text(
        '<Project Sdk="Microsoft.NET.Sdk">\n  <ItemGroup>\n'
        '    <PackageReference Include="RealRuntimeDep" Version="1.0.0" />\n'
        "  </ItemGroup>\n</Project>\n",
        encoding="utf-8",
    )
    (tmp_path / "tests" / "Aspose.X.Foss.Tests").mkdir(parents=True)
    (tmp_path / "tests" / "Aspose.X.Foss.Tests" / "Aspose.X.Foss.Tests.csproj").write_text(
        '<Project Sdk="Microsoft.NET.Sdk">\n  <ItemGroup>\n'
        '    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.8.0" />\n'
        '    <PackageReference Include="xunit" Version="2.5.3" />\n'
        "  </ItemGroup>\n</Project>\n",
        encoding="utf-8",
    )
    snap = de.extract_dependencies("x", "net", tmp_path)
    assert {e["name"] for e in snap["required"]} == {"RealRuntimeDep"}
    dev_names = {e["name"] for e in snap["development"]}
    assert dev_names == {"Microsoft.NET.Test.Sdk", "xunit"}
    assert all(e["dev_only"] for e in snap["development"])
    sdk_entry = next(e for e in snap["development"] if e["name"] == "Microsoft.NET.Test.Sdk")
    assert sdk_entry["version_constraint"] == "17.8.0"


def test_nuget_scans_real_test_project_csproj_when_nuspec_path_used_too(tmp_path):
    # The same gap, confirmed real for the SEPARATE nuspec-authoritative extraction path
    # (words/net: has a real .nuspec, so _extract_nuget_dependencies never reaches the plain-
    # csproj branch at all, and would otherwise never scan the test project either).
    (tmp_path / "Aspose.Words").mkdir()
    (tmp_path / "Aspose.Words" / "Aspose.Words.csproj").write_text(
        '<Project Sdk="Microsoft.NET.Sdk">\n  <ItemGroup>\n'
        '    <PackageReference Include="ILRepack" Version="2.0.46" PrivateAssets="all" />\n'
        "  </ItemGroup>\n</Project>\n",
        encoding="utf-8",
    )
    (tmp_path / "Package").mkdir()
    (tmp_path / "Package" / "Aspose.Words.FOSS.nuspec").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<package xmlns="http://schemas.microsoft.com/packaging/2012/06/nuspec.xsd">\n'
        "  <metadata>\n    <dependencies>\n"
        '      <group targetFramework="net8.0">\n'
        '        <dependency id="SkiaSharp" version="3.119.0" exclude="Build,Analyzers" />\n'
        "      </group>\n"
        "    </dependencies>\n  </metadata>\n</package>\n",
        encoding="utf-8",
    )
    (tmp_path / "Aspose.Words.Tests").mkdir()
    (tmp_path / "Aspose.Words.Tests" / "Aspose.Words.Tests.csproj").write_text(
        '<Project Sdk="Microsoft.NET.Sdk">\n  <ItemGroup>\n'
        '    <PackageReference Include="NUnit" Version="4.2.2" />\n'
        "  </ItemGroup>\n</Project>\n",
        encoding="utf-8",
    )
    snap = de.extract_dependencies("words", "net", tmp_path)
    assert snap["source_manifest_path"] == "Package/Aspose.Words.FOSS.nuspec"
    assert {e["name"] for e in snap["required"]} == {"SkiaSharp"}
    assert {e["name"] for e in snap["development"]} == {"NUnit"}


def test_nuget_extracts_target_frameworks_native_system(tmp_path):
    # readme-refresh-seo-deps-headings-hardening (2026-08-19): real 3d/net shape -- a multi-
    # target <TargetFrameworks> list, mixing net10.0/net8.0/net6.0 with the older netcoreapp3.1
    # idiom. Extraction reports the raw list verbatim; it never computes an "X or later" floor
    # across generations that don't compare numerically in a simple way.
    (tmp_path / "x.csproj").write_text(
        '<Project Sdk="Microsoft.NET.Sdk">\n  <PropertyGroup>\n'
        "    <TargetFrameworks>net10.0;net8.0;net6.0;netcoreapp3.1</TargetFrameworks>\n"
        "  </PropertyGroup>\n</Project>\n",
        encoding="utf-8",
    )
    snap = de.extract_dependencies("3d", "net", tmp_path)
    native = {e["name"]: e["version_constraint"] for e in snap["native_system"]}
    assert native == {"Target Framework(s)": "net10.0, net8.0, net6.0, netcoreapp3.1"}


def test_nuget_single_target_framework_native_system(tmp_path):
    (tmp_path / "x.csproj").write_text(
        '<Project Sdk="Microsoft.NET.Sdk">\n  <PropertyGroup>\n'
        "    <TargetFramework>net8.0</TargetFramework>\n"
        "  </PropertyGroup>\n</Project>\n",
        encoding="utf-8",
    )
    snap = de.extract_dependencies("t", "net", tmp_path)
    native = {e["name"]: e["version_constraint"] for e in snap["native_system"]}
    assert native == {"Target Framework(s)": "net8.0"}


def test_nuget_target_framework_extracted_via_nuspec_path_too(tmp_path):
    # The nuspec-authoritative extraction path never parses the main csproj for dependencies
    # (see _find_nuspec's own docstring) but must still pick up its TargetFramework(s) fact --
    # a .nuspec never carries that concept.
    (tmp_path / "Aspose.Words").mkdir()
    (tmp_path / "Aspose.Words" / "Aspose.Words.csproj").write_text(
        '<Project Sdk="Microsoft.NET.Sdk">\n  <PropertyGroup>\n'
        "    <TargetFrameworks>net8.0;net462</TargetFrameworks>\n"
        "  </PropertyGroup>\n  <ItemGroup>\n"
        '    <PackageReference Include="ILRepack" Version="2.0.46" PrivateAssets="all" />\n'
        "  </ItemGroup>\n</Project>\n",
        encoding="utf-8",
    )
    (tmp_path / "Package").mkdir()
    (tmp_path / "Package" / "Aspose.Words.FOSS.nuspec").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<package xmlns="http://schemas.microsoft.com/packaging/2012/06/nuspec.xsd">\n'
        "  <metadata>\n    <dependencies>\n"
        '      <group targetFramework="net8.0">\n'
        '        <dependency id="SkiaSharp" version="3.119.0" />\n'
        "      </group>\n"
        "    </dependencies>\n  </metadata>\n</package>\n",
        encoding="utf-8",
    )
    snap = de.extract_dependencies("words", "net", tmp_path)
    assert snap["source_manifest_path"] == "Package/Aspose.Words.FOSS.nuspec"
    native = {e["name"]: e["version_constraint"] for e in snap["native_system"]}
    assert native == {"Target Framework(s)": "net8.0, net462"}


def test_nuget_selects_library_over_exe_output_on_path_depth_tie(tmp_path):
    # Real, live latent shape found reviewing 3d/net (2026-08-19): a demo/converter console
    # tool ties in path depth with the real library and isn't test-named, so the original
    # shortest-path-wins heuristic (with no secondary key) would pick the demo tool.
    (tmp_path / "src" / "converter").mkdir(parents=True)
    (tmp_path / "src" / "converter" / "Converter.csproj").write_text(
        '<Project Sdk="Microsoft.NET.Sdk">\n  <PropertyGroup>\n'
        "    <OutputType>Exe</OutputType>\n  </PropertyGroup>\n</Project>\n",
        encoding="utf-8",
    )
    (tmp_path / "src" / "main" / "Aspose.ThreeD").mkdir(parents=True)
    (tmp_path / "src" / "main" / "Aspose.ThreeD" / "Aspose.ThreeD.csproj").write_text(
        '<Project Sdk="Microsoft.NET.Sdk">\n  <ItemGroup>\n'
        '    <PackageReference Include="RealRuntimeDep" Version="1.0.0" />\n'
        "  </ItemGroup>\n</Project>\n",
        encoding="utf-8",
    )
    snap = de.extract_dependencies("3d", "net", tmp_path)
    assert snap["source_manifest_path"] == "src/main/Aspose.ThreeD/Aspose.ThreeD.csproj"
    assert {e["name"] for e in snap["required"]} == {"RealRuntimeDep"}


# ---------------------------------------------------------------------------------------------
# Java
# ---------------------------------------------------------------------------------------------


def test_maven_real_default_xmlns_declared_still_parses(tmp_path):
    """The real, confirmed Maven pitfall: a naive `.//dependency` search silently returns zero
    results against a pom.xml with the real default xmlns declared, unless it's stripped
    first."""
    (tmp_path / "pom.xml").write_text(
        '<project xmlns="http://maven.apache.org/POM/4.0.0">\n'
        "  <dependencies>\n"
        "    <dependency>\n"
        "      <groupId>org.junit.jupiter</groupId>\n"
        "      <artifactId>junit-jupiter</artifactId>\n"
        "      <version>5.9.0</version>\n"
        "      <scope>test</scope>\n"
        "    </dependency>\n"
        "    <dependency>\n"
        "      <groupId>com.example</groupId>\n"
        "      <artifactId>runtime-lib</artifactId>\n"
        "      <version>1.0</version>\n"
        "    </dependency>\n"
        "  </dependencies>\n</project>\n",
        encoding="utf-8",
    )
    snap = de.extract_dependencies("t", "java", tmp_path)
    dev_names = {e["name"] for e in snap["development"]}
    required_names = {e["name"] for e in snap["required"]}
    assert "org.junit.jupiter:junit-jupiter" in dev_names
    assert "com.example:runtime-lib" in required_names


def test_maven_dependency_management_never_counted(tmp_path):
    (tmp_path / "pom.xml").write_text(
        "<project>\n  <dependencyManagement>\n    <dependencies>\n"
        "      <dependency><groupId>x</groupId><artifactId>y</artifactId><version>1</version></dependency>\n"
        "    </dependencies>\n  </dependencyManagement>\n</project>\n",
        encoding="utf-8",
    )
    snap = de.extract_dependencies("t", "java", tmp_path)
    assert snap["required"] == []
    assert snap["development"] == []


def test_maven_real_cells_java_shape_zero_runtime(tmp_path):
    (tmp_path / "pom.xml").write_text(
        "<project>\n  <dependencies>\n"
        "    <dependency><groupId>org.junit.jupiter</groupId><artifactId>junit-jupiter</artifactId>"
        "<version>5.9.0</version><scope>test</scope></dependency>\n"
        "    <dependency><groupId>org.apache.poi</groupId><artifactId>poi-ooxml</artifactId>"
        "<version>5.2.0</version><scope>test</scope></dependency>\n"
        "  </dependencies>\n</project>\n",
        encoding="utf-8",
    )
    snap = de.extract_dependencies("cells", "java", tmp_path)
    assert snap["required"] == []
    assert len(snap["development"]) == 2


def test_maven_extracts_java_version_native_system_from_properties(tmp_path):
    (tmp_path / "pom.xml").write_text(
        "<project>\n  <properties>\n"
        "    <maven.compiler.release>17</maven.compiler.release>\n"
        "  </properties>\n  <dependencies>\n"
        "    <dependency><groupId>com.example</groupId><artifactId>runtime-lib</artifactId>"
        "<version>1.0</version></dependency>\n"
        "  </dependencies>\n</project>\n",
        encoding="utf-8",
    )
    snap = de.extract_dependencies("t", "java", tmp_path)
    native = {e["name"]: e["version_constraint"] for e in snap["native_system"]}
    assert native == {"maven.compiler.release": "17"}


def test_maven_java_version_property_absent_omitted_not_guessed(tmp_path):
    (tmp_path / "pom.xml").write_text(
        "<project>\n  <dependencies>\n"
        "    <dependency><groupId>com.example</groupId><artifactId>runtime-lib</artifactId>"
        "<version>1.0</version></dependency>\n"
        "  </dependencies>\n</project>\n",
        encoding="utf-8",
    )
    snap = de.extract_dependencies("t", "java", tmp_path)
    assert snap["native_system"] == []


def test_maven_gradle_extracts_source_compatibility_native_system(tmp_path):
    (tmp_path / "build.gradle").write_text(
        "sourceCompatibility = '11'\n"
        "dependencies {\n    implementation 'com.example:runtime-lib:1.0'\n}\n",
        encoding="utf-8",
    )
    snap = de.extract_dependencies("t", "java", tmp_path)
    native = {e["name"]: e["version_constraint"] for e in snap["native_system"]}
    assert native == {"java": "11"}


def test_maven_gradle_extracts_toolchain_language_version_native_system(tmp_path):
    (tmp_path / "build.gradle.kts").write_text(
        "java {\n    toolchain {\n        languageVersion.set(JavaLanguageVersion.of(21))\n"
        "    }\n}\n"
        "dependencies {\n    implementation(\"com.example:runtime-lib:1.0\")\n}\n",
        encoding="utf-8",
    )
    snap = de.extract_dependencies("t", "java", tmp_path)
    native = {e["name"]: e["version_constraint"] for e in snap["native_system"]}
    assert native == {"java": "21"}


# ---------------------------------------------------------------------------------------------
# Go
# ---------------------------------------------------------------------------------------------


def test_go_mod_indirect_dependency_excluded(tmp_path):
    (tmp_path / "go.mod").write_text(
        "module github.com/aspose-cells-foss/aspose-cells-foss-go\n\ngo 1.21\n\n"
        "require (\n"
        "\tgithub.com/direct/dep v1.2.3\n"
        "\tgithub.com/transitive/dep v0.1.0 // indirect\n"
        ")\n",
        encoding="utf-8",
    )
    snap = de.extract_dependencies("t", "go", tmp_path)
    names = {e["name"] for e in snap["required"]}
    assert names == {"github.com/direct/dep"}
    assert "github.com/transitive/dep" not in names


def test_go_mod_real_cells_go_shape_no_require_block(tmp_path):
    (tmp_path / "go.mod").write_text(
        "module github.com/aspose-cells-foss/aspose-cells-foss-go\n\ngo 1.24.5\n",
        encoding="utf-8",
    )
    snap = de.extract_dependencies("cells", "go", tmp_path)
    assert snap["required"] == []
    assert {e["name"]: e["version_constraint"] for e in snap["native_system"]} == {"go": "1.24.5"}


def test_go_mod_absent_raises(tmp_path):
    try:
        de.extract_dependencies("t", "go", tmp_path)
        assert False, "expected DependencyExtractionError"
    except de.DependencyExtractionError:
        pass


# ---------------------------------------------------------------------------------------------
# npm
# ---------------------------------------------------------------------------------------------


def test_npm_real_3d_typescript_shape(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "x", "dependencies": {"xmldom": "^0.6.0"}}), encoding="utf-8",
    )
    snap = de.extract_dependencies("3d", "typescript", tmp_path)
    assert {e["name"]: e["version_constraint"] for e in snap["required"]} == {"xmldom": "^0.6.0"}


def test_npm_three_way_bucketing(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({
        "name": "x",
        "dependencies": {"a": "1.0"},
        "devDependencies": {"b": "2.0"},
        "optionalDependencies": {"c": "3.0"},
    }), encoding="utf-8")
    snap = de.extract_dependencies("t", "typescript", tmp_path)
    assert {e["name"] for e in snap["required"]} == {"a"}
    assert {e["name"] for e in snap["development"]} == {"b"}
    assert {e["name"] for e in snap["optional"]} == {"c"}


def test_npm_extracts_engines_node_native_system(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({
        "name": "x",
        "engines": {"node": ">=18.0.0"},
        "dependencies": {"xmldom": "^0.6.0"},
    }), encoding="utf-8")
    snap = de.extract_dependencies("3d", "typescript", tmp_path)
    native = {e["name"]: e["version_constraint"] for e in snap["native_system"]}
    assert native == {"node": ">=18.0.0"}


def test_npm_missing_engines_omitted_not_guessed(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "x", "dependencies": {"xmldom": "^0.6.0"}}), encoding="utf-8",
    )
    snap = de.extract_dependencies("t", "typescript", tmp_path)
    assert snap["native_system"] == []


# ---------------------------------------------------------------------------------------------
# C++
# ---------------------------------------------------------------------------------------------


def test_cpp_no_manifest_anywhere_is_not_applicable(tmp_path):
    snap = de.extract_dependencies("cells", "cpp", tmp_path)
    assert snap["applicable"] is False
    assert "precompiled" in snap["not_applicable_reason"]
    assert snap["required"] == []


def test_cpp_real_cells_cpp_shape_nested_zero_dep_cmakelists(tmp_path):
    """The real, confirmed cells/cpp shape: a genuine, dependency-free CMakeLists.txt one
    level down (not at repo root) -- must be found and trusted as a real zero-dependency
    result, never treated as a possible regex miss just because the file is substantial."""
    nested = tmp_path / "Aspose.Cells.Foss.Cpp"
    nested.mkdir()
    (nested / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.16)\nproject(aspose_cells_foss_cpp LANGUAGES CXX)\n"
        "set(CMAKE_CXX_STANDARD 17)\n"
        "file(GLOB_RECURSE SRC CONFIGURE_DEPENDS src/*.cpp)\n"
        "add_library(aspose_cells_foss STATIC ${SRC})\n"
        "enable_testing()\nadd_subdirectory(tests)\n",
        encoding="utf-8",
    )
    snap = de.extract_dependencies("cells", "cpp", tmp_path)
    assert snap["applicable"] is True
    assert snap["required"] == []
    assert snap["parse_errors"] == []


def test_cpp_cmakelists_with_fetchcontent_only_target_is_dev_only(tmp_path):
    # 2026-08-17 (slides/* portfolio audit): FetchContent_Declare is now parsed directly, not
    # treated as an unparseable "ask a human" signal -- this fixture (googletest, never linked
    # to any non-test target) must land in `development`, not raise.
    (tmp_path / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.16)\n"
        "include(FetchContent)\n"
        "FetchContent_Declare(googletest URL https://example.com/gtest.zip)\n"
        "FetchContent_MakeAvailable(googletest)\n"
        "add_executable(t_tests test.cpp)\n"
        "target_link_libraries(t_tests PRIVATE GTest::gtest_main)\n",
        encoding="utf-8",
    )
    snap = de.extract_dependencies("t", "cpp", tmp_path)
    assert snap["required"] == []
    assert [e["name"] for e in snap["development"]] == ["googletest"]
    assert snap["development"][0]["dev_only"] is True
    assert snap["development"][0]["role"] == "build"


def test_cpp_cmakelists_fetchcontent_real_slides_cpp_shape(tmp_path):
    # Real, captured-verbatim slides/cpp shape: 2 runtime deps (linked directly to the main
    # library target) + 1 test-only dep (linked only to the `_tests` executable via GTest::).
    (tmp_path / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.20)\n"
        "project(aspose_slides_foss LANGUAGES CXX)\n"
        "add_library(${PROJECT_NAME} src/x.cpp)\n"
        "include(FetchContent)\n"
        "FetchContent_Declare(\n"
        "    pugixml\n"
        "    GIT_REPOSITORY https://github.com/zeux/pugixml.git\n"
        "    GIT_TAG v1.14\n"
        ")\n"
        "FetchContent_MakeAvailable(pugixml)\n"
        "target_link_libraries(${PROJECT_NAME} PUBLIC pugixml::pugixml)\n"
        "FetchContent_Declare(\n"
        "    miniz\n"
        "    GIT_REPOSITORY https://github.com/richgel999/miniz.git\n"
        "    GIT_TAG 3.0.2\n"
        ")\n"
        "FetchContent_MakeAvailable(miniz)\n"
        "target_link_libraries(${PROJECT_NAME} PUBLIC miniz)\n"
        "FetchContent_Declare(\n"
        "    googletest\n"
        "    GIT_REPOSITORY https://github.com/google/googletest.git\n"
        "    GIT_TAG v1.15.2\n"
        ")\n"
        "FetchContent_MakeAvailable(googletest)\n"
        "enable_testing()\n"
        "add_executable(${PROJECT_NAME}_tests test.cpp)\n"
        "target_link_libraries(${PROJECT_NAME}_tests PRIVATE ${PROJECT_NAME} GTest::gtest_main "
        "GTest::gmock)\n",
        encoding="utf-8",
    )
    snap = de.extract_dependencies("slides", "cpp", tmp_path)
    required = {e["name"]: e["version_constraint"] for e in snap["required"]}
    assert required == {"pugixml": "v1.14", "miniz": "3.0.2"}
    assert all(e["source_type"] == "git" for e in snap["required"])
    dev = {e["name"]: e["version_constraint"] for e in snap["development"]}
    assert dev == {"googletest": "v1.15.2"}


def test_cpp_cmakelists_fetchcontent_plus_find_package_both_extracted(tmp_path):
    # Regression guard: a file using BOTH find_package and FetchContent_Declare must extract
    # entries from both mechanisms, not only one.
    (tmp_path / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.16)\n"
        "add_library(${PROJECT_NAME} src/x.cpp)\n"
        "find_package(ZLIB REQUIRED)\n"
        "target_link_libraries(${PROJECT_NAME} PUBLIC ZLIB::ZLIB)\n"
        "include(FetchContent)\n"
        "FetchContent_Declare(fmt GIT_REPOSITORY https://github.com/fmtlib/fmt.git GIT_TAG 10.2.1)\n"
        "FetchContent_MakeAvailable(fmt)\n"
        "target_link_libraries(${PROJECT_NAME} PUBLIC fmt::fmt)\n",
        encoding="utf-8",
    )
    snap = de.extract_dependencies("t", "cpp", tmp_path)
    names = {e["name"] for e in snap["required"]}
    assert names == {"ZLIB", "fmt"}


def test_cpp_vcpkg_json(tmp_path):
    (tmp_path / "vcpkg.json").write_text(
        json.dumps({"name": "x", "dependencies": ["fmt", "zlib"]}), encoding="utf-8",
    )
    snap = de.extract_dependencies("t", "cpp", tmp_path)
    assert {e["name"] for e in snap["required"]} == {"fmt", "zlib"}


# ---------------------------------------------------------------------------------------------
# Dispatch / unregistered platform
# ---------------------------------------------------------------------------------------------


def test_unregistered_platform_raises(tmp_path):
    try:
        de.extract_dependencies("t", "cobol", tmp_path)
        assert False, "expected DependencyExtractionError"
    except de.DependencyExtractionError as exc:
        assert "no ecosystem registered" in str(exc)


def test_unregistered_platform_resolved_via_override(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "dependency_overrides.json").write_text(json.dumps({
        "t/cobol": {
            "ecosystem": "none",
            "required": [{"name": "some-lib", "version_constraint": None}],
        },
    }), encoding="utf-8")
    snap = de.extract_dependencies("t", "cobol", tmp_path, pipeline_repo_root=tmp_path)
    assert {e["name"] for e in snap["required"]} == {"some-lib"}


# ---------------------------------------------------------------------------------------------
# claims.json corroboration
# ---------------------------------------------------------------------------------------------


def test_cross_reference_dependency_claims_real_cells_rust_shape(tmp_path):
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "x"\nversion = "1.0"\n\n[dependencies]\nchrono = "0.4"\nzip = "0.6"\n',
        encoding="utf-8",
    )
    snap = de.extract_dependencies("cells", "rust", tmp_path, source_revision="abc123")
    claims = [
        {"kind": "dependency", "text": "Depends on chrono"},
        {"kind": "dependency", "text": "Depends on stale-removed-crate"},
    ]
    result = de.cross_reference_dependency_claims(snap, claims, knowledge_repo_sha="abc123")
    assert result["matched"] == ["chrono"]
    assert result["manifest_only"] == ["zip"]
    assert result["claims_only"] == ["stale-removed-crate"]
    assert result["same_revision"] is True


def test_cross_reference_dependency_claims_different_revision():
    snap = {"required": [], "optional": [], "source_revision": "new-sha"}
    result = de.cross_reference_dependency_claims(snap, [], knowledge_repo_sha="old-sha")
    assert result["same_revision"] is False
