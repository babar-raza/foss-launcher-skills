def test_glyphs_default_limit():
    result = run("glyphs", ROBOTO)
    assert result.returncode == 0
    lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
    # Header + up to 50 data rows
    assert len(lines) <= 51
    assert len(lines) >= 2  # at least header + 1 glyph