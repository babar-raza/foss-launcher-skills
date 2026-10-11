def test_preview_compare_includes_diff_panel_colors(tmp_path: Path):
    out = tmp_path / "compare-sheet.png"
    result = run(
        "preview-compare",
        ROBOTO,
        str(out),
        "--before-instance-name",
        "Regular",
        "--after-instance-name",
        "Condensed Bold",
    )
    assert result.returncode == 0
    _width, _height, pixels = _decode_png_rgb(out.read_bytes())
    triplets = {
        tuple(pixels[index:index + 3])
        for index in range(0, len(pixels), 3)
    }
    assert (198, 109, 42) in triplets
    assert (71, 126, 199) in triplets
    assert (126, 94, 156) in triplets