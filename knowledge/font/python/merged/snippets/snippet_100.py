def test_var_delta_requires_target():
    result = run(
        "var-delta",
        ROBOTO,
        "--instance-name",
        "Bold",
    )
    assert result.returncode == 1
    assert "requires glyph_id or codepoint" in result.stderr