"""HARDEN-py-canonical-namespace (MT013): Python class entries must populate
canonical_namespace from their module path.

Found live while launching pdf/python: two genuinely distinct classes both
named `Document` exist -- the primary implementation
(`aspose_pdf/document.py`, 35 methods) and a separate, real compatibility-
shim class (`aspose_pdf/generated/document.py`, 16 methods, its own
docstring: "Compatibility Document mirroring a subset of the Aspose.PDF
API"). The same-name disambiguation mechanism in batch_reference.py /
api_completeness.py (already proven working for C++ and Rust) resolves
collisions using `canonical_namespace` -- but the Python branch of
api_surface.py's class-import derivation computed the module path only for
`class_import`, never exposing it as `canonical_namespace`. Without it,
BOTH `Document` classes (and `Rectangle`, `Decoder`, `PageCollection`, and
others sharing a name across modules) failed page generation entirely.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from extraction.api_surface import extract_api_surface
from extraction.tree_helpers import get_parser

_DOCUMENT_SOURCE = """
class Document:
    def __init__(self):
        pass

    def save(self, path: str) -> None:
        pass
"""

_GENERATED_DOCUMENT_SOURCE = """
class Document:
    \"\"\"Compatibility Document mirroring a subset of the Aspose.PDF API.\"\"\"

    def __init__(self):
        pass

    def load_from(self, path: str) -> "Document":
        pass
"""


@pytest.fixture
def two_document_classes(tmp_path):
    pkg_root = tmp_path / "aspose_pdf"
    pkg_root.mkdir()
    (pkg_root / "document.py").write_text(_DOCUMENT_SOURCE, encoding="utf-8")
    generated_dir = pkg_root / "generated"
    generated_dir.mkdir()
    (generated_dir / "document.py").write_text(_GENERATED_DOCUMENT_SOURCE, encoding="utf-8")
    return tmp_path, pkg_root


class TestPythonCanonicalNamespace:
    def test_canonical_namespace_derived_from_module_path(self, two_document_classes):
        repo, pkg_root = two_document_classes
        parser = get_parser("python")
        classes, _claims, *_ = extract_api_surface(
            parser, "python", pkg_root, repo, "pdf",
        )
        by_file = {c["file"]: c for c in classes if c["name"] == "Document"}
        assert len(by_file) == 2

        primary = next(c for c in by_file.values() if c["file"].endswith("document.py")
                        and "generated" not in c["file"])
        generated = next(c for c in by_file.values() if "generated" in c["file"])

        assert primary["canonical_namespace"] == "document"
        assert generated["canonical_namespace"] == "generated.document"
        # The two distinct classes must now have DIFFERENT canonical_namespace
        # values, which is what lets batch_reference.py's disambiguation
        # mechanism generate two separate, correctly-scoped pages instead of
        # failing both with a same-name collision.
        assert primary["canonical_namespace"] != generated["canonical_namespace"]

    def test_init_py_class_namespace_drops_init_segment(self, tmp_path):
        pkg_root = tmp_path / "aspose_pdf"
        data_dir = pkg_root / "engine" / "data"
        data_dir.mkdir(parents=True)
        (data_dir / "__init__.py").write_text(
            "class PdfNull:\n    def __init__(self):\n        pass\n",
            encoding="utf-8",
        )
        parser = get_parser("python")
        classes, _claims, *_ = extract_api_surface(
            parser, "python", pkg_root, tmp_path, "pdf",
        )
        entry = next(c for c in classes if c["name"] == "PdfNull")
        assert entry["canonical_namespace"] == "engine.data"
