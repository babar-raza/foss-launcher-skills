def test_convert_ttf_to_eot(tmp_path: Path):
    out = str(tmp_path / "out.eot")
    result = run("convert", ROBOTO, out, "--to", "eot")
    assert result.returncode == 0
    assert Path(out).exists()
    loaded = FontLoader.open(out)
    assert isinstance(loaded, EotFont)