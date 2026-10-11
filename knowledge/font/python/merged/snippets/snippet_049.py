def test_info_nonexistent_exits_1():
    result = run("info", "/nonexistent_font_file.ttf")
    assert result.returncode == 1
    assert result.stderr.strip() != ""