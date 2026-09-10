def test_stamp_generate_appearance_end_to_end():
    doc = _new_page_doc()
    ann = doc.pages[0].annotations.add(
        "Stamp",
        (100, 100, 260, 150),
        "",
        properties={"Name": AnnotationName("Approved")},
    )
    assert ann.generate_appearance() is True
    assert b"(APPROVED) Tj" in ann.appearance_normal