def test_cleaned_font_round_trips_without_removed_tables(roboto_path: Path, tmp_path: Path):
    font = _font_with_extra_metadata(roboto_path)
    out_path = tmp_path / "cleaned.ttf"
    out_path.write_bytes(FontCleaner.clean_for_web(font).to_bytes())

    loaded = FontLoader.open(str(out_path))

    assert "DSIG" not in loaded.ttf_tables._raw
    assert "FFTM" not in loaded.ttf_tables._raw
    assert "meta" not in loaded.ttf_tables._raw
    assert loaded.ttf_tables.name is not None
    assert all(record.platform_id != 1 for record in loaded.ttf_tables.name.records)

    with pytest.raises(FontParseException):
        loaded.get_table_bytes("DSIG")