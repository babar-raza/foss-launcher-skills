def test_generated_appearance_survives_save_load():
    doc = _new_page_doc()
    ann = doc.pages[0].annotations.add(
        "Circle", (100, 100, 200, 160), "", properties={"C": [0, 0, 1]}
    )
    ann.generate_appearance()
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    reopened = Document()
    reopened.load_from(buf)
    assert reopened.pages[0].annotations[0].has_appearance