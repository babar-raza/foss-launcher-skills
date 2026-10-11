"""HRD-11 (MT076-2026-10-07-PSD-NET-PYTHON-LAUNCH), Layer 2: `batch_reference.py` must refuse
to write a reference page whose source `file` is test-like (the same shared predicate HRD-04
landed in `extraction.tree_helpers._is_non_public_path`), with a named, printed reason -- never
a silent drop. Mirrors the existing H-04d internal/vendor-class exclusion
(`_apply_kind_filter`'s neighbor filter at the call site), as a standalone, independently
testable function rather than inline code in `run()`.
"""
from __future__ import annotations

from commands.content.batch_reference import _exclude_test_like_entries


def test_test_like_entries_are_excluded():
    entries = [
        {"name": "PsdImage", "file": "aspose_psd_foss/psdimage.py"},
        {"name": "TestSave", "file": "aspose_psd_foss_test/psdimagesavetests.py"},
        {"name": "PsdTestFixtureBase", "file": "aspose_psd_foss_test/helpers.py"},
    ]
    kept, skipped = _exclude_test_like_entries(entries)
    assert [e["name"] for e in kept] == ["PsdImage"]
    assert skipped == 2


def test_real_obj_format_package_is_not_excluded():
    """Negative control: 3d/python's real formats/obj/ package must survive (HRD-04's
    build-output rule only excludes obj|bin immediately followed by debug|release)."""
    entries = [{"name": "ObjExporter", "file": "aspose/threed/formats/obj/ObjExporter.py"}]
    kept, skipped = _exclude_test_like_entries(entries)
    assert [e["name"] for e in kept] == ["ObjExporter"]
    assert skipped == 0


def test_entry_with_no_file_field_is_kept():
    """Entries that never carried a `file` field (older scout output / synthetic entries)
    must not be dropped by a filter that is additive, not a new hard requirement."""
    entries = [{"name": "NoFileEntry"}]
    kept, skipped = _exclude_test_like_entries(entries)
    assert [e["name"] for e in kept] == ["NoFileEntry"]
    assert skipped == 0


def test_empty_list_is_a_noop():
    kept, skipped = _exclude_test_like_entries([])
    assert kept == []
    assert skipped == 0
