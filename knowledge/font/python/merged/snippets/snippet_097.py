def test_var_delta_prints_active_tuple_summary():
    result = run(
        "var-delta",
        ROBOTO,
        "--instance-name",
        "Bold",
        "--char",
        "A",
        "--top-points",
        "2",
    )
    assert result.returncode == 0
    assert "Glyph:" in result.stdout
    assert "Instance:" in result.stdout
    assert "Active tuples:" in result.stdout
    assert "Strongest points:" in result.stdout
    assert "outline=" in result.stdout
    assert "phantom=" in result.stdout
    assert "Tuple #" in result.stdout