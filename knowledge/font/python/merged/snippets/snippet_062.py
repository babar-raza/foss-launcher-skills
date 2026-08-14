def test_preview_animation_path_writes_apng(tmp_path: Path):
    out = tmp_path / "animation-path.png"
    result = run(
        "preview-animation-path",
        ROBOTO,
        str(out),
        "--state",
        "Regular",
        "--state",
        "wght=700,wdth=75",
        "--state",
        "Bold",
        "--frames-per-segment",
        "3",
        "--preset",
        "draft",
        "--easing",
        "ease-in-out",
        "--caption-mode",
        "both",
        "--text",
        "Anim Path",
    )
    assert result.returncode == 0
    assert out.exists()
    data = out.read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    assert b"acTL" in data