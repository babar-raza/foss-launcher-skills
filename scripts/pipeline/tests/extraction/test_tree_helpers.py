"""HRD-04 (MT076-2026-10-07-PSD-NET-PYTHON-LAUNCH): test projects named with a `_test`/`.Tests`
suffix must never contribute to a product's public API surface.

Found live on psd/python (Aspose.PSD-FOSS-for-Python): the package directory `aspose_psd_foss` sits beside
`aspose_psd_foss_test`; with no packaging manifest the package root falls back to the repo root, and
`_NON_PUBLIC_DIRS` matched directory names exactly (`tests`, `test`, ...), so 13 test classes entered
api_surface.json (they would have received reference pages) and all 71 snippets were test-derived.

Scope is deliberately narrow: directory-name suffix/prefix rules and pytest's own file conventions only.
A bare `*tests` file-name suffix is NOT adopted (`contests.py`-style false positives).
"""
from __future__ import annotations

import pytest

from extraction.tree_helpers import _collect_source_files, _is_non_public_path


@pytest.mark.parametrize("rel", [
    "aspose_psd_foss_test/psdimagesavetests.py",   # the live psd/python case
    "Aspose.PSD.FOSS.Test/LayerTests.cs",          # .NET test project suffix
    "tests/Aspose.Slides.Foss.Tests/A.cs",         # plural suffix
    "foo-tests/a.py",
    "test_data/sample.py",
    "pkg/test_foo.py",                             # pytest file conventions
    "pkg/foo_test.py",
    "pkg/conftest.py",
    "samples/App/obj/Release/net10.0/App.AssemblyInfo.cs",   # .NET build output
    "aspose_psd_foss/obj/debug/net10_0/aspose_psd_foss_assemblyinfo.py",   # tracked build output (psd/python)
    "src/Lib/bin/Debug/net10.0/Lib.AssemblyAttributes.cs",
])
def test_test_like_paths_are_non_public(tmp_path, rel):
    assert _is_non_public_path(tmp_path / rel, tmp_path) is True


@pytest.mark.parametrize("rel", [
    "aspose_psd_foss/psdimage.py",                 # the real package
    "src/Aspose.PSD.FOSS/Image.cs",
    "latest/a.py",                                 # contains "test" but is not a test directory
    "contest/a.py",
    "attestation/a.py",
    "protest_utils/a.py",
    "testing/a.py",                                # not `test_` / `test-` prefixed
    "pkg/contests.py",                             # bare `tests` file suffix deliberately NOT adopted
    "pkg/latest.py",
    "pkg/psdimagesavetests.py",
    "aspose/threed/formats/obj/ObjExporter.py",    # REAL format package named `obj` (3d/python, 3d/typescript): must stay public
    "src/aspose/threed/formats/obj/ObjImporter.ts",
    "tool/bin/cli.py",                             # `bin` without a debug/release child is not build output
])
def test_negative_controls_stay_public(tmp_path, rel):
    assert _is_non_public_path(tmp_path / rel, tmp_path) is False


@pytest.mark.parametrize("rel", ["tests/a.py", "examples/a.py", "docs/a.py", "scripts/a.py"])
def test_original_exact_directory_rules_still_apply(tmp_path, rel):
    assert _is_non_public_path(tmp_path / rel, tmp_path) is True


def test_collect_source_files_skips_the_manifestless_test_package(tmp_path):
    (tmp_path / "aspose_psd_foss").mkdir()
    (tmp_path / "aspose_psd_foss" / "psdimage.py").write_text("class PsdImage: ...\n", encoding="utf-8")
    (tmp_path / "aspose_psd_foss_test").mkdir()
    (tmp_path / "aspose_psd_foss_test" / "psdimagesavetests.py").write_text("class TestSave: ...\n", encoding="utf-8")
    (tmp_path / "aspose_psd_foss_test" / "helpers.py").write_text("class PsdTestFixtureBase: ...\n", encoding="utf-8")
    names = sorted(p.name for p in _collect_source_files(tmp_path, ".py"))
    assert names == ["psdimage.py"]
