def test_preview_grid_accepts_primary_axis_presets(tmp_path: Path):
    out_dir = tmp_path / "preview-grid-presets"
    result = run(
        "preview-grid",
        ROBOTO,
        str(out_dir),
        "--axis",
        "wght",
        "--use-presets",
    )
    assert result.returncode == 0
    files = sorted(path.name for path in out_dir.glob("*.png"))
    assert len(files) == 9
    assert "roboto-instance-bold.png" in files