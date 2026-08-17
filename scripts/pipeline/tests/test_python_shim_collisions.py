"""Tests for _resolve_python_shim_collisions() — dedup of same-name Python
classes caused by an abandoned top-level compatibility shim shadowing a
real submodule implementation, or an unreferenced internal duplicate.

Discovered during the 3d/python MEGA-TRAIN-004 refresh (2026-08-01):
upstream left files like formats/FbxLoadOptions.py (empty placeholder,
class FbxLoadOptions with no bases) alongside the real implementation at
formats/fbx/FbxLoadOptions.py (class FbxLoadOptions(LoadOptions), real
properties) after moving format-specific option classes into per-format
submodules. File-based extraction picks up both as distinct classes;
consolidate_classes() treats differing canonical_namespace values as
genuinely different types and keeps both, which blocks batch_reference's
undisambiguated-collision guard.
"""
from pathlib import Path

from extraction.api_surface import _resolve_python_shim_collisions


def _cls(name, *, bases=None, file, namespace):
    return {
        "name": name,
        "kind": "class_declaration",
        "visibility": "public",
        "file": file,
        "methods": [],
        "properties": [],
        "bases": bases or [],
        "canonical_namespace": namespace,
    }


def _write(root: Path, rel_path: str, content: str) -> Path:
    p = root / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


class TestBaselessShimDiscarded:
    """Signal 1: a class with bases beats a sibling with none, regardless
    of __init__.py import order (the Fbx/Gltf/Obj/Stl/Collada pattern)."""

    def test_shadowed_stub_dropped_when_submodule_has_bases(self, tmp_path):
        _write(
            tmp_path, "aspose/threed/formats/__init__.py",
            "from .fbx.FbxLoadOptions import FbxLoadOptions\n"
            "from .FbxLoadOptions import FbxLoadOptions\n",
        )
        classes = [
            _cls("FbxLoadOptions", bases=[],
                 file="aspose/threed/formats/FbxLoadOptions.py",
                 namespace="threed.formats.FbxLoadOptions"),
            _cls("FbxLoadOptions", bases=["LoadOptions"],
                 file="aspose/threed/formats/fbx/FbxLoadOptions.py",
                 namespace="threed.formats.fbx.FbxLoadOptions"),
        ]
        source_files = [tmp_path / "aspose/threed/formats/__init__.py"]
        result = _resolve_python_shim_collisions(classes, source_files, tmp_path)
        assert len(result) == 1
        assert result[0]["file"] == "aspose/threed/formats/fbx/FbxLoadOptions.py"

    def test_bases_signal_wins_even_when_stub_imported_last(self, tmp_path):
        # Import order deliberately matches real upstream: submodule first,
        # stub second (stub would win Python's actual name binding) — the
        # bases signal must still prefer the real implementation.
        _write(
            tmp_path, "aspose/threed/formats/__init__.py",
            "from .fbx.FbxSaveOptions import FbxSaveOptions\n"
            "from .FbxSaveOptions import FbxSaveOptions\n",
        )
        classes = [
            _cls("FbxSaveOptions", bases=[],
                 file="aspose/threed/formats/FbxSaveOptions.py",
                 namespace="threed.formats.FbxSaveOptions"),
            _cls("FbxSaveOptions", bases=["SaveOptions"],
                 file="aspose/threed/formats/fbx/FbxSaveOptions.py",
                 namespace="threed.formats.fbx.FbxSaveOptions"),
        ]
        source_files = [tmp_path / "aspose/threed/formats/__init__.py"]
        result = _resolve_python_shim_collisions(classes, source_files, tmp_path)
        assert len(result) == 1
        assert result[0]["bases"] == ["SaveOptions"]


class TestReachabilityTiebreak:
    """Signal 2: when bases don't disambiguate, prefer the entry actually
    imported by some __init__.py."""

    def test_unreferenced_duplicate_dropped(self, tmp_path):
        # ArrayListAdapter pattern: utilities/__init__.py imports the class
        # only from ArrayList.py; ArrayListAdapter.py is never referenced.
        _write(
            tmp_path, "aspose/threed/utilities/__init__.py",
            "from .ArrayList import ArrayListAdapter\n",
        )
        classes = [
            _cls("ArrayListAdapter", bases=[],
                 file="aspose/threed/utilities/ArrayList.py",
                 namespace="threed.utilities.ArrayList"),
            _cls("ArrayListAdapter", bases=[],
                 file="aspose/threed/utilities/ArrayListAdapter.py",
                 namespace="threed.utilities.ArrayListAdapter"),
        ]
        source_files = [tmp_path / "aspose/threed/utilities/__init__.py"]
        result = _resolve_python_shim_collisions(classes, source_files, tmp_path)
        assert len(result) == 1
        assert result[0]["file"] == "aspose/threed/utilities/ArrayList.py"

    def test_reachable_top_level_kept_over_unreferenced_submodule(self, tmp_path):
        # ColladaTransformStyle pattern: only the top-level file is ever
        # imported; the collada/ submodule version, despite richer
        # methods/properties, is dead code.
        _write(
            tmp_path, "aspose/threed/formats/__init__.py",
            "from .ColladaTransformStyle import ColladaTransformStyle\n",
        )
        classes = [
            _cls("ColladaTransformStyle", bases=[],
                 file="aspose/threed/formats/ColladaTransformStyle.py",
                 namespace="threed.formats.ColladaTransformStyle"),
            _cls("ColladaTransformStyle", bases=[],
                 file="aspose/threed/formats/collada/ColladaTransformStyle.py",
                 namespace="threed.formats.collada.ColladaTransformStyle"),
        ]
        source_files = [tmp_path / "aspose/threed/formats/__init__.py"]
        result = _resolve_python_shim_collisions(classes, source_files, tmp_path)
        assert len(result) == 1
        assert result[0]["file"] == "aspose/threed/formats/ColladaTransformStyle.py"

    def test_wholly_unreferenced_group_dropped_when_package_is_curated(self, tmp_path):
        # Token/TokenType pattern: fbx/__init__.py is a real, curating
        # __init__.py (imports other classes) but never imports either
        # tokenizer's Token/TokenType -- positive evidence of non-public
        # status, so the whole group is dropped.
        _write(
            tmp_path, "aspose/threed/formats/fbx/__init__.py",
            "from .FbxLoadOptions import FbxLoadOptions\n",
        )
        classes = [
            _cls("Token", bases=[],
                 file="aspose/threed/formats/fbx/binary_tokenizer.py",
                 namespace="threed.formats.fbx.binary_tokenizer"),
            _cls("Token", bases=[],
                 file="aspose/threed/formats/fbx/tokenizer.py",
                 namespace="threed.formats.fbx.tokenizer"),
        ]
        source_files = [tmp_path / "aspose/threed/formats/fbx/__init__.py"]
        result = _resolve_python_shim_collisions(classes, source_files, tmp_path)
        assert result == []

    def test_zero_reachable_left_untouched_without_a_curating_init(self, tmp_path):
        # Same shape as the Token/TokenType case above, but neither
        # candidate's own directory has ANY __init__.py at all -- no
        # evidence either way (the pdf/python Document regression shape:
        # no init to check means no basis for dropping).
        classes = [
            _cls("Widget", bases=[], file="aspose/pkg/a/Widget.py",
                 namespace="pkg.a.Widget"),
            _cls("Widget", bases=[], file="aspose/pkg/b/Widget.py",
                 namespace="pkg.b.Widget"),
        ]
        result = _resolve_python_shim_collisions(classes, [], tmp_path)
        assert len(result) == 2


class TestNoFalsePositives:

    def test_no_duplicates_returns_unchanged(self, tmp_path):
        classes = [
            _cls("Scene", bases=[], file="aspose/threed/Scene.py",
                 namespace="threed.Scene"),
            _cls("Mesh", bases=["Geometry"], file="aspose/threed/entities/Mesh.py",
                 namespace="threed.entities.Mesh"),
        ]
        result = _resolve_python_shim_collisions(classes, [], tmp_path)
        assert result == classes

    def test_ambiguous_collision_left_untouched(self, tmp_path):
        # Both entries reachable, neither has bases -> genuinely
        # unresolvable by either signal; must not guess.
        _write(
            tmp_path, "aspose/pkg/__init__.py",
            "from .a.Widget import Widget\n"
            "from .b.Widget import Widget\n",
        )
        classes = [
            _cls("Widget", bases=[], file="aspose/pkg/a/Widget.py",
                 namespace="pkg.a.Widget"),
            _cls("Widget", bases=[], file="aspose/pkg/b/Widget.py",
                 namespace="pkg.b.Widget"),
        ]
        source_files = [tmp_path / "aspose/pkg/__init__.py"]
        result = _resolve_python_shim_collisions(classes, source_files, tmp_path)
        assert len(result) == 2

    def test_private_init_files_excluded_from_reachability(self, tmp_path):
        # An __init__.py under a single-underscore-prefixed directory is
        # excluded (matches _mark_package_init_exports' own filter) — an
        # import there must not count as public reachability. Only the
        # public-package entry counts, so it alone should survive.
        _write(
            tmp_path, "aspose/pkg/__init__.py",
            "from .a.Widget import Widget\n",
        )
        _write(
            tmp_path, "aspose/pkg/_internal/__init__.py",
            "from .Widget import Widget\n",
        )
        classes = [
            _cls("Widget", bases=[], file="aspose/pkg/a/Widget.py",
                 namespace="pkg.a.Widget"),
            _cls("Widget", bases=[], file="aspose/pkg/_internal/Widget.py",
                 namespace="pkg._internal.Widget"),
        ]
        source_files = [
            tmp_path / "aspose/pkg/__init__.py",
            tmp_path / "aspose/pkg/_internal/__init__.py",
        ]
        result = _resolve_python_shim_collisions(classes, source_files, tmp_path)
        assert len(result) == 1
        assert result[0]["file"] == "aspose/pkg/a/Widget.py"


class TestParenthesizedInitImport:
    """Regex fix: __init__.py imports listed across multiple lines inside
    parens (`from .forms import (\n    Field,\n    ...\n)`) must be
    recognized as reachability evidence just like the single-line form
    (pdf/python, 2026-08-17: UnsignedContentAbsorber's own __init__.py
    export was invisible to the old single-line-only regex, causing a
    real public class to be wrongly treated as an unreferenced dead
    duplicate)."""

    def test_multiline_paren_init_import_grants_reachability(self, tmp_path):
        _write(
            tmp_path, "aspose_pdf/__init__.py",
            "from .forms import (\n"
            "    Field,\n"
            "    UnsignedContent,\n"
            "    UnsignedContentAbsorber,\n"
            ")\n",
        )
        classes = [
            _cls("UnsignedContentAbsorber", bases=[], file="aspose_pdf/forms.py",
                 namespace="aspose_pdf.forms.UnsignedContentAbsorber"),
            _cls("UnsignedContentAbsorber", bases=[], file="aspose_pdf/generated/forms.py",
                 namespace="aspose_pdf.generated.forms.UnsignedContentAbsorber"),
        ]
        source_files = [tmp_path / "aspose_pdf/__init__.py"]
        result = _resolve_python_shim_collisions(classes, source_files, tmp_path)
        assert len(result) == 1
        assert result[0]["file"] == "aspose_pdf/forms.py"


class TestTestFileReachability:
    """New signal: a duplicate is also treated as reachable when the
    package's own test suite imports it directly from its defining
    module, even when no __init__.py re-exports it (Rectangle pattern,
    pdf/python, 2026-08-17) -- must not be lumped in with dead code just
    because nothing curates it at the package-init level."""

    def test_class_reachable_via_test_import_survives_group_drop(self, tmp_path):
        _write(
            tmp_path, "aspose_pdf/__init__.py",
            "from .forms import Field\n",
        )
        _write(
            tmp_path, "tests/test_images.py",
            "from aspose_pdf.images import Rectangle\n",
        )
        classes = [
            _cls("Rectangle", bases=[], file="aspose_pdf/images.py",
                 namespace="aspose_pdf.images.Rectangle"),
            _cls("Rectangle", bases=[], file="aspose_pdf/geometry.py",
                 namespace="aspose_pdf.geometry.Rectangle"),
        ]
        source_files = [
            tmp_path / "aspose_pdf/__init__.py",
            tmp_path / "aspose_pdf/images.py",
            tmp_path / "aspose_pdf/geometry.py",
        ]
        result = _resolve_python_shim_collisions(classes, source_files, tmp_path)
        assert len(result) == 1
        assert result[0]["file"] == "aspose_pdf/images.py"

    def test_class_reachable_via_test_import_parenthesized_form(self, tmp_path):
        _write(
            tmp_path, "aspose_pdf/__init__.py",
            "from .forms import Field\n",
        )
        _write(
            tmp_path, "tests/test_text.py",
            "from aspose_pdf.text import (\n"
            "    TextFragmentCollection,\n"
            ")\n",
        )
        classes = [
            _cls("TextFragmentCollection", bases=[], file="aspose_pdf/text.py",
                 namespace="aspose_pdf.text.TextFragmentCollection"),
            _cls("TextFragmentCollection", bases=[], file="aspose_pdf/collection.py",
                 namespace="aspose_pdf.collection.TextFragmentCollection"),
        ]
        source_files = [
            tmp_path / "aspose_pdf/__init__.py",
            tmp_path / "aspose_pdf/text.py",
            tmp_path / "aspose_pdf/collection.py",
        ]
        result = _resolve_python_shim_collisions(classes, source_files, tmp_path)
        assert len(result) == 1
        assert result[0]["file"] == "aspose_pdf/text.py"

    def test_src_layout_absolute_import_resolves_via_module_index(self, tmp_path):
        # src/-layout package (pdf/python's real shape): the real file is
        # "src/aspose_pdf/images.py" but tests import it as plain
        # "aspose_pdf.images" once "src" is on sys.path -- module_path_index
        # must resolve across that root-prefix difference.
        _write(
            tmp_path, "src/aspose_pdf/__init__.py",
            "from .forms import Field\n",
        )
        _write(
            tmp_path, "tests/test_images.py",
            "from aspose_pdf.images import Rectangle\n",
        )
        classes = [
            _cls("Rectangle", bases=[], file="src/aspose_pdf/images.py",
                 namespace="aspose_pdf.images.Rectangle"),
            _cls("Rectangle", bases=[], file="src/aspose_pdf/geometry.py",
                 namespace="aspose_pdf.geometry.Rectangle"),
        ]
        source_files = [
            tmp_path / "src/aspose_pdf/__init__.py",
            tmp_path / "src/aspose_pdf/images.py",
            tmp_path / "src/aspose_pdf/geometry.py",
        ]
        result = _resolve_python_shim_collisions(classes, source_files, tmp_path)
        assert len(result) == 1
        assert result[0]["file"] == "src/aspose_pdf/images.py"

    def test_tests_dir_present_but_silent_still_drops_group(self, tmp_path):
        # Token/TokenType precedent must survive unaffected by the new
        # test-reachability signal: an unrelated tests/ dir that never
        # mentions these classes must not grant them false reachability.
        _write(
            tmp_path, "aspose/threed/formats/fbx/__init__.py",
            "from .FbxLoadOptions import FbxLoadOptions\n",
        )
        _write(
            tmp_path, "tests/test_something_else.py",
            "from aspose.threed import Scene\n",
        )
        classes = [
            _cls("Token", bases=[],
                 file="aspose/threed/formats/fbx/binary_tokenizer.py",
                 namespace="threed.formats.fbx.binary_tokenizer"),
            _cls("Token", bases=[],
                 file="aspose/threed/formats/fbx/tokenizer.py",
                 namespace="threed.formats.fbx.tokenizer"),
        ]
        source_files = [
            tmp_path / "aspose/threed/formats/fbx/__init__.py",
            tmp_path / "aspose/threed/formats/fbx/binary_tokenizer.py",
            tmp_path / "aspose/threed/formats/fbx/tokenizer.py",
        ]
        result = _resolve_python_shim_collisions(classes, source_files, tmp_path)
        assert result == []
