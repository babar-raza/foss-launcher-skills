"""Direct unit tests for extraction/api_surface.py's RC-W1-004 reachability-tagging
extraction logic (MT026-2026-08-09-BLIND-SPOT-AUDIT-WAVE1, TC-BSA-...-09 / F-18-03).

The evaluator-level tests (scripts/pipeline/tests/content_eval/test_code_reachability.py)
hand-supply the `reachable` field in fixtures and never exercise the code that computes it.
This file closes that gap by testing `_python_top_level_exports` and `_rust_reexported_names`
directly against real filesystem layouts, including the words/python namespace-parent case
that motivated the fallback-subdirectory branch in the first place.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from extraction.api_surface import (  # noqa: E402
    _python_top_level_exports,
    _rust_reexported_names,
    _extract_all_from_init,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# _extract_all_from_init
# ---------------------------------------------------------------------------

def test_extract_all_from_init_simple_list(tmp_path):
    init_py = tmp_path / "__init__.py"
    _write(init_py, "__all__ = ['Document', 'SaveFormat']\n")
    assert _extract_all_from_init(init_py) == {"Document", "SaveFormat"}


def test_extract_all_from_init_tuple(tmp_path):
    init_py = tmp_path / "__init__.py"
    _write(init_py, "__all__ = ('Document', 'SaveFormat')\n")
    assert _extract_all_from_init(init_py) == {"Document", "SaveFormat"}


def test_extract_all_from_init_no_all_returns_none(tmp_path):
    init_py = tmp_path / "__init__.py"
    _write(init_py, "from .document import Document\n")
    assert _extract_all_from_init(init_py) is None


def test_extract_all_from_init_missing_file_returns_none(tmp_path):
    assert _extract_all_from_init(tmp_path / "nonexistent.py") is None


def test_extract_all_from_init_empty_all_returns_empty_set_not_none(tmp_path):
    init_py = tmp_path / "__init__.py"
    _write(init_py, "__all__ = []\n")
    assert _extract_all_from_init(init_py) == set()


# ---------------------------------------------------------------------------
# _python_top_level_exports
# ---------------------------------------------------------------------------

def test_python_exports_simple_top_level_init(tmp_path):
    """The common case: pkg_root/__init__.py declares __all__ directly."""
    pkg_root = tmp_path / "aspose_barcode_foss"
    _write(pkg_root / "__init__.py", "__all__ = ['generate', 'Barcode']\n")
    names, export_root = _python_top_level_exports(pkg_root)
    assert names == {"generate", "Barcode"}
    assert export_root == pkg_root


def test_python_exports_namespace_parent_layout(tmp_path):
    """The real words/python case: pkg_root resolves to an outer empty-__init__.py
    directory, with the actual __all__ one level down in exactly one subpackage."""
    pkg_root = tmp_path / "aspose"
    _write(pkg_root / "__init__.py", "")  # empty, namespace-parent
    _write(pkg_root / "words_foss" / "__init__.py",
           "__all__ = ['Document', 'SaveFormat', 'LoadFormat', 'saving']\n")
    names, export_root = _python_top_level_exports(pkg_root)
    assert names == {"Document", "SaveFormat", "LoadFormat", "saving"}
    assert export_root == pkg_root / "words_foss"


def test_python_exports_no_all_anywhere_returns_none_none(tmp_path):
    """Cannot positively determine -- caller must default reachable=True."""
    pkg_root = tmp_path / "aspose_x"
    _write(pkg_root / "__init__.py", "from .a import A\n")
    names, export_root = _python_top_level_exports(pkg_root)
    assert names is None
    assert export_root is None


def test_python_exports_ambiguous_multiple_subdirs_with_all_returns_none(tmp_path):
    """Two subdirectories both declare __all__ -- ambiguous, must not guess."""
    pkg_root = tmp_path / "aspose"
    _write(pkg_root / "__init__.py", "")
    _write(pkg_root / "pkg_a" / "__init__.py", "__all__ = ['A']\n")
    _write(pkg_root / "pkg_b" / "__init__.py", "__all__ = ['B']\n")
    names, export_root = _python_top_level_exports(pkg_root)
    assert names is None
    assert export_root is None


def test_python_exports_missing_pkg_root_returns_none_none(tmp_path):
    names, export_root = _python_top_level_exports(tmp_path / "does_not_exist")
    assert names is None
    assert export_root is None


def test_python_exports_top_level_all_wins_over_subdirs(tmp_path):
    """When pkg_root's own __init__.py has a usable __all__, that's authoritative --
    subdirectories are never consulted even if present."""
    pkg_root = tmp_path / "aspose_html_foss"
    _write(pkg_root / "__init__.py", "__all__ = ['HTMLDocument']\n")
    _write(pkg_root / "layout" / "__init__.py", "__all__ = ['BoxRoot']\n")
    names, export_root = _python_top_level_exports(pkg_root)
    assert names == {"HTMLDocument"}
    assert export_root == pkg_root


# ---------------------------------------------------------------------------
# _rust_reexported_names
# ---------------------------------------------------------------------------

def test_rust_reexports_brace_form(tmp_path):
    pkg_root = tmp_path / "src"
    _write(pkg_root / "lib.rs", "pub use api::{Workbook, Worksheet, Cell, SaveFormat};\n")
    names = _rust_reexported_names(pkg_root)
    assert names == {"Workbook", "Worksheet", "Cell", "SaveFormat"}


def test_rust_reexports_single_form(tmp_path):
    pkg_root = tmp_path / "src"
    _write(pkg_root / "lib.rs", "pub use api::Workbook;\npub use api::Worksheet;\n")
    names = _rust_reexported_names(pkg_root)
    assert names == {"Workbook", "Worksheet"}


def test_rust_reexports_with_as_alias_keeps_source_name(tmp_path):
    """Struct/enum extraction records the source-side name, so `as Alias` must not
    replace it -- the class was extracted under its real name, not the alias."""
    pkg_root = tmp_path / "src"
    _write(pkg_root / "lib.rs", "pub use api::{WorkbookModel as PublicWorkbook};\n")
    names = _rust_reexported_names(pkg_root)
    assert names == {"WorkbookModel"}


def test_rust_reexports_glob_returns_none_stays_safe(tmp_path):
    """A glob re-export can't be enumerated by this regex-only pass -- must return
    None (unknown), never an empty/wrong set that would mark everything unreachable."""
    pkg_root = tmp_path / "src"
    _write(pkg_root / "lib.rs", "pub use api::*;\n")
    assert _rust_reexported_names(pkg_root) is None


def test_rust_reexports_no_pub_use_returns_none(tmp_path):
    pkg_root = tmp_path / "src"
    _write(pkg_root / "lib.rs", "mod api;\nmod core;\n")
    assert _rust_reexported_names(pkg_root) is None


def test_rust_reexports_missing_lib_rs_returns_none(tmp_path):
    pkg_root = tmp_path / "src"
    pkg_root.mkdir(parents=True)
    assert _rust_reexported_names(pkg_root) is None


def test_rust_reexports_real_cells_rust_shape(tmp_path):
    """Modeled on the real aspose_cells_rust lib.rs shape: private internal mods
    alongside a public api re-export block -- only the re-exported names count."""
    pkg_root = tmp_path / "src"
    _write(pkg_root / "lib.rs", (
        "mod core_color_value;\n"
        "mod display_text_formatter;\n"
        "mod color;\n"
        "pub use color::Color;\n"
        "mod api;\n"
        "pub use api::{Workbook, Worksheet, Cell, Chart, SaveFormat, LoadFormat};\n"
    ))
    names = _rust_reexported_names(pkg_root)
    assert names == {"Color", "Workbook", "Worksheet", "Cell", "Chart", "SaveFormat", "LoadFormat"}
    # The internal-only types (never appearing in any pub use) are correctly absent.
    assert "ColorValue" not in names
    assert "DisplayTextFormatter" not in names


def test_rust_reexports_mixed_glob_and_explicit_exports_stays_safe(tmp_path):
    """The dangerous shape a second independent review found untested: a lib.rs that
    has BOTH a glob re-export (which this regex-only pass cannot enumerate) AND an
    explicit `pub use` block. Without the glob guard, only the explicitly-named items
    would be captured, silently marking everything reached only via the glob as
    unreachable=False -- a false positive that would flag genuinely-public API as
    private. The whole result must stay None (unknown) whenever a glob is present,
    regardless of what else is also re-exported explicitly."""
    pkg_root = tmp_path / "src"
    _write(pkg_root / "lib.rs", (
        "pub use api::*;\n"
        "pub use color::Color;\n"
    ))
    assert _rust_reexported_names(pkg_root) is None
