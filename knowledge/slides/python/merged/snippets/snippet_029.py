def test_a_produced_file_opens_in_an_independent_reader(
    produced, shape_on_blank_slide, python_pptx
):
    """A third-party reader must see the shape and its text.

    python-pptx is deliberately not the library under test: when it and the
    library disagree about what is in the file, the file decides.
    """
    pres, shape = shape_on_blank_slide(with_text="Independent read-back")
    pkg = produced(pres)

    deck = pkg.open_with_python_pptx()
    texts = [
        s.text_frame.text
        for s in deck.slides[0].shapes
        if s.has_text_frame and s.text_frame.text
    ]
    assert "Independent read-back" in texts, texts