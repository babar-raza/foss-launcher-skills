def test_clean_for_web_strips_tables_and_mac_names(roboto_path: Path):
    font = _font_with_extra_metadata(roboto_path)

    cleaned = FontCleaner.clean_for_web(font)

    assert cleaned.font_type is FontType.TTF
    assert "DSIG" not in cleaned.ttf_tables._raw
    assert "FFTM" not in cleaned.ttf_tables._raw
    assert "meta" not in cleaned.ttf_tables._raw
    assert cleaned.ttf_tables.name is not None
    assert all(record.platform_id != 1 for record in cleaned.ttf_tables.name.records)