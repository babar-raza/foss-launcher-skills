def test_curveto_has_three_points(opensans_cff):
    gid = opensans_cff.encoding.unicode_to_gid(0x41)
    glyph = opensans_cff.glyph_accessor.get_glyph_by_id(gid)
    for cmd in _commands(glyph.path):
        if isinstance(cmd, CurveTo):
            assert isinstance(cmd.x1, float)
            assert isinstance(cmd.y1, float)
            assert isinstance(cmd.x2, float)
            assert isinstance(cmd.y2, float)
            assert isinstance(cmd.x, float)
            assert isinstance(cmd.y, float)