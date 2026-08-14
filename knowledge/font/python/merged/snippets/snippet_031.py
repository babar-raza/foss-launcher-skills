def test_glyph_path_ends_with_closepath(opensans_cff):
    gid = opensans_cff.encoding.unicode_to_gid(0x41)
    glyph = opensans_cff.glyph_accessor.get_glyph_by_id(gid)
    cmds = _commands(glyph.path)
    assert isinstance(cmds[-1], ClosePath)