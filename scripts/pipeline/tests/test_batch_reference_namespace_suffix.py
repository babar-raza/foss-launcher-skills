"""Regression test for the same-last-dot-segment namespace-suffix fallback
(HARDEN-py-namespace-suffix, MT013, 2026-07-29).

batch_reference.py disambiguates same-name classes across namespaces by
appending the last dot-segment of ``canonical_namespace`` as a slug suffix
(``Aspose.Pdf.Drawing`` -> ``Drawing``). This is deliberately short for
readability and is exercised by
``test_batch_reference.py::TestNameCollisionDedup::test_namespace_disambiguated_slugs``.

That shortcut silently re-collides when two DIFFERENT namespaces share the
same last segment -- found live on pdf/python, where ``aspose_pdf.document``
and ``aspose_pdf.generated.document`` both truncated to ``document``, so the
real, distinct compatibility-shim ``Document`` class was dropped entirely
(0 pages written for either candidate). ``_assign_namespace_slug_suffixes()``
falls back to the full sanitized namespace only for entries whose truncated
suffix is still ambiguous within the group.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import batch_reference as _br
from batch_reference import _assign_namespace_slug_suffixes, _entry_slug

from test_batch_reference import _make_api_surface, run as _run  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_paths(tmp_path):
    _br.configure(repo_root=tmp_path)
    yield
    _br.configure()


def test_helper_falls_back_to_full_namespace_on_shared_last_segment():
    group = [
        {"name": "Document", "canonical_namespace": "aspose_pdf.document"},
        {"name": "Document", "canonical_namespace": "aspose_pdf.generated.document"},
    ]
    _assign_namespace_slug_suffixes(group)
    suffixes = {e["_slug_suffix"] for e in group}
    assert suffixes == {"aspose_pdf.document", "aspose_pdf.generated.document"}


def test_helper_still_prefers_short_suffix_when_unambiguous():
    group = [
        {"name": "Color", "canonical_namespace": "Aspose.Pdf"},
        {"name": "Color", "canonical_namespace": "Aspose.Pdf.Drawing"},
    ]
    _assign_namespace_slug_suffixes(group)
    suffixes = {e["_slug_suffix"] for e in group}
    assert suffixes == {"Pdf", "Drawing"}


def test_helper_skips_entries_without_canonical_namespace():
    group = [
        {"name": "Foo", "canonical_namespace": ""},
        {"name": "Foo", "canonical_namespace": "pkg.foo"},
    ]
    _assign_namespace_slug_suffixes(group)
    assert "_slug_suffix" not in group[0]
    assert group[1]["_slug_suffix"] == "foo"


def test_end_to_end_python_document_collision_generates_both_pages(tmp_path):
    """Full run() integration proof: the pdf/python Document collision that
    used to raise 'within-batch case-collision' (0 pages written) now
    produces two properly-disambiguated pages."""
    entries = [
        {"name": "Document", "kind": "class_definition",
         "file": "document.py", "visibility": "public",
         "canonical_namespace": "aspose_pdf.document",
         "class_import": "aspose_pdf.document.Document",
         "methods": [{"name": "open", "params": [], "return_type": "", "doc": "", "line": 1}],
         "properties": []},
        {"name": "Document", "kind": "class_definition",
         "file": "generated/document.py", "visibility": "public",
         "canonical_namespace": "aspose_pdf.generated.document",
         "class_import": "aspose_pdf.generated.document.Document",
         "methods": [{"name": "save", "params": [], "return_type": "", "doc": "", "line": 1}],
         "properties": []},
    ]
    _make_api_surface(tmp_path, entries, "pdf", "python")
    out_dir = tmp_path / "content" / "reference.aspose.org" / "en" / "pdf" / "python"
    out_dir.mkdir(parents=True)

    result = _run("pdf", "python")

    assert (out_dir / "Document-aspose_pdf_document.md").exists()
    assert (out_dir / "Document-aspose_pdf_generated_document.md").exists()
    assert result["generated"] == 2
