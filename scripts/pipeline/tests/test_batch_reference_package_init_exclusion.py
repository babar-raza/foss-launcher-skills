"""HRD-9N-14 (MT076-2026-10-07-PSD-NET-PYTHON-LAUNCH): batch_reference.py's H-04e
"conventional class" exclusion must key off genuine PACKAGE-level __all__ curation
(exported_via_package_init=True, set by extraction's _mark_package_init_exports()), not
merely any per-file-local visibility=="exported" entry (api_surface.py's S-1 extraction,
scoped to a single module file). Found live on psd/python: PsdImageLoader's visibility ==
"exported" only because its OWN file (loaders/psdimageloader.py) declares a local
__all__ -- the real top-level aspose_psd_foss/__init__.py is empty, 0 bytes, no __all__ at
all. The old check treated that one per-file marker as proof the whole package curates its
public surface, silently excluding all 18 "conventional" classes with no existing page,
including Layer (the product's central class), Point, and Size.
"""
from __future__ import annotations

from commands.content.batch_reference import _apply_conventional_exclusion


def test_per_file_local_all_does_not_trigger_package_wide_exclusion():
    """Failing-before-fix case: an entry with visibility=="exported" but
    exported_via_package_init unset/None/False must NOT cause conventional classes
    with no existing page to be dropped -- this is psd/python's real shape."""
    candidates = [
        {"name": "PsdImageLoader", "visibility": "exported", "exported_via_package_init": None},
        {"name": "Layer", "visibility": "conventional"},
        {"name": "Point", "visibility": "conventional"},
    ]
    kept, skipped = _apply_conventional_exclusion(candidates, "zzz-nonexistent-family", "zzz-platform")
    assert skipped == 0
    assert {e["name"] for e in kept} == {"PsdImageLoader", "Layer", "Point"}


def test_genuine_package_init_export_still_excludes_unpublished_conventional():
    """Negative control: a REAL package-level __all__ (exported_via_package_init=True)
    must still exclude conventional classes with no existing page -- preserves the
    original intent (and pdf/python's live PdfNumber.md "already published" exception
    path)."""
    candidates = [
        {"name": "Annotation", "visibility": "exported", "exported_via_package_init": True},
        {"name": "InternalHelper", "visibility": "conventional"},
    ]
    kept, skipped = _apply_conventional_exclusion(candidates, "zzz-nonexistent-family", "zzz-platform")
    assert skipped == 1
    assert [e["name"] for e in kept] == ["Annotation"]


def test_no_exports_at_all_is_a_noop():
    candidates = [{"name": "Foo", "visibility": "public"}, {"name": "Bar", "visibility": "conventional"}]
    kept, skipped = _apply_conventional_exclusion(candidates, "zzz-nonexistent-family", "zzz-platform")
    assert skipped == 0
    assert len(kept) == 2


def test_empty_list_is_a_noop():
    kept, skipped = _apply_conventional_exclusion([], "zzz-nonexistent-family", "zzz-platform")
    assert kept == []
    assert skipped == 0
