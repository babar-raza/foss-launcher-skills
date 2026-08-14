def test_preview_grid_sheet_accepts_preset_driven_two_axis_grid(tmp_path: Path):
    out = tmp_path / "grid-sheet-presets.png"
    result = run(
        "preview-grid-sheet",
        ROBOTO,
        str(out),
        "--axis",
        "wght",
        "--use-presets",
        "--axis2",
        "wdth",
        "--use-secondary-presets",
    )
    assert result.returncode == 0
    assert out.exists()
    assert out.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")