def test_preview_grid_writes_axis_sweep_pngs(tmp_path: Path):
    out_dir = tmp_path / "preview-grid"
    result = run(
        "preview-grid",
        ROBOTO,
        str(out_dir),
        "--axis",
        "wght",
        "--value",
        "400",
        "--value",
        "700",
        "--axis2",
        "wdth",
        "--value2",
        "75",
        "--value2",
        "100",
    )
    assert result.returncode == 0
    files = sorted(path.name for path in out_dir.glob("*.png"))
    assert len(files) == 4
    assert "roboto-instance-bold.png" in files
    assert any("condensed" in name for name in files)