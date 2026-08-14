def test_otf_embedded_cff_available(opensans_cff_path: Path):
    otf_data = _wrap_otf_with_cff(opensans_cff_path.read_bytes())
    font = FontLoader.open(otf_data)
    assert isinstance(font, TtfFont)
    assert font.cff_font is not None
    assert isinstance(font.cff_font, CffFont)