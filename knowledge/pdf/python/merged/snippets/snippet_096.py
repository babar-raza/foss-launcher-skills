def test_generate_appearance_unsupported_subtype_returns_false():
    doc = _new_page_doc()
    ann = doc.pages[0].annotations.add("Sound", (0, 0, 20, 20), "note")
    assert ann.generate_appearance() is False
    assert not ann.has_appearance