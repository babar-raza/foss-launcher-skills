def test_text_markup_quadpoints_roundtrip():
    doc, page = _new_page()
    quad = [10, 90, 110, 90, 10, 60, 110, 60]
    for st in ("Highlight", "Underline", "StrikeOut", "Squiggly"):
        page.annotations.add(st, (10, 60, 110, 90), "", properties={"QuadPoints": quad})
    page2 = _roundtrip(doc).pages[0]
    assert [a.subtype for a in page2.annotations] == [
        "Highlight",
        "Underline",
        "StrikeOut",
        "Squiggly",
    ]
    for a in page2.annotations:
        assert a.get_property("QuadPoints") == quad