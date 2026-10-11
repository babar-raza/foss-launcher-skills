def test_glyph_width_positive(opensans_cff):
    gid = opensans_cff.encoding.unicode_to_gid(0x41)
    glyph = opensans_cff.glyph_accessor.get_glyph_by_id(gid)
    assert glyph.advance_width > 0