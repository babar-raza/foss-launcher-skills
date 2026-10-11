def test_preview_animation_writes_apng(tmp_path: Path):
    out = tmp_path / "animation.png"
    result = run(
        "preview-animation",
        ROBOTO,
        str(out),
        "--axis",
        "wdth",
        "--start",
        "75",
        "--end",
        "100",
        "--frames",
        "4",
        "--preset",
        "draft",
        "--easing",
        "ease-out",
        "--caption-mode",
        "coordinates",
        "--text",
        "Anim",
    )
    assert result.returncode == 0
    assert out.exists()
    data = out.read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    assert b"acTL" in data
    assert "Saved:" in result.stdout