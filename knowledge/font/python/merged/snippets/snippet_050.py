def test_glyphs_limit():
    result = run("glyphs", ROBOTO, "--limit", "5")
    assert result.returncode == 0
    lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
    # Header + 5 data rows
    assert len(lines) == 6