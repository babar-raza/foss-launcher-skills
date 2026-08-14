def test_name_marker_roundtrip_and_equality():
    doc, page = _new_page()
    page.annotations.add(
        "Text",
        (10, 10, 30, 30),
        "note",
        properties={"Name": Name("Comment"), "Open": True},
    )
    a = _roundtrip(doc).pages[0].annotations[0]
    name = a.get_property("Name")
    assert name == "Comment"  # equality with a plain str still holds
    assert isinstance(name, Name)  # but it is still marked as a PDF name
    assert a.get_property("Open") is True