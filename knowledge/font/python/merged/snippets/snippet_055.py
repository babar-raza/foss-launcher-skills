def test_metrics_output():
    result = run("metrics", ROBOTO)
    assert result.returncode == 0
    out = result.stdout
    assert "units_per_em:" in out
    assert "ascender:" in out
    assert "descender:" in out