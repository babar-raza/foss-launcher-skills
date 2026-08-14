def test_generate_appearance_keeps_existing_unless_forced():
    doc = _new_page_doc()
    ann = doc.pages[0].annotations.add(
        "Square", (0, 0, 50, 50), "x", appearance_normal=b"0 0 50 50 re f\n"
    )
    assert ann.has_appearance
    original = ann.appearance_normal
    # Idempotent: an existing appearance is preserved.
    assert ann.generate_appearance() is True
    assert ann.appearance_normal == original
    # force=True regenerates from the annotation geometry.
    assert ann.generate_appearance(force=True) is True
    assert ann.appearance_normal != original