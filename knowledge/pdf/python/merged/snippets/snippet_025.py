def test_agl_algorithmic_uni_forms() -> None:
    assert glyph_name_to_unicode("uni0041") == "A"
    assert glyph_name_to_unicode("uni00410042") == "AB"
    assert glyph_name_to_unicode("u1F600") == "\U0001f600"