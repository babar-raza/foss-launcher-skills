def test_meta_clean_writes_cleaned_font(tmp_path: Path):
    from aspose_font.ttf.tables.name import NameRecord

    source = FontLoader.open(ROBOTO)
    assert source.ttf_tables.name is not None
    source.set_table_bytes("DSIG", b"signature")
    source.set_table_bytes("FFTM", b"fontforge")
    source.set_table_bytes("meta", b"metadata")
    source.ttf_tables.name.records.append(
        NameRecord(
            platform_id=1,
            encoding_id=0,
            language_id=0,
            name_id=1,
            value="Roboto Mac",
        )
    )
    dirty = tmp_path / "dirty.ttf"
    dirty.write_bytes(source.to_bytes())

    out = tmp_path / "cleaned.ttf"
    result = run("meta-clean", str(dirty), str(out))

    assert result.returncode == 0
    assert out.exists()
    assert "Saved:" in result.stdout

    cleaned = FontLoader.open(str(out))
    assert "DSIG" not in cleaned.ttf_tables._raw
    assert "FFTM" not in cleaned.ttf_tables._raw
    assert "meta" not in cleaned.ttf_tables._raw
    assert cleaned.ttf_tables.name is not None
    assert all(record.platform_id != 1 for record in cleaned.ttf_tables.name.records)