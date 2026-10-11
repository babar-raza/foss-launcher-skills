def test_version():
    result = run("--version")
    assert result.returncode == 0
    assert "aspose-font" in result.stdout
    assert "1.0.0" in result.stdout