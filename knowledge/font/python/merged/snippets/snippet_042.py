def test_clean_for_web_rejects_non_sfnt_fonts(opensans_cff_path: Path):
    font = FontLoader.open(str(opensans_cff_path))

    with pytest.raises(FontNotSupportedException):
        FontCleaner.clean_for_web(font)