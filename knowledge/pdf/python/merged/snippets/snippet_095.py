def test_caret_generate_appearance_end_to_end():
    doc = _new_page_doc()
    ann = doc.pages[0].annotations.add("Caret", (100, 100, 120, 120), "")
    assert ann.generate_appearance() is True
    assert b"\nf\n" in ann.appearance_normal