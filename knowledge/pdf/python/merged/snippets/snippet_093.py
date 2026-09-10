def test_freetext_generate_appearance_registers_font_resource():
    doc = _new_page_doc()
    ann = doc.pages[0].annotations.add(
        "FreeText",
        (100, 100, 300, 160),
        "hello from a free text box",
        properties={"DA": "/Helv 12 Tf 0 g"},
    )
    assert ann.generate_appearance() is True
    assert b"/Helv 12 Tf" in ann.appearance_normal
    # The generated form XObject carries the /Helv font in its /Resources.
    engine = doc._engine_pdf
    annot = engine.get_annotations(0)[0]
    assert annot["has_AP"] is True
    assert b"Tj" in annot["AP_N"]