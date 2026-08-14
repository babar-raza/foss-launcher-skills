def test_glyph_path_has_curveto(opensans_cff):
    gid = opensans_cff.encoding.unicode_to_gid(0x41)
    glyph = opensans_cff.glyph_accessor.get_glyph_by_id(gid)
    assert glyph.path is not None
    cmds = _commands(glyph.path)
    assert any(isinstance(c, MoveTo) for c in cmds)
    assert any(isinstance(c, CurveTo) for c in cmds)