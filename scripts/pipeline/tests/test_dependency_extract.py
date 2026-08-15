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


def test_cpp_cmakelists_with_fetchcontent_raises(tmp_path):
    (tmp_path / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.16)\n"
        "include(FetchContent)\n"
        "FetchContent_Declare(googletest URL https://example.com/gtest.zip)\n"
        "FetchContent_MakeAvailable(googletest)\n",
        encoding="utf-8",
    )
    try:
        de.extract_dependencies("t", "cpp", tmp_path)
        assert False, "expected DependencyExtractionError"
    except de.DependencyExtractionError as exc:
        assert "FetchContent_Declare" in str(exc)


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
