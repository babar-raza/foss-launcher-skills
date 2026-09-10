def test_annotation_generate_appearance_sets_ap():
    doc = _new_page_doc()
    ann = doc.pages[0].annotations.add(
        "Square", (100, 100, 200, 200), "", properties={"C": [1, 0, 0], "IC": [0, 1, 0]}
    )
    assert not ann.has_appearance
    assert ann.generate_appearance() is True
    assert ann.has_appearance
    assert b"1 0 0 RG" in ann.appearance_normal
    assert b"0 1 0 rg" in ann.appearance_normal