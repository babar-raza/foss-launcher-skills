def test_convert_ttf_to_woff(tmp_path: Path):
    out = str(tmp_path / "out.woff")
    result = run("convert", ROBOTO, out, "--to", "woff")
    assert result.returncode == 0
    assert "Saved:" in result.stdout
    assert Path(out).exists()
    assert Path(out).stat().st_size > 0