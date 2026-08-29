def test_agl_named_glyphs() -> None:
    assert glyph_name_to_unicode("aacute") == "á"
    assert glyph_name_to_unicode("Euro") == "€"
    assert glyph_name_to_unicode("afii10017") == "А"  # Cyrillic A
    assert glyph_name_to_unicode("bullet") == "•"
    assert glyph_name_to_unicode("Lcommaaccent") == "Ļ"