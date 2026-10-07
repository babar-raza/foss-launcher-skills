"""HRD-11 (MT076-2026-10-07-PSD-NET-PYTHON-LAUNCH), Layer 1: `validate_scout_output.py` gains a
`check_no_test_entries` helper -- FAIL when any `api_surface.json` entry's `file` is test-like
(the shared predicate from `extraction.tree_helpers._is_non_public_path`). Defense-in-depth: as
of this card, nothing in the live pipeline calls this module (see
`evidence/decisions/hrd-11-01-investigate.md`), so this closes the "logic exists and is unit
tested" requirement without claiming it gates a live run today.
"""
from __future__ import annotations

from extraction.validate_scout_output import check_no_test_entries


def test_fails_on_the_psd_python_polluted_fixture():
    """Reproduces the live, pre-HRD-04 defect shape: 13 test classes in a 77-entry surface."""
    api_surface = (
        [{"name": "PsdImage", "file": "aspose_psd_foss/psdimage.py"}]
        + [
            {"name": f"TestClass{i}", "file": f"aspose_psd_foss_test/thing{i}.py"}
            for i in range(13)
        ]
    )
    result = check_no_test_entries(api_surface)
    assert result["verdict"] == "FAIL"
    assert result["test_like_count"] == 13
    assert "aspose_psd_foss_test/thing0.py" in result["test_like_files"]


def test_passes_on_the_patched_64_entry_surface():
    api_surface = [{"name": "PsdImage", "file": "aspose_psd_foss/psdimage.py"}]
    result = check_no_test_entries(api_surface)
    assert result["verdict"] == "OK"
    assert result["test_like_count"] == 0
    assert result["test_like_files"] == []


def test_real_obj_format_package_does_not_trip_the_check():
    api_surface = [{"name": "ObjExporter", "file": "aspose/threed/formats/obj/ObjExporter.py"}]
    result = check_no_test_entries(api_surface)
    assert result["verdict"] == "OK"


def test_entries_without_a_file_field_are_ignored_not_flagged():
    result = check_no_test_entries([{"name": "NoFile"}])
    assert result["verdict"] == "OK"
    assert result["test_like_count"] == 0


def test_empty_api_surface_is_ok():
    result = check_no_test_entries([])
    assert result["verdict"] == "OK"
    assert result["test_like_count"] == 0
