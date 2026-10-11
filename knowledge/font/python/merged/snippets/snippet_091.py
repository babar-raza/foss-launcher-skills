def test_var_compat_prints_compatibility_summary():
    result = run(
        "var-compat",
        ROBOTO,
        "--before-instance-name",
        "Regular",
        "--after-instance-name",
        "Condensed Bold",
        "--text",
        "Aspose",
    )
    assert result.returncode == 0
    assert "Before:" in result.stdout
    assert "After:" in result.stdout
    assert "Compatible:" in result.stdout
    assert "yes" in result.stdout
    assert "Interpolation diagnostics:" in result.stdout