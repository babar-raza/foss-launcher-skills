def test_agl_unresolved_and_bad_input() -> None:
    assert glyph_name_to_unicode(".notdef") is None
    assert glyph_name_to_unicode("nonexistentglyphname") is None
    assert glyph_name_to_unicode("") is None
    assert glyph_name_to_unicode("x" * 200) is None  # bounded name length
    assert glyph_name_to_unicode("uniD800") is None  # surrogate rejected