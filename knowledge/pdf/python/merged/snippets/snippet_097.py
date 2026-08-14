def test_markup_subclass_wrapping():
    doc, page = _new_page()
    page.annotations.add("Highlight", (0, 0, 10, 10), "")
    assert isinstance(page.annotations[0], MarkupAnnotation)