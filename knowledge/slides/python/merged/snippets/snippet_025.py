def test_an_unknown_formatting_property_is_rejected(shape_on_blank_slide):
    """A misspelt or unimplemented property must raise, not vanish.

    Without this, every unimplemented feature in the library fails the same
    silent way, and a user's typo is indistinguishable from a working call.
    """
    pres, shape = shape_on_blank_slide(with_text="Click me")
    try:
        portion_format = shape.text_frame.paragraphs[0].portions[0].portion_format
        with pytest.raises(AttributeError):
            portion_format.definitely_not_a_formatting_property = 1
    finally:
        pres.dispose()