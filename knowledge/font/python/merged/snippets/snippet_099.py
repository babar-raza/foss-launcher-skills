def test_var_delta_supports_composite_glyph():
    result = run(
        "var-delta",
        ROBOTO,
        "--instance-name",
        "Bold",
        "--char",
        "Á",
        "--top-points",
        "2",
    )
    assert result.returncode == 0
    assert "Outline support:   composite outline-derived" in result.stdout
    assert "Components:" in result.stdout
    assert "Component motion:" in result.stdout
    assert "GID " in result.stdout
    assert "local=" in result.stdout
    assert "child glyph delta analysis" in result.stdout