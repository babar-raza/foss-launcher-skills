def test_preview_accepts_symbolic_axis_presets(tmp_path: Path):
    out = tmp_path / "preset-preview.png"
    result = run(
        "preview",
        ROBOTO,
        str(out),
        "--instance",
        "wght=Bold",
        "--instance",
        "wdth=Condensed",
    )
    assert result.returncode == 0
    assert out.exists()
    assert out.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")