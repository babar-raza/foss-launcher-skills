def test_preview_accepts_instance_name(tmp_path: Path):
    out = tmp_path / "bold-preview.png"
    result = run("preview", ROBOTO, str(out), "--instance-name", "Bold")
    assert result.returncode == 0
    assert out.exists()
    assert out.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")