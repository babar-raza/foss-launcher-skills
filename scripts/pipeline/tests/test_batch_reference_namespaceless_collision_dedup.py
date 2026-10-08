"""HRD-9N-14 (MT076-2026-10-07-PSD-NET-PYTHON-LAUNCH): when 2+ same-name candidates have
no distinguishing effective namespace, _assign_namespace_slug_suffixes cannot tell them
apart and they'd otherwise collide on the same output filename (an arbitrary
processing-order "WITHIN-BATCH-DEDUP" skip could then keep the wrong, lower-visibility
entry). _dedup_namespaceless_name_collisions() keeps only the highest-visibility-rank
entry in that case, mirroring the dedup-by-visibility-rank logic
lib/denominator_reconciler.py already applies for its own M==N scope count.
"""
from __future__ import annotations

from commands.content.batch_reference import _dedup_namespaceless_name_collisions


def test_namespaceless_duplicate_keeps_highest_visibility():
    candidates = [
        {"name": "Document", "file": "internal/model.py", "visibility": "conventional"},
        {"name": "Document", "file": "document.py", "visibility": "exported"},
    ]
    kept, dropped = _dedup_namespaceless_name_collisions(candidates)
    assert dropped == 1
    assert len(kept) == 1
    assert kept[0]["visibility"] == "exported"


def test_entries_with_distinguishing_namespace_are_left_untouched():
    """Real different-namespace collisions (Point in Drawing vs. Point in Geometry)
    must not be deduped away -- they are genuinely distinct classes."""
    candidates = [
        {"name": "Point", "class_import": "aspose.drawing.Point", "visibility": "public"},
        {"name": "Point", "class_import": "aspose.geometry.Point", "visibility": "public"},
    ]
    kept, dropped = _dedup_namespaceless_name_collisions(candidates)
    assert dropped == 0
    assert len(kept) == 2


def test_no_collision_is_a_noop():
    candidates = [{"name": "Alpha", "visibility": "public"}, {"name": "Beta", "visibility": "conventional"}]
    kept, dropped = _dedup_namespaceless_name_collisions(candidates)
    assert dropped == 0
    assert kept == candidates


def test_empty_list_is_a_noop():
    kept, dropped = _dedup_namespaceless_name_collisions([])
    assert kept == []
    assert dropped == 0
