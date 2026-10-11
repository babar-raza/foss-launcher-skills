def test_info_prints_metadata():
    result = run("info", ROBOTO)
    assert result.returncode == 0
    out = result.stdout
    assert "TTF" in out
    assert "Roboto" in out
    assert "Glyphs:" in out
    assert "Units/EM:" in out