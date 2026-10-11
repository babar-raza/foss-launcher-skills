def test_preview_waterfall_writes_png(tmp_path: Path):
    out = tmp_path / "waterfall.png"
    result = run(
        "preview-waterfall",
        ROBOTO,
        str(out),
        "--instance-name",
        "Bold",
        "--instance-name",
        "Condensed Bold",
        "--include-default",
        "--text",
        "Waterfall QA",
    )
    assert result.returncode == 0
    assert out.exists()
    assert out.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert "Saved:" in result.stdout