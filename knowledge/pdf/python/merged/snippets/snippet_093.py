def test_stamp_name_roundtrip():
    doc, page = _new_page()
    page.annotations.add(
        "Stamp", (10, 10, 110, 60), "", properties={"Name": Name("Approved")}
    )
    a = _roundtrip(doc).pages[0].annotations[0]
    assert a.subtype == "Stamp"
    assert a.get_property("Name") == "Approved"