def test_preview_writes_svg_when_requested(tmp_path: Path):
    out = tmp_path / "bold-preview.svg"
    result = run("preview", ROBOTO, str(out), "--instance-name", "Bold", "--format", "svg")
    assert result.returncode == 0
    assert out.exists()
    data = out.read_bytes()
    assert data.startswith(b'<?xml version="1.0" encoding="UTF-8"?>')
    assert b"<svg " in data
    assert b"<path d=" in data