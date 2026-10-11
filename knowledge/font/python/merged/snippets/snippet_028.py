def test_notdef_glyph_cff(opensans_cff):
    glyph = opensans_cff.glyph_accessor.get_glyph_by_id(GlyphId(0))
    assert glyph.glyph_id == GlyphId(0)