def test_preview_invalid_axis_exits_1(tmp_path: Path):
    out = tmp_path / "bad-preview.png"
    result = run("preview", ROBOTO, str(out), "--instance", "opsz=12")
    assert result.returncode == 1
    assert "Unknown variable axis" in result.stderr