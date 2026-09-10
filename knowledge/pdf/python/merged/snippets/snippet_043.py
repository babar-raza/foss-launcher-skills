def test_cff_predefined_charsets() -> None:
    expert, subset = cff_predefined_charset(1), cff_predefined_charset(2)
    assert len(expert) == 166 and len(subset) == 87
    assert expert[0] == ".notdef" and expert[2] == "exclamsmall"
    assert subset[0] == ".notdef"
    # 0 is ISOAdobe, which needs no table (glyph id is the SID); 3+ do not exist.
    assert cff_predefined_charset(0) is None
    assert cff_predefined_charset(3) is None