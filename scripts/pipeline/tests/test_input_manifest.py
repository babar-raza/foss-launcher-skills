"""Tests for scripts/pipeline/lib/input_manifest.py (TC-13 slice,
readme-refresh-trackb-and-followon-2026-09-01).

Real regression input: tex/python's own documented BLOCKER (this mission's TC-27a
canary) -- data/aspose_com_targets.json corrected 4 days after the candidate was
composed, undetected because nothing recorded what the candidate was built against.
"""

import json
import subprocess
from pathlib import Path

import pytest

from lib import input_manifest as im


@pytest.fixture(autouse=True)
def _reset():
    yield
    im.configure()


def _init_real_git_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=str(path), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(path), check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(path), check=True)
    (path / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(path), check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=str(path), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=str(path), check=True)


def _write_targets(repo_root: Path, platforms: dict) -> None:
    (repo_root / "data").mkdir(parents=True, exist_ok=True)
    (repo_root / "data" / "aspose_com_targets.json").write_text(
        json.dumps({"targets": {"products.aspose.com": {"platforms": platforms}}}), encoding="utf-8",
    )


def test_resolve_manifest_real_clone_cache_and_ee_target(tmp_path):
    repo_root = tmp_path / "repo"
    clone_cache = repo_root / "clone"
    _init_real_git_repo(clone_cache)
    _write_targets(repo_root, {"tex/python": {"url": "https://products.aspose.com/tex/python/", "http_status": 200}})
    im.configure(repo_root=repo_root)

    manifest = im.resolve_input_manifest("tex", "python", clone_cache)
    assert manifest["clone_cache"]["commit"] is not None
    assert manifest["clone_cache"]["tree"] is not None
    assert manifest["enterprise_edition_target"]["entry"]["url"] == "https://products.aspose.com/tex/python/"
    assert manifest["manifest_hash"]


def test_resolve_manifest_handles_missing_clone_cache_and_registry(tmp_path):
    repo_root = tmp_path / "repo"
    (repo_root / "data").mkdir(parents=True)
    im.configure(repo_root=repo_root)

    manifest = im.resolve_input_manifest("nope", "nope", repo_root / "no-such-clone")
    assert manifest["clone_cache"]["commit"] is None
    assert manifest["clone_cache"]["tree"] is None
    assert manifest["enterprise_edition_target"]["entry"] is None
    assert manifest["manifest_hash"]  # still hashes cleanly, never raises


def test_diff_manifests_empty_when_identical():
    m = {"clone_cache": {"commit": "abc", "tree": "def"},
         "enterprise_edition_target": {"entry_sha256": "xyz"}}
    assert im.diff_manifests(m, m) == []


def test_diff_manifests_real_tex_python_regression_ee_target_changed_after_compose():
    """The exact real incident: the EE target entry changes underneath an already-composed
    candidate. Must be named specifically, not just 'something changed'."""
    pinned = {"clone_cache": {"commit": "abc", "tree": "def"},
              "enterprise_edition_target": {"entry_sha256": "old-hash"}}
    current = {"clone_cache": {"commit": "abc", "tree": "def"},
               "enterprise_edition_target": {"entry_sha256": "new-hash"}}
    diffs = im.diff_manifests(pinned, current)
    assert len(diffs) == 1
    assert "aspose_com_targets.json" in diffs[0]


def test_diff_manifests_detects_clone_cache_drift_separately_from_registry_drift():
    pinned = {"clone_cache": {"commit": "abc", "tree": "tree1"},
              "enterprise_edition_target": {"entry_sha256": "same"}}
    current = {"clone_cache": {"commit": "xyz", "tree": "tree2"},
               "enterprise_edition_target": {"entry_sha256": "same"}}
    diffs = im.diff_manifests(pinned, current)
    assert len(diffs) == 2
    assert any("commit" in d for d in diffs)
    assert any("tree" in d for d in diffs)


def test_manifest_hash_changes_when_ee_target_entry_changes(tmp_path):
    repo_root = tmp_path / "repo"
    clone_cache = repo_root / "clone"
    _init_real_git_repo(clone_cache)
    im.configure(repo_root=repo_root)

    _write_targets(repo_root, {"tex/python": {"url": "https://products.aspose.com/tex/python/", "http_status": 200}})
    before = im.resolve_input_manifest("tex", "python", clone_cache)

    _write_targets(repo_root, {"tex/python": {"url": "https://products.aspose.com/tex/python-corrected/", "http_status": 200}})
    after = im.resolve_input_manifest("tex", "python", clone_cache)

    assert before["manifest_hash"] != after["manifest_hash"]
    diffs = im.diff_manifests(before, after)
    assert len(diffs) == 1
    assert "aspose_com_targets.json" in diffs[0]


# --- resolve_manifest_version (TC-14, MT061-2026-09-01-TRACKB-FOLLOWON-2) ------------------------
# Real regression input: `data/package_registry.json` was confirmed live to carry NO version at
# all for any product on the current scout mechanism (every `scout_source` starting
# `"package_manifest.py:"` has `candidate.version: None`) -- the real "current version" source is
# each product's own clone-cache manifest file. Fixture shapes below mirror real, live-confirmed
# per-language layouts found in `runs/.clone_cache/` while building this resolver (file names,
# nesting, and edge cases are all real, not invented).

def test_resolve_manifest_version_dotnet_pdf_net_canary(tmp_path):
    # The mission's own mandatory acceptance criterion: reproduce the already-manually-verified
    # v26.8.0 (TC-31, parent mission) before this resolver is trusted on anything else. Fixture
    # mirrors pdf/net's real clone shape exactly: a `src/*.csproj` with the real <Version>, plus
    # a sibling `tests/*.csproj` with NO Version tag -- the resolver must not pick the tests file.
    clone = tmp_path / "clone"
    (clone / "src").mkdir(parents=True)
    (clone / "tests").mkdir(parents=True)
    (clone / "src" / "Aspose.Pdf.Foss.csproj").write_text(
        "<Project><PropertyGroup><Version>26.8.0</Version></PropertyGroup></Project>", encoding="utf-8",
    )
    (clone / "tests" / "Aspose.Pdf.Foss.Tests.csproj").write_text(
        "<Project><PropertyGroup><TargetFramework>net8.0</TargetFramework></PropertyGroup></Project>", encoding="utf-8",
    )
    result = im.resolve_manifest_version("pdf", "net", clone)
    assert result["version"] == "26.8.0"
    assert result["source_path"] == "src/Aspose.Pdf.Foss.csproj"
    assert result["source_field"] == "Version"


def test_resolve_manifest_version_dotnet_no_csproj(tmp_path):
    clone = tmp_path / "clone"
    clone.mkdir()
    result = im.resolve_manifest_version("pdf", "net", clone)
    assert result["version"] is None
    assert "no .csproj" in result["reason"]


def test_resolve_manifest_version_typescript_package_json(tmp_path):
    clone = tmp_path / "clone"
    clone.mkdir()
    (clone / "package.json").write_text(json.dumps({"name": "excel-cells", "version": "1.0.0"}), encoding="utf-8")
    result = im.resolve_manifest_version("cells", "typescript", clone)
    assert result == {"version": "1.0.0", "source_path": "package.json", "source_field": "version"}


def test_resolve_manifest_version_java_pom_scopes_to_project_own_version_not_parent(tmp_path):
    # A real pom.xml can declare a <parent> block (with ITS OWN <version>) before the project's
    # own groupId/artifactId/version -- a naive "first <version> in the file" scan would pick the
    # WRONG one. This fixture deliberately puts the parent's version first to prove the resolver
    # is scoped to the root <project> element's own direct child, not just the first match.
    clone = tmp_path / "clone"
    clone.mkdir()
    (clone / "pom.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<project xmlns="http://maven.apache.org/POM/4.0.0">\n'
        "  <parent>\n"
        "    <groupId>org.aspose</groupId>\n"
        "    <artifactId>aspose-parent</artifactId>\n"
        "    <version>1.0.0</version>\n"
        "  </parent>\n"
        "  <groupId>org.aspose</groupId>\n"
        "  <artifactId>aspose-cells-foss</artifactId>\n"
        "  <version>26.7.0</version>\n"
        "  <dependencies>\n"
        "    <dependency><groupId>org.junit.jupiter</groupId><artifactId>junit-jupiter</artifactId>"
        "<version>5.10.2</version></dependency>\n"
        "  </dependencies>\n"
        "</project>\n",
        encoding="utf-8",
    )
    result = im.resolve_manifest_version("cells", "java", clone)
    assert result["version"] == "26.7.0"
    assert result["source_path"] == "pom.xml"


def test_resolve_manifest_version_java_pom_with_bom_and_encoding_declaration(tmp_path):
    # Real, confirmed-live gotcha: a decoded str passed to ET.fromstring() raises ValueError when
    # the XML carries an `encoding="UTF-8"` declaration; one real product's pom.xml also has a
    # leading UTF-8 BOM. Both are exercised together here (bytes, not str, on disk).
    clone = tmp_path / "clone"
    clone.mkdir()
    xml_bytes = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<project xmlns="http://maven.apache.org/POM/4.0.0">\n'
        "  <groupId>org.aspose</groupId><artifactId>aspose-3d-foss</artifactId>"
        "  <version>26.5.0</version>\n"
        "</project>\n"
    ).encode("utf-8-sig")
    (clone / "pom.xml").write_bytes(xml_bytes)
    result = im.resolve_manifest_version("3d", "java", clone)
    assert result["version"] == "26.5.0"


def test_resolve_manifest_version_java_gradle_fallback(tmp_path):
    clone = tmp_path / "clone"
    clone.mkdir()
    (clone / "build.gradle").write_text("group = 'org.aspose'\nversion = '26.7.0'\n", encoding="utf-8")
    result = im.resolve_manifest_version("cells", "java", clone)
    assert result == {"version": "26.7.0", "source_path": "build.gradle", "source_field": "version"}


def test_resolve_manifest_version_rust_cargo_toml(tmp_path):
    clone = tmp_path / "clone"
    clone.mkdir()
    (clone / "Cargo.toml").write_text('[package]\nname = "aspose-cells-foss-rust"\nversion = "26.7.0"\n', encoding="utf-8")
    result = im.resolve_manifest_version("cells", "rust", clone)
    assert result == {"version": "26.7.0", "source_path": "Cargo.toml", "source_field": "package.version"}


def test_resolve_manifest_version_rust_nested_workspace_fallback(tmp_path):
    # Matches package_manifest.py's own established nested/workspace fallback: no Cargo.toml at
    # the clone root, but a first-level subdirectory has one.
    clone = tmp_path / "clone"
    (clone / "aspose-cells-foss-rust").mkdir(parents=True)
    (clone / "aspose-cells-foss-rust" / "Cargo.toml").write_text(
        '[package]\nname = "aspose-cells-foss-rust"\nversion = "26.7.0"\n', encoding="utf-8",
    )
    result = im.resolve_manifest_version("cells", "rust", clone)
    assert result["version"] == "26.7.0"
    assert result["source_path"] == "aspose-cells-foss-rust/Cargo.toml"


def test_resolve_manifest_version_python_pyproject_literal(tmp_path):
    clone = tmp_path / "clone"
    clone.mkdir()
    (clone / "pyproject.toml").write_text('[project]\nname = "aspose-words-foss"\nversion = "26.7.0"\n', encoding="utf-8")
    result = im.resolve_manifest_version("words", "python", clone)
    assert result == {"version": "26.7.0", "source_path": "pyproject.toml", "source_field": "project.version"}


def test_resolve_manifest_version_python_setup_py_ast_literal(tmp_path):
    # Real shape: 3d/python has no pyproject.toml at all, only a legacy setup.py.
    clone = tmp_path / "clone"
    clone.mkdir()
    (clone / "setup.py").write_text(
        "from setuptools import setup\nsetup(\n    name='aspose-3d-foss',\n    version='26.1.0',\n)\n",
        encoding="utf-8",
    )
    result = im.resolve_manifest_version("3d", "python", clone)
    assert result == {"version": "26.1.0", "source_path": "setup.py", "source_field": "ast:setup(version=...)"}


def test_resolve_manifest_version_python_setup_py_never_execs_untrusted_code(tmp_path):
    # A malicious/broken setup.py must never be executed -- only its AST is walked (or a regex
    # fallback used). This file would raise/side-effect if exec()'d; the resolver must not crash
    # and must still find the literal version via the AST walk.
    clone = tmp_path / "clone"
    clone.mkdir()
    (clone / "setup.py").write_text(
        "import sys\nsys.exit(1)  # would blow up any exec()-based extractor\n"
        "from setuptools import setup\nsetup(name='x', version='9.9.9')\n",
        encoding="utf-8",
    )
    result = im.resolve_manifest_version("x", "python", clone)
    assert result["version"] == "9.9.9"


def test_resolve_manifest_version_python_dynamic_attr_pdf_python_shape(tmp_path):
    # Real, confirmed-live shape: pdf/python's pyproject.toml declares
    # `dynamic = ["version"]` + `[tool.setuptools.dynamic] version = {attr = "..."}`, with the
    # real value living in a separate source file, not literally in pyproject.toml at all.
    clone = tmp_path / "clone"
    (clone / "src" / "aspose_pdf").mkdir(parents=True)
    (clone / "pyproject.toml").write_text(
        "[project]\n"
        'name = "aspose-pdf-foss-for-python"\n'
        'dynamic = ["version"]\n\n'
        "[tool.setuptools.dynamic]\n"
        'version = { attr = "aspose_pdf._version.__release_version__" }\n',
        encoding="utf-8",
    )
    (clone / "src" / "aspose_pdf" / "_version.py").write_text(
        '__release_version__ = "0.1.0"\n', encoding="utf-8",
    )
    result = im.resolve_manifest_version("pdf", "python", clone)
    assert result["version"] == "0.1.0"
    assert result["source_path"] == "src/aspose_pdf/_version.py"
    assert result["source_field"] == "dynamic:aspose_pdf._version.__release_version__"


def test_resolve_manifest_version_python_dynamic_attr_unresolvable_file_missing(tmp_path):
    clone = tmp_path / "clone"
    clone.mkdir()
    (clone / "pyproject.toml").write_text(
        '[project]\nname = "x"\ndynamic = ["version"]\n\n'
        "[tool.setuptools.dynamic]\n"
        'version = { attr = "nosuchpkg._version.__release_version__" }\n',
        encoding="utf-8",
    )
    result = im.resolve_manifest_version("x", "python", clone)
    assert result["version"] is None
    assert "no file matching" in result["reason"]


def test_resolve_manifest_version_python_no_pyproject_no_setup_py(tmp_path):
    clone = tmp_path / "clone"
    clone.mkdir()
    result = im.resolve_manifest_version("x", "python", clone)
    assert result["version"] is None
    assert "no pyproject.toml or setup.py" in result["reason"]


def test_resolve_manifest_version_cpp_root_level_version_present(tmp_path):
    clone = tmp_path / "clone"
    clone.mkdir()
    (clone / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.20)\nproject(Aspose_PDF_FOSS VERSION 1.0.0 LANGUAGES CXX)\n",
        encoding="utf-8",
    )
    result = im.resolve_manifest_version("pdf", "cpp", clone)
    assert result == {"version": "1.0.0", "source_path": "CMakeLists.txt", "source_field": "project(...VERSION...)"}


def test_resolve_manifest_version_cpp_root_level_no_version_declared(tmp_path):
    # Real, confirmed-live fact (slides/cpp): a project() call with genuinely no VERSION field.
    # Must be an explicit, honest miss -- not a crash, not a guessed value.
    clone = tmp_path / "clone"
    clone.mkdir()
    (clone / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.20)\nproject(aspose_slides_foss LANGUAGES CXX)\n", encoding="utf-8",
    )
    result = im.resolve_manifest_version("slides", "cpp", clone)
    assert result["version"] is None
    assert "no VERSION field" in result["reason"]


def test_resolve_manifest_version_cpp_nested_manifest_not_at_repo_root(tmp_path):
    # Real, confirmed-live shape (cells/cpp): no CMakeLists.txt at the clone root at all -- the
    # real one is nested at Aspose.Cells.Foss.Cpp/CMakeLists.txt. A sibling tests/ CMakeLists.txt
    # must NOT be picked over it.
    clone = tmp_path / "clone"
    (clone / "Aspose.Cells.Foss.Cpp").mkdir(parents=True)
    (clone / "Aspose.Cells.Foss.Cpp" / "tests").mkdir(parents=True)
    (clone / "Aspose.Cells.Foss.Cpp" / "CMakeLists.txt").write_text(
        "project(aspose_cells_foss_cpp VERSION 2.3.4 LANGUAGES CXX)\n", encoding="utf-8",
    )
    (clone / "Aspose.Cells.Foss.Cpp" / "tests" / "CMakeLists.txt").write_text(
        "project(aspose_cells_foss_cpp_tests VERSION 9.9.9 LANGUAGES CXX)\n", encoding="utf-8",
    )
    result = im.resolve_manifest_version("cells", "cpp", clone)
    assert result["version"] == "2.3.4"
    assert result["source_path"] == "Aspose.Cells.Foss.Cpp/CMakeLists.txt"


def test_resolve_manifest_version_cpp_no_cmakelists_anywhere(tmp_path):
    clone = tmp_path / "clone"
    clone.mkdir()
    result = im.resolve_manifest_version("x", "cpp", clone)
    assert result["version"] is None
    assert "no CMakeLists.txt" in result["reason"]


def test_resolve_manifest_version_go_declared_out_of_scope(tmp_path):
    # go.mod has no version field in this ecosystem; the git-tag alternative was investigated
    # live and found unreliable (pdf/go's real tag is unreachable from HEAD) -- declared out of
    # scope rather than risk a misleading value. Must still be an honest, explicit reason, not a
    # crash, even with a real go.mod present.
    clone = tmp_path / "clone"
    clone.mkdir()
    (clone / "go.mod").write_text("module github.com/aspose-pdf-foss/aspose-pdf-foss-for-go\n\ngo 1.24\n", encoding="utf-8")
    result = im.resolve_manifest_version("pdf", "go", clone)
    assert result["version"] is None
    assert "out of scope" in result["reason"]


def test_resolve_manifest_version_missing_clone_cache_directory(tmp_path):
    result = im.resolve_manifest_version("pdf", "net", tmp_path / "no-such-clone")
    assert result["version"] is None
    assert "does not exist" in result["reason"]


def test_resolve_manifest_version_unknown_platform(tmp_path):
    clone = tmp_path / "clone"
    clone.mkdir()
    result = im.resolve_manifest_version("pdf", "cobol", clone)
    assert result["version"] is None
    assert "no manifest-version resolver registered" in result["reason"]


def test_resolve_input_manifest_wires_manifest_version_additively(tmp_path):
    # TC-14: manifest_version is a peer of clone_cache/enterprise_edition_target, additive per
    # this module's own established schema-evolution style.
    repo_root = tmp_path / "repo"
    clone_cache = repo_root / "clone"
    _init_real_git_repo(clone_cache)
    (clone_cache / "pyproject.toml").write_text('[project]\nname = "tex"\nversion = "1.2.3"\n', encoding="utf-8")
    im.configure(repo_root=repo_root)

    manifest = im.resolve_input_manifest("tex", "python", clone_cache)
    assert manifest["manifest_version"] == {
        "version": "1.2.3", "source_path": "pyproject.toml", "source_field": "project.version",
    }


def test_diff_manifests_ignores_manifest_version_drift_by_design(tmp_path):
    # TC-14's own disclosed scope boundary: a package version changing between compose and
    # approve is normal product activity, not the kind of silent-registry-correction incident
    # diff_manifests exists to catch -- must never force a replan on version drift alone.
    pinned = {"clone_cache": {"commit": "abc", "tree": "def"},
              "enterprise_edition_target": {"entry_sha256": "same"},
              "manifest_version": {"version": "26.7.0"}}
    current = {"clone_cache": {"commit": "abc", "tree": "def"},
               "enterprise_edition_target": {"entry_sha256": "same"},
               "manifest_version": {"version": "26.8.0"}}
    assert im.diff_manifests(pinned, current) == []
