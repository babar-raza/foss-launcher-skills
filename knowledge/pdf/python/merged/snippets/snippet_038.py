def test_agl_ligature_and_variant_components() -> None:
    assert glyph_name_to_unicode("f_f_i") == "ffi"
    assert glyph_name_to_unicode("A.sc") == "A"
    assert glyph_name_to_unicode("fi") == "ﬁ"  # a real AGL ligature name