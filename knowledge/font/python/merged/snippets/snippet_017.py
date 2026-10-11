def test_cff_truncated_raises(opensans_cff_path: Path):
    payload = _extract_embedded_cff(opensans_cff_path.read_bytes())
    with pytest.raises(FontParseException):
        FontLoader.open(payload[:40], font_type=FontType.CFF)