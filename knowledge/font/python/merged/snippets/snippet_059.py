def test_preview_writes_png_for_static_variable_font(tmp_path: Path):
    out = tmp_path / "preview.png"
    result = run("preview", ROBOTO, str(out), "--text", "CLI Preview")
    assert result.returncode == 0
    assert out.exists()
    assert out.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert "Saved:" in result.stdout