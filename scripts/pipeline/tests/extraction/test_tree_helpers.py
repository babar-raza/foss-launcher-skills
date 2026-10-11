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

from extraction.tree_helpers import (
    _collect_source_files,
    _is_non_public_path,
    collect_nodes,
    get_parser,
    is_public,
)


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


# ---------------------------------------------------------------------------
# TC-PSD-HRD-9N-11 — is_public() for Python only special-cased __init__ as
# public; every OTHER dunder method (__eq__, __ne__, __hash__, __str__,
# __repr__, __copy__, ...) starts with "_" too, so the original
# `return not name.startswith("_")` fallback silently classified all of
# them as private, even though they are genuinely public, callable,
# documented Python protocol methods (e.g. `point1 == point2` calls the
# public __eq__ method, not an internal helper).
#
# Found live on psd/python's Point/Rectangle/RectangleF/Size classes: 18
# real dunder protocol methods invisible to api_surface.json, only
# __init__ (4, one per class) ever extracted. Not psd-specific --
# is_public() is the single, shared Python visibility gate for the whole
# pipeline; any Python FOSS product implementing __eq__/__hash__/__str__/
# __repr__/etc. for real protocol behavior has the same gap.
# ---------------------------------------------------------------------------

def _first_python_function(code: str):
    parser = get_parser("python")
    root = parser.parse(code.encode("utf-8")).root_node
    funcs = collect_nodes(root, {"function_definition"})
    assert funcs, "no function_definition node found in test fixture"
    return funcs[0]


@pytest.mark.parametrize("dunder", [
    "__eq__", "__ne__", "__hash__", "__str__", "__repr__", "__copy__",
    "__len__", "__iter__", "__enter__", "__exit__", "__call__", "__add__",
])
def test_python_dunder_protocol_methods_are_public(dunder):
    """Every real dunder protocol method must be recognized as public --
    this is the exact live regression found on psd/python's Point/
    Rectangle/RectangleF/Size classes (18 real occurrences across
    __eq__/__ne__/__hash__/__str__/__repr__/__copy__)."""
    code = f"class Foo:\n    def {dunder}(self):\n        pass\n"
    node = _first_python_function(code)
    assert is_public(node, "python") is True, (
        f"{dunder} is a real Python protocol method and must be public, "
        f"not silently hidden from api_surface.json"
    )


def test_python_init_still_public():
    """Negative control: the ORIGINAL, already-working __init__ case must
    keep working (it's now just one instance of the general dunder rule,
    not a hardcoded special case)."""
    code = "class Foo:\n    def __init__(self):\n        pass\n"
    node = _first_python_function(code)
    assert is_public(node, "python") is True


def test_python_single_underscore_still_private():
    """Negative control: a genuinely private, single-underscore-prefixed
    method must stay private."""
    code = "class Foo:\n    def _helper(self):\n        pass\n"
    node = _first_python_function(code)
    assert is_public(node, "python") is False


def test_python_name_mangled_double_underscore_still_private():
    """Negative control: a name-mangled attribute (leading __, NO
    trailing __ -- Python mangles self.__secret to
    self._ClassName__secret) is genuinely private, unlike a real dunder
    (leading AND trailing __). Must not be swept up by a loose "starts
    with __" check."""
    code = "class Foo:\n    def __secret(self):\n        pass\n"
    node = _first_python_function(code)
    assert is_public(node, "python") is False


def test_python_plain_public_method_unaffected():
    """Negative control: an ordinary public method (no leading
    underscore at all) must be unaffected by this fix."""
    code = "class Foo:\n    def do_thing(self):\n        pass\n"
    node = _first_python_function(code)
    assert is_public(node, "python") is True
