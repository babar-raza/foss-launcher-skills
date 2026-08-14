def test_convert_bad_format(tmp_path: Path):
    out = str(tmp_path / "out.xyz")
    result = run("convert", ROBOTO, out, "--to", "xyz")
    assert result.returncode == 1
    assert result.stderr.strip() != ""