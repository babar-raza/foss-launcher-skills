"""Tests for extraction/api_surface.py's _mark_package_init_exports -- PY-INIT-002
(MT028-2026-08-09-FONT-PYTHON-BLIND-SPOT-HEAL, RC-font-python-02).

Regression coverage for a real, live-verified defect found by S-122 blind-spot-audit: an
__all__ entry with no corresponding import statement (a genuine upstream package bug --
confirmed live against aspose-font-foss-for-python's BinaryReader/BinaryWriter, which are
listed in __all__ but never actually bound in the module namespace, so
`from aspose_font import BinaryReader` really does raise ImportError) must NOT be treated
as a legitimate re-export.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from extraction.api_surface import _mark_package_init_exports  # noqa: E402


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_all_entry_with_no_import_is_not_marked_exported(tmp_path):
    """The exact bug this fix closes: __all__ lists a name with zero corresponding
    import -- must NOT be marked exported_via_package_init."""
    init_py = tmp_path / "__init__.py"
    _write(init_py, "__all__ = ['BinaryReader']\n")  # no import at all
    classes = [{"name": "BinaryReader", "file": "pkg/_io.py"}]

    _mark_package_init_exports(classes, [init_py])

    assert "exported_via_package_init" not in classes[0]


def test_all_entry_with_real_import_is_marked_exported(tmp_path):
    """The legitimate case this function exists for: a class defined in a private
    submodule, genuinely imported and re-exported via __init__.py's __all__."""
    init_py = tmp_path / "__init__.py"
    _write(init_py, "from pkg._internal.loader import FontLoader\n__all__ = ['FontLoader']\n")
    classes = [{"name": "FontLoader", "file": "pkg/_internal/loader.py"}]

    _mark_package_init_exports(classes, [init_py])

    assert classes[0]["exported_via_package_init"] is True


def test_aliased_import_is_recognized_by_its_bound_name(tmp_path):
    init_py = tmp_path / "__init__.py"
    _write(init_py, "from pkg._impl import RealName as PublicName\n__all__ = ['PublicName']\n")
    classes = [{"name": "PublicName", "file": "pkg/_impl.py"}]

    _mark_package_init_exports(classes, [init_py])

    assert classes[0]["exported_via_package_init"] is True


def test_class_defined_directly_in_init_and_listed_in_all_is_recognized(tmp_path):
    init_py = tmp_path / "__init__.py"
    _write(init_py, "class LocalThing:\n    pass\n__all__ = ['LocalThing']\n")
    classes = [{"name": "LocalThing", "file": "pkg/__init__.py"}]

    _mark_package_init_exports(classes, [init_py])

    assert classes[0]["exported_via_package_init"] is True


def test_multiline_parenthesized_import_is_handled(tmp_path):
    init_py = tmp_path / "__init__.py"
    _write(
        init_py,
        "from pkg._types import (\n    TypeA,\n    TypeB,\n)\n__all__ = ['TypeA', 'TypeB']\n",
    )
    classes = [{"name": "TypeA", "file": "x.py"}, {"name": "TypeB", "file": "x.py"}]

    _mark_package_init_exports(classes, [init_py])

    assert classes[0]["exported_via_package_init"] is True
    assert classes[1]["exported_via_package_init"] is True


def test_partial_all_list_only_marks_the_actually_bound_names(tmp_path):
    """A mix of one real re-export and one bug-class entry in the same __all__ --
    only the genuinely-bound name is marked, proving this isn't an all-or-nothing
    per-file decision."""
    init_py = tmp_path / "__init__.py"
    _write(init_py, "from pkg._io import BinaryWriter\n__all__ = ['BinaryWriter', 'BinaryReader']\n")
    classes = [
        {"name": "BinaryWriter", "file": "pkg/_io.py"},
        {"name": "BinaryReader", "file": "pkg/_io.py"},
    ]

    _mark_package_init_exports(classes, [init_py])

    assert classes[0]["exported_via_package_init"] is True
    assert "exported_via_package_init" not in classes[1]


def test_syntax_error_in_init_py_contributes_nothing_and_does_not_raise(tmp_path):
    init_py = tmp_path / "__init__.py"
    _write(init_py, "def broken(:\n    __all__ = ['Whatever']\n")
    classes = [{"name": "Whatever", "file": "x.py"}]

    _mark_package_init_exports(classes, [init_py])  # must not raise

    assert "exported_via_package_init" not in classes[0]


def test_private_subtree_init_py_is_still_excluded(tmp_path):
    """Pre-existing behavior (not touched by this fix) must still hold: an __init__.py
    inside a private (_-prefixed) directory is never consulted."""
    init_py = tmp_path / "_internal" / "__init__.py"
    _write(init_py, "from pkg._internal._x import Secret\n__all__ = ['Secret']\n")
    classes = [{"name": "Secret", "file": "pkg/_internal/_x.py"}]

    _mark_package_init_exports(classes, [init_py])

    assert "exported_via_package_init" not in classes[0]


def test_no_all_list_at_all_contributes_nothing(tmp_path):
    init_py = tmp_path / "__init__.py"
    _write(init_py, "from pkg._x import Thing\n")  # imported but never listed in __all__
    classes = [{"name": "Thing", "file": "pkg/_x.py"}]

    _mark_package_init_exports(classes, [init_py])

    assert "exported_via_package_init" not in classes[0]


def test_top_level_reexport_gets_empty_public_import_module(tmp_path):
    """PY-INIT-003: a class re-exported by the package ROOT __init__.py is
    importable as `from {package} import {name}` -- public_import_module must
    be the empty string, not omitted, so a consumer can distinguish "resolved,
    at the root" from "not resolved at all"."""
    init_py = tmp_path / "__init__.py"
    _write(init_py, "from pkg._internal.loader import FontLoader\n__all__ = ['FontLoader']\n")
    classes = [{"name": "FontLoader", "file": "pkg/_internal/loader.py"}]

    _mark_package_init_exports(classes, [init_py], pkg_root=tmp_path)

    assert classes[0]["exported_via_package_init"] is True
    assert classes[0]["public_import_module"] == ""


def test_subpackage_reexport_gets_its_own_module_path(tmp_path):
    """The exact real-world bug this closes: CffCharset is defined in
    aspose_font/cff/charset.py and re-exported by aspose_font/cff/__init__.py
    (`from aspose_font.cff import CffCharset` -- live-verified), but NOT by the
    top-level aspose_font/__init__.py (`from aspose_font import CffCharset`
    raises ImportError, live-verified). class_import ("cff.charset.CffCharset")
    names the DEFINING module, which is a different fact from the re-exporting
    one and must not be conflated with it."""
    top_init = tmp_path / "__init__.py"
    _write(top_init, "from pkg.cff.font import CffFont\n__all__ = ['CffFont']\n")
    sub_init = tmp_path / "cff" / "__init__.py"
    _write(sub_init, "from pkg.cff.charset import CffCharset\n__all__ = ['CffCharset']\n")
    classes = [
        {"name": "CffFont", "file": "pkg/cff/font.py"},
        {"name": "CffCharset", "file": "pkg/cff/charset.py"},
    ]

    _mark_package_init_exports(classes, [top_init, sub_init], pkg_root=tmp_path)

    assert classes[0]["public_import_module"] == ""
    assert classes[1]["public_import_module"] == "cff"


def test_shallowest_reexport_wins_when_both_levels_export_the_same_name(tmp_path):
    top_init = tmp_path / "__init__.py"
    _write(top_init, "from pkg.cff.charset import CffCharset\n__all__ = ['CffCharset']\n")
    sub_init = tmp_path / "cff" / "__init__.py"
    _write(sub_init, "from pkg.cff.charset import CffCharset\n__all__ = ['CffCharset']\n")
    classes = [{"name": "CffCharset", "file": "pkg/cff/charset.py"}]

    _mark_package_init_exports(classes, [sub_init, top_init], pkg_root=tmp_path)

    assert classes[0]["public_import_module"] == ""


def test_no_pkg_root_omits_public_import_module_but_keeps_boolean(tmp_path):
    """Backward compatibility: callers that don't pass pkg_root (or old test
    fixtures) still get the boolean flag with no new field forced onto them."""
    init_py = tmp_path / "__init__.py"
    _write(init_py, "from pkg._internal.loader import FontLoader\n__all__ = ['FontLoader']\n")
    classes = [{"name": "FontLoader", "file": "pkg/_internal/loader.py"}]

    _mark_package_init_exports(classes, [init_py])

    assert classes[0]["exported_via_package_init"] is True
    assert "public_import_module" not in classes[0]
