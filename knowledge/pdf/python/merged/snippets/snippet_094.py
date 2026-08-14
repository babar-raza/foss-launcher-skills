def test_every_known_subtype_roundtrips(subtype):
    doc, page = _new_page()
    page.annotations.add(
        subtype, (5, 5, 55, 55), f"c-{subtype}", properties={"NM": f"id-{subtype}"}
    )
    a = _roundtrip(doc).pages[0].annotations[0]
    assert a.subtype == subtype
    assert a.contents == f"c-{subtype}"
    assert a.get_property("NM") == f"id-{subtype}"